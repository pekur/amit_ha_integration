"""Offline live-monitor scheduling, samples, and lifecycle regressions."""
import asyncio
import importlib
import json
import struct
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock

from test_backups import HAStubTestCase
from test_protocol import long_frame


class MonitorTests(HAStubTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.module = importlib.import_module("_amit_backup_tests.monitor")

    def setUp(self):
        self.normal = self.protocol.Variable("Normal", 1, self.protocol.VarType.INT16)
        self.extra = self.protocol.Variable("Extra", 2, self.protocol.VarType.FLOAT)
        self.array = self.protocol.Variable("Array", 3, self.protocol.VarType.ARRAY)
        self.client = SimpleNamespace(read_variable=AsyncMock(return_value=12.5),
                                      write_variable=AsyncMock())
        self.hass = SimpleNamespace(async_create_background_task=
                                   lambda coro, name: asyncio.create_task(coro, name=name))

    def monitor(self, variables=None, monitored=None, interval=30):
        monitor = self.module.AMiTMonitor(
            self.hass, self.client,
            variables if variables is not None else [self.normal, self.extra, self.array],
            monitored if monitored is not None else [self.normal], interval,
        )
        self.addAsyncCleanup(monitor.async_close)
        return monitor

    async def next_read(self, count=1):
        async def wait():
            while self.client.read_variable.await_count < count:
                await asyncio.sleep(0.001)
        await asyncio.wait_for(wait(), 1)

    async def test_no_viewers_do_not_read_or_cache_values(self):
        monitor = self.monitor()
        monitor.record(self.normal, 99)
        await asyncio.sleep(0)
        self.assertEqual(monitor.snapshot()["samples"], [])
        self.client.read_variable.assert_not_awaited()
        self.assertEqual([v["readable"] for v in monitor.snapshot()["variables"]],
                         [True, True, False])

    async def test_viewers_share_one_worker_and_only_extra_readable_values(self):
        monitor = self.monitor()
        first, second = Mock(), Mock()
        unsubscribe_first = monitor.subscribe(first)
        task = monitor._task
        unsubscribe_second = monitor.subscribe(second)
        self.assertIs(monitor._task, task)
        await self.next_read()
        self.client.read_variable.assert_awaited_once_with(self.extra)
        self.assertEqual(first.call_args, second.call_args)
        unsubscribe_first()
        self.assertIs(monitor._task, task)
        unsubscribe_second()
        unsubscribe_second()  # HA cleanup may run after an entry has closed.
        await asyncio.wait_for(task, 1)
        self.assertEqual(monitor.snapshot()["samples"], [])
        self.assertIsNone(monitor._task)
        self.client.write_variable.assert_not_awaited()

    async def test_regular_reads_have_distinct_ids_even_when_unchanged(self):
        monitor = self.monitor([self.normal], [self.normal])
        events = []
        monitor.subscribe(events.append)
        self.assertIsNone(monitor._task)
        monitor.record(self.normal, 7)
        monitor.record(self.normal, 7)
        samples = [event["sample"] for event in events]
        self.assertEqual([s["value"] for s in samples], [7, 7])
        self.assertLess(samples[0]["sequence"], samples[1]["sequence"])
        self.assertTrue(samples[0]["timestamp"].endswith("+00:00"))
        self.assertEqual(len(monitor.snapshot()["samples"]), 1)
        self.client.read_variable.assert_not_awaited()

    async def test_failures_and_nonfinite_values_preserve_last_success(self):
        monitor = self.monitor([self.normal], [self.normal])
        monitor.subscribe(Mock())
        monitor.record(self.normal, 7)
        good = monitor.snapshot()["samples"][0]
        for value in (float("nan"), float("inf"), -float("inf"), None, True):
            monitor.record(self.normal, value)
            sample = monitor.snapshot()["samples"][0]
            self.assertEqual(sample["status"], "invalid")
            self.assertIsNone(sample["value"])
            self.assertEqual(sample["last_value"], 7)
            self.assertEqual(sample["last_success"], good["timestamp"])
            json.dumps(monitor.snapshot(), allow_nan=False)
        monitor.record(self.normal, failed=True)
        self.assertEqual(monitor.snapshot()["samples"][0]["status"], "read_error")
        monitor.record(self.normal, 0)
        self.assertEqual(monitor.snapshot()["samples"][0]["value"], 0)

    async def test_snapshot_is_not_a_new_sample_and_can_be_modified_by_caller(self):
        monitor = self.monitor([self.normal], [self.normal])
        events = []
        monitor.subscribe(events.append)
        monitor.record(self.normal, 7)
        snapshot = monitor.snapshot()
        snapshot["samples"][0]["value"] = 999
        monitor.snapshot()
        self.assertEqual(len(events), 1)
        self.assertEqual(monitor.snapshot()["samples"][0]["value"], 7)

    async def test_priority_gate_blocks_extras_during_normal_reads(self):
        monitor = self.monitor()
        with monitor.normal_reads():
            monitor.subscribe(Mock())
            await asyncio.sleep(0.01)
            self.client.read_variable.assert_not_awaited()
        await self.next_read()
        self.client.read_variable.assert_awaited_once_with(self.extra)

    async def test_real_protocol_lock_delays_normal_read_by_only_inflight_extra(self):
        client = self.protocol.AMiTClient("plc.invalid")
        started, release = asyncio.Event(), asyncio.Event()
        calls = []
        async def exchange(frame):
            if frame == client._create_read_frame(self.extra.wid, self.extra.var_type):
                calls.append("extra")
                started.set()
                await release.wait()
                return long_frame(struct.pack("<f", 12.5))
            calls.append("normal")
            return long_frame(struct.pack("<h", 7))
        client._send_receive_internal = AsyncMock(side_effect=exchange)
        monitor = self.module.AMiTMonitor(
            self.hass, client, [self.normal, self.extra], [self.normal], 30)
        self.addAsyncCleanup(monitor.async_close)
        monitor.subscribe(Mock())
        await asyncio.wait_for(started.wait(), 1)
        async def ordinary_read():
            with monitor.normal_reads():
                return await client.read_variable(self.normal)
        normal = asyncio.create_task(ordinary_read())
        try:
            await asyncio.sleep(.01)
            self.assertEqual(calls, ["extra"])
            release.set()
            self.assertEqual(await asyncio.wait_for(normal, 1), 7)
            self.assertEqual(calls, ["extra", "normal"])
            await asyncio.sleep(.01)
            self.assertEqual(calls, ["extra", "normal"])
        finally:
            release.set()
            normal.cancel()
            await asyncio.gather(normal, return_exceptions=True)

    async def test_rate_limit_and_fair_order(self):
        another = self.protocol.Variable("Other", 4, self.protocol.VarType.INT32)
        monitor = self.monitor([self.extra, another], [], interval=10)
        times = []
        self.client.read_variable.side_effect = lambda v: times.append(
            asyncio.get_running_loop().time()) or 12
        monitor.subscribe(Mock())
        await self.next_read(2)
        self.assertEqual([c.args[0].wid for c in self.client.read_variable.await_args_list], [2, 4])
        self.assertGreaterEqual(times[1] - times[0], self.module.MIN_READ_DELAY - .01)
        await asyncio.sleep(.01)
        self.assertEqual(self.client.read_variable.await_count, 2)

    async def test_selected_requests_combine_per_wid_and_restore_on_close(self):
        monitor = self.monitor()
        with monitor.normal_reads():
            first = monitor.subscribe(Mock(), interval=2.5, wids=[1])
            second = monitor.subscribe(Mock(), interval=10)
            self.assertEqual(monitor.snapshot()["intervals"], {1: 2.5, 2: 10})
            first()
            self.assertEqual(monitor.snapshot()["intervals"], {1: 10, 2: 10})
            second()
            self.assertEqual(monitor.snapshot()["intervals"], {1: 30, 2: 30})
            monitor.subscribe(Mock())
            self.assertEqual(monitor.snapshot()["intervals"], {1: 30, 2: 30})

    async def test_long_interval_overrides_extras_but_not_normal_polling(self):
        monitor = self.monitor()
        monitor.subscribe(Mock(), interval=120)
        await self.next_read()
        self.client.read_variable.assert_awaited_once_with(self.extra)
        self.assertEqual(monitor.snapshot()["intervals"], {1: 120, 2: 120})
        self.assertAlmostEqual(monitor._due[2] - monitor._last_read[2], 120)
        monitor.record(self.normal, 42)
        self.assertEqual(monitor.snapshot()["samples"][-1]["value"], 42)

    async def test_fresh_normal_read_defers_extra_read_for_selected_normal(self):
        monitor = self.monitor([self.normal], [self.normal])
        with monitor.normal_reads():
            monitor.subscribe(Mock(), interval=1, wids=[1])
            monitor.record(self.normal, 7)
        await asyncio.sleep(.03)
        self.client.read_variable.assert_not_awaited()
        monitor._due[1] = 0
        monitor._wake.set()
        await self.next_read()
        self.client.read_variable.assert_awaited_once_with(self.normal)
        self.client.write_variable.assert_not_awaited()

    async def test_empty_selection_keeps_device_interval(self):
        monitor = self.monitor([self.normal], [self.normal])
        monitor.subscribe(Mock(), interval=1, wids=[])
        self.assertEqual(monitor.snapshot()["intervals"], {1: 30})
        self.assertIsNone(monitor._task)

    async def test_invalid_requests_do_not_attach_or_start_reads(self):
        monitor = self.monitor()
        for interval in (True, "5", 0, .99, 120.01, float("inf"), float("nan")):
            with self.subTest(interval=interval), self.assertRaises(ValueError):
                monitor.subscribe(Mock(), interval=interval)
        for wids in ([True], [999], [3], ["1"], "1"):
            with self.subTest(wids=wids), self.assertRaises(ValueError):
                monitor.subscribe(Mock(), interval=1, wids=wids)
        self.assertEqual(monitor._listeners, {})
        self.assertIsNone(monitor._task)

    async def test_interval_bounds_and_decimal_are_accepted(self):
        monitor = self.monitor([self.normal], [self.normal])
        with monitor.normal_reads():
            for interval in (1, 1.25, 120):
                unsubscribe = monitor.subscribe(Mock(), interval=interval)
                self.assertEqual(monitor.snapshot()["intervals"], {1: interval})
                unsubscribe()

    async def test_default_viewer_limits_slower_override(self):
        monitor = self.monitor([self.normal], [self.normal])
        default = monitor.subscribe(Mock())
        monitor.subscribe(Mock(), interval=120)
        self.assertEqual(monitor.snapshot()["intervals"], {1: 30})
        default()
        self.assertEqual(monitor.snapshot()["intervals"], {1: 120})

    async def test_removed_selection_is_removed_from_schedule(self):
        monitor = self.monitor([self.normal], [self.normal])
        with monitor.normal_reads():
            monitor.subscribe(Mock(), interval=1, wids=[1])
            monitor.update_catalog([])
            self.assertEqual(monitor.snapshot()["intervals"], {})

    async def test_replacement_subscription_reuses_reads_and_keeps_other_viewer(self):
        monitor = self.monitor()
        with monitor.normal_reads():
            observer = Mock()
            monitor.subscribe(observer)
            previous = monitor.subscribe(Mock(), interval=1, wids=[1])
            monitor.record(self.normal, 7)
            monitor.record(self.extra, 8)
            samples = monitor.snapshot()["samples"]
            stamp = monitor._last_read[2]
            previous()
            monitor.subscribe(Mock(), interval=2.5, wids=[2])
            self.assertEqual(monitor.snapshot()["intervals"], {1: 30, 2: 2.5})
            self.assertEqual(monitor.snapshot()["samples"], samples)
            self.assertAlmostEqual(monitor._due[2], stamp + 2.5)
            self.assertEqual(observer.call_args.args[0]["kind"], "intervals")
        await asyncio.sleep(.03)
        self.client.read_variable.assert_not_awaited()

    async def test_custom_interval_does_not_shorten_transport_backoff(self):
        monitor = self.monitor([self.normal], [self.normal])
        self.client.read_variable.side_effect = TimeoutError("offline")
        monitor.subscribe(Mock(), interval=1)
        await self.next_read()
        self.assertGreater(monitor._retry_after - self.module.monotonic(), 29)
        await asyncio.sleep(self.module.MIN_READ_DELAY + .03)
        self.assertEqual(self.client.read_variable.await_count, 1)

    async def test_timeout_stops_the_scan_until_backoff_expires(self):
        another = self.protocol.Variable("Other", 4, self.protocol.VarType.INT32)
        monitor = self.monitor([self.extra, another], [], interval=30)
        self.client.read_variable.side_effect = TimeoutError("offline")
        monitor.subscribe(Mock())
        await self.next_read()
        await asyncio.sleep(self.module.MIN_READ_DELAY + .03)
        self.assertEqual(self.client.read_variable.await_count, 1)
        self.assertEqual(monitor.snapshot()["samples"][0]["status"], "read_error")
        # Advance only the deadline, without a real 30-second wait.
        monitor._retry_after = 0
        self.client.read_variable.side_effect = None
        monitor._wake.set()
        await self.next_read(2)
        self.assertEqual(monitor.snapshot()["samples"][-1]["value"], 12.5)

    async def test_rejected_variable_does_not_back_off_healthy_extra_reads(self):
        another = self.protocol.Variable("Healthy", 4, self.protocol.VarType.INT32)
        monitor = self.monitor([self.extra, another], [], interval=30)
        self.client.read_variable.side_effect = [RuntimeError("PLC rejected read"), 42]
        monitor.subscribe(Mock())
        await self.next_read(2)
        self.assertEqual([c.args[0].wid for c in self.client.read_variable.await_args_list], [2, 4])
        samples = {s["wid"]: s for s in monitor.snapshot()["samples"]}
        self.assertEqual(samples[2]["status"], "read_error")
        self.assertEqual(samples[4]["value"], 42)
        # Keep the failed variable's own retry deadline.
        await asyncio.sleep(self.module.MIN_READ_DELAY + .02)
        self.assertEqual(self.client.read_variable.await_count, 2)

    async def test_repeated_partial_normal_failures_do_not_starve_extras(self):
        monitor = self.monitor()
        with monitor.normal_reads():
            monitor.subscribe(Mock())
            monitor.record(self.normal, failed=True)
        for _ in range(4):
            await asyncio.sleep(.03)
            with monitor.normal_reads():
                monitor.record(self.normal, failed=True)
        await self.next_read()
        self.client.read_variable.assert_awaited_once_with(self.extra)

    async def test_normal_transport_failure_still_backs_off_extra_reads(self):
        monitor = self.monitor()
        with monitor.normal_reads():
            monitor.subscribe(Mock())
            monitor.record(self.normal, failed=True, connection_failed=True)
        await asyncio.sleep(self.module.MIN_READ_DELAY + .03)
        self.client.read_variable.assert_not_awaited()

    async def test_catalog_preserves_unchanged_samples_and_revises_changed_types(self):
        monitor = self.monitor([self.normal, self.array], [self.normal])
        events = []
        monitor.subscribe(events.append)
        monitor.record(self.normal, 7)
        old = monitor.snapshot()
        clone = self.protocol.Variable("Normal", 1, self.protocol.VarType.INT16)
        monitor.update_catalog([clone])
        self.assertEqual(monitor.snapshot()["samples"], old["samples"])
        self.assertEqual(len(monitor.snapshot()["variables"]), 1)
        changed = self.protocol.Variable("Normal", 1, self.protocol.VarType.ARRAY)
        monitor.update_catalog([changed])
        monitor.record(self.normal, 10)  # Old coordinator definition is ignored.
        self.assertEqual(monitor.snapshot()["samples"], [])
        self.assertNotEqual(monitor.snapshot()["variables"][0]["revision"],
                            old["variables"][0]["revision"])
        self.assertEqual(events[-1]["kind"], "catalog")
        self.client.read_variable.assert_not_awaited()

    async def test_removed_and_reintroduced_wid_gets_new_revision(self):
        monitor = self.monitor([self.normal], [self.normal])
        revision = monitor.snapshot()["variables"][0]["revision"]
        monitor.update_catalog([])
        monitor.update_catalog([self.normal])
        self.assertGreater(monitor.snapshot()["variables"][0]["revision"], revision)

    async def test_old_read_is_ignored_after_last_unsubscribe_and_resubscribe(self):
        monitor = self.monitor()
        release = asyncio.Event()
        async def read(variable):
            await release.wait()
            return 12
        self.client.read_variable.side_effect = read
        unsubscribe = monitor.subscribe(Mock())
        await self.next_read()
        task = monitor._task
        unsubscribe()
        events = []
        monitor.subscribe(events.append)
        self.assertIs(monitor._task, task)
        release.set()
        await asyncio.sleep(.01)
        self.assertEqual(events, [])
        await self.next_read(2)
        self.assertEqual(events[0]["sample"]["value"], 12)

    async def test_changed_catalog_ignores_inflight_old_definition(self):
        monitor = self.monitor()
        release = asyncio.Event()
        async def read(variable):
            await release.wait()
            return 12
        self.client.read_variable.side_effect = read
        events = []
        monitor.subscribe(events.append)
        await self.next_read()
        changed = self.protocol.Variable("Changed", 2, self.protocol.VarType.INT32)
        monitor.update_catalog([changed])
        release.set()
        await asyncio.sleep(.01)
        self.assertEqual([e["kind"] for e in events], ["catalog"])
        await self.next_read(2)
        self.assertEqual(self.client.read_variable.await_args_list[-1].args, (changed,))
        self.assertEqual(events[-1]["sample"]["revision"],
                         monitor.snapshot()["variables"][0]["revision"])

    async def test_close_cancels_inflight_read_and_rejects_new_subscribers(self):
        monitor = self.monitor()
        release = asyncio.Event()
        async def read(variable):
            await release.wait()
        self.client.read_variable.side_effect = read
        events = []
        monitor.subscribe(events.append)
        await self.next_read()
        task = monitor._task
        await monitor.async_close()
        self.assertTrue(task.done())
        self.assertTrue(monitor.closed)
        self.assertEqual(events[-1]["kind"], "unavailable")
        self.assertEqual(monitor.snapshot()["samples"], [])
        with self.assertRaises(ValueError):
            monitor.subscribe(Mock())

    async def test_units_follow_profile_without_inferring_generic_temperature(self):
        targets = importlib.import_module("_amit_backup_tests.targets")
        variables = [self.protocol.Variable(name, i, self.protocol.VarType.FLOAT)
                     for i, name in enumerate(("TE01", "Zad_UT1", "Hposun1", "Unknown"))]
        biosuntec = self.module.AMiTMonitor(
            self.hass, self.client, variables, variables, 30,
            targets.BIOSUNTEC.entity_rules)
        self.addAsyncCleanup(biosuntec.async_close)
        generic = self.monitor(variables, variables)
        self.assertEqual([v["unit"] for v in biosuntec.snapshot()["variables"]],
                         ["°C", "°C", "°C", None])
        self.assertEqual([v["unit"] for v in generic.snapshot()["variables"]],
                         [None] * 4)

    async def test_listener_failure_does_not_break_other_viewers(self):
        monitor = self.monitor([self.normal], [self.normal])
        monitor.subscribe(Mock(side_effect=RuntimeError("viewer failed")))
        events = []
        monitor.subscribe(events.append)
        monitor.record(self.normal, 5)
        self.assertEqual(events[0]["sample"]["value"], 5)


if __name__ == "__main__":
    unittest.main()
