"""Entry setup/recovery regressions with mocked HA lifecycle boundaries."""
import asyncio
import importlib
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from test_backups import HAStubTestCase, module
from test_protocol import long_frame, short_frame


class ConfigEntryNotReady(Exception):
    pass


class UpdateFailed(Exception):
    pass


class CoordinatorStub:
    def __init__(self, hass, logger, *, name, update_method, update_interval):
        self.update_method = update_method
        self.data = None
        self.listeners = {}

    def async_add_listener(self, callback):
        token = object()
        self.listeners[token] = callback
        return lambda: self.listeners.pop(token)

    async def async_poll_if_listening(self):
        # Model HA's scheduled polling: no listeners means no refresh.
        if self.listeners:
            self.data = await self.update_method()
            for callback in list(self.listeners.values()):
                callback()

    async def async_config_entry_first_refresh(self):
        # Model HA's documented UpdateFailed -> retryable setup behavior.
        try:
            self.data = await self.update_method()
        except UpdateFailed as err:
            raise ConfigEntryNotReady(str(err)) from err


class SetupTests(HAStubTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        import sys
        sys.modules["homeassistant.core"].ServiceCall = object
        sys.modules["homeassistant.exceptions"].ConfigEntryNotReady = ConfigEntryNotReady
        sys.modules["homeassistant.helpers.update_coordinator"] = module(
            "homeassistant.helpers.update_coordinator",
            DataUpdateCoordinator=CoordinatorStub, UpdateFailed=UpdateFailed,
        )
        cls.integration = importlib.import_module("_amit_backup_tests.__init__")

    def setUp(self):
        self.other_entry = {"client": object()}
        self.hass = SimpleNamespace(
            data={"amit": {"other_entry": self.other_entry}},
            async_create_background_task=lambda coro, name: asyncio.create_task(coro, name=name),
            services=SimpleNamespace(has_service=Mock(return_value=True), async_register=Mock()),
            config_entries=SimpleNamespace(
                async_forward_entry_setups=AsyncMock(),
                async_unload_platforms=AsyncMock(return_value=True),
            ),
        )
        self.entry = SimpleNamespace(entry_id="test_entry", data={
            "host": "plc.invalid", "variables": ["4001"],
        })
        self.variable = self.protocol.Variable("Sample", 4001, self.protocol.VarType.INT16)
        self.client = SimpleNamespace(
            connect=AsyncMock(return_value=True),
            disconnect=AsyncMock(),
            load_variables=AsyncMock(return_value=[self.variable]),
            read_variable=AsyncMock(return_value=123),
        )
        context = patch.object(self.integration, "AMiTClient", return_value=self.client)
        context.start()
        self.addCleanup(context.stop)

    def assert_clean_failure(self):
        self.client.disconnect.assert_awaited_once()
        self.assertEqual(self.hass.data["amit"], {"other_entry": self.other_entry})
        self.hass.services.async_register.assert_not_called()

    async def test_failed_connection_retries_without_starting_platforms(self):
        self.client.connect.return_value = False
        with self.assertRaises(ConfigEntryNotReady):
            await self.integration.async_setup_entry(self.hass, self.entry)
        self.assert_clean_failure()
        self.client.load_variables.assert_not_awaited()
        self.hass.config_entries.async_forward_entry_setups.assert_not_awaited()

    async def test_discovery_failure_retries_then_can_recover(self):
        self.client.load_variables.side_effect = [ConnectionError("offline"), [self.variable]]
        with self.assertRaises(ConfigEntryNotReady):
            await self.integration.async_setup_entry(self.hass, self.entry)
        self.assert_clean_failure()
        self.assertTrue(await self.integration.async_setup_entry(self.hass, self.entry))
        self.assertEqual(self.hass.data["amit"][self.entry.entry_id]["coordinator"].data, {4001: 123})
        self.assertEqual(self.client.disconnect.await_count, 1)
        self.hass.config_entries.async_forward_entry_setups.assert_awaited_once()

    async def test_failed_first_read_retries_and_cleans_up(self):
        self.client.read_variable.side_effect = TimeoutError("offline")
        with self.assertRaises(ConfigEntryNotReady):
            await self.integration.async_setup_entry(self.hass, self.entry)
        self.assert_clean_failure()
        self.hass.config_entries.async_forward_entry_setups.assert_not_awaited()

    async def test_partial_read_failure_keeps_available_values(self):
        second = self.protocol.Variable("Other", 4002, self.protocol.VarType.INT16)
        self.entry.data["variables"].append("4002")
        self.client.load_variables.return_value.append(second)
        self.client.read_variable.side_effect = [TimeoutError("one failed"), 456]
        self.assertTrue(await self.integration.async_setup_entry(self.hass, self.entry))
        coordinator = self.hass.data["amit"][self.entry.entry_id]["coordinator"]
        self.assertEqual(coordinator.data, {4001: None, 4002: 456})
        self.client.disconnect.assert_not_awaited()

    async def test_polling_failure_is_reported_and_next_poll_can_recover(self):
        await self.integration.async_setup_entry(self.hass, self.entry)
        coordinator = self.hass.data["amit"][self.entry.entry_id]["coordinator"]
        self.client.read_variable.side_effect = TimeoutError("offline")
        with self.assertRaises(UpdateFailed):
            await coordinator.update_method()
        self.client.read_variable.side_effect = None
        self.client.read_variable.return_value = 456
        self.assertEqual(await coordinator.update_method(), {4001: 456})

    async def test_fast_monitor_reads_continue_during_ten_second_normal_scan(self):
        variables = [self.protocol.Variable(f"Sample{i}", 4001 + i, self.protocol.VarType.INT16)
                     for i in range(90)]
        extras = [self.protocol.Variable(f"Extra{i}", 5000 + i, self.protocol.VarType.INT16)
                  for i in range(49)]
        self.client.load_variables.return_value = variables + extras
        self.entry.data.update(variables=[str(v.wid) for v in variables], scan_interval=10)
        await self.integration.async_setup_entry(self.hass, self.entry)
        data = self.hass.data["amit"][self.entry.entry_id]
        monitor = data["monitor"]
        self.addAsyncCleanup(monitor.async_close)
        normal_task, active, maximum = None, 0, 0
        lock = asyncio.Lock()  # Model the real protocol's per-request serialization.
        reads, samples = [], []
        loop = asyncio.get_running_loop()
        async def read(variable):
            nonlocal active, maximum
            ordinary = asyncio.current_task() is normal_task
            async with lock:
                active += 1
                maximum = max(maximum, active)
                try:
                    await asyncio.sleep(.1 if ordinary else .01)
                    reads.append((ordinary, variable.wid))
                    return 123
                finally:
                    active -= 1
        self.client.read_variable.side_effect = read
        def receive(event):
            if event["kind"] == "sample" and event["sample"]["wid"] == 4001:
                samples.append(loop.time())
        unsubscribe = monitor.subscribe(receive, interval=1, wids=[4001])
        started = loop.time()
        normal_task = asyncio.create_task(data["coordinator"].update_method())
        try:
            result = await asyncio.wait_for(normal_task, 20)
        finally:
            unsubscribe()
            if not normal_task.done():
                normal_task.cancel()
                await asyncio.gather(normal_task, return_exceptions=True)
        self.assertGreaterEqual(loop.time() - started, 10)
        self.assertGreater(len(samples), 8)
        self.assertLessEqual(max(b - a for a, b in zip(samples, samples[1:])), 1.3)
        self.assertEqual(maximum, 1)
        self.assertTrue(any(wid >= 5000 for _, wid in reads))
        self.assertEqual([wid for ordinary, wid in reads if ordinary], [v.wid for v in variables])
        self.assertEqual(result, {v.wid: 123 for v in variables})

    async def test_empty_but_successful_discovery_is_not_a_connection_failure(self):
        self.client.load_variables.return_value = []
        self.assertTrue(await self.integration.async_setup_entry(self.hass, self.entry))
        self.client.disconnect.assert_not_awaited()
        self.client.read_variable.assert_not_awaited()

    async def test_failure_after_starting_platforms_rolls_back_this_entry(self):
        self.hass.config_entries.async_forward_entry_setups.side_effect = RuntimeError("platform failed")
        with self.assertRaisesRegex(RuntimeError, "platform failed"):
            await self.integration.async_setup_entry(self.hass, self.entry)
        self.assert_clean_failure()
        self.hass.config_entries.async_unload_platforms.assert_awaited_once()

    async def test_unexpected_setup_exception_is_not_converted_to_network_failure(self):
        self.client.load_variables.side_effect = ValueError("bad configuration")
        with self.assertRaisesRegex(ValueError, "bad configuration"):
            await self.integration.async_setup_entry(self.hass, self.entry)
        self.assert_clean_failure()

    async def test_cancelled_setup_preserves_cancellation_and_cleans_up(self):
        self.client.load_variables.side_effect = asyncio.CancelledError()
        with self.assertRaises(asyncio.CancelledError):
            await self.integration.async_setup_entry(self.hass, self.entry)
        self.assert_clean_failure()

    async def test_platform_cleanup_error_does_not_mask_cancellation(self):
        self.hass.config_entries.async_forward_entry_setups.side_effect = asyncio.CancelledError()
        self.hass.config_entries.async_unload_platforms.side_effect = RuntimeError("cleanup failed")
        with self.assertLogs(self.integration.__name__, level="ERROR"):
            with self.assertRaises(asyncio.CancelledError):
                await self.integration.async_setup_entry(self.hass, self.entry)
        self.assertIs(self.hass.data["amit"][self.entry.entry_id]["client"], self.client)
        self.client.disconnect.assert_not_awaited()

    async def test_failed_unload_keeps_data_and_client_until_cleanup_succeeds(self):
        self.hass.config_entries.async_forward_entry_setups.side_effect = RuntimeError("platform failed")
        self.hass.config_entries.async_unload_platforms.return_value = False
        with self.assertRaisesRegex(RuntimeError, "platform failed"):
            await self.integration.async_setup_entry(self.hass, self.entry)
        retained = self.hass.data["amit"][self.entry.entry_id]
        self.assertIs(retained["client"], self.client)
        self.client.disconnect.assert_not_awaited()

        with self.assertRaises(ConfigEntryNotReady):
            await self.integration.async_setup_entry(self.hass, self.entry)
        self.assertIs(self.hass.data["amit"][self.entry.entry_id], retained)
        self.assertEqual(self.client.connect.await_count, 1)

        self.hass.config_entries.async_unload_platforms.return_value = True
        self.hass.config_entries.async_forward_entry_setups.side_effect = None
        self.assertTrue(await self.integration.async_setup_entry(self.hass, self.entry))
        self.client.disconnect.assert_awaited_once()
        self.assertEqual(self.client.connect.await_count, 2)
        self.assertIsNot(self.hass.data["amit"][self.entry.entry_id], retained)
        self.assertIs(self.hass.data["amit"]["other_entry"], self.other_entry)

    async def test_previous_unload_exception_keeps_existing_runtime(self):
        retained = {"client": self.client}
        self.hass.data["amit"][self.entry.entry_id] = retained
        self.hass.config_entries.async_unload_platforms.side_effect = RuntimeError("cleanup failed")
        with self.assertRaises(ConfigEntryNotReady):
            await self.integration.async_setup_entry(self.hass, self.entry)
        self.assertIs(self.hass.data["amit"][self.entry.entry_id], retained)
        self.client.connect.assert_not_awaited()
        self.client.disconnect.assert_not_awaited()

    async def test_cancelled_previous_unload_preserves_existing_runtime(self):
        retained = {"client": self.client}
        self.hass.data["amit"][self.entry.entry_id] = retained
        self.hass.config_entries.async_unload_platforms.side_effect = asyncio.CancelledError()
        with self.assertRaises(asyncio.CancelledError):
            await self.integration.async_setup_entry(self.hass, self.entry)
        self.assertIs(self.hass.data["amit"][self.entry.entry_id], retained)
        self.client.connect.assert_not_awaited()
        self.client.disconnect.assert_not_awaited()

    async def test_cancellation_during_failed_setup_rollback_keeps_runtime(self):
        self.hass.config_entries.async_forward_entry_setups.side_effect = RuntimeError("platform failed")
        self.hass.config_entries.async_unload_platforms.side_effect = asyncio.CancelledError()
        with self.assertRaises(asyncio.CancelledError):
            await self.integration.async_setup_entry(self.hass, self.entry)
        self.assertIs(self.hass.data["amit"][self.entry.entry_id]["client"], self.client)
        self.client.disconnect.assert_not_awaited()

    async def test_options_client_is_closed_after_success_failure_or_cancellation(self):
        for outcome in ("success", "connect_failed", "discovery_failed", "cancelled"):
            with self.subTest(outcome=outcome):
                self.client.connect.reset_mock()
                self.client.disconnect.reset_mock()
                self.client.load_variables.reset_mock()
                self.client.connect.return_value = outcome != "connect_failed"
                self.client.load_variables.side_effect = {
                    "discovery_failed": ConnectionError("offline"),
                    "cancelled": asyncio.CancelledError(),
                }.get(outcome)
                options = self.flow_module.AMiTOptionsFlow(self.entry)
                options.config_entry = self.entry
                options.hass = self.hass
                options.async_show_form = lambda **kwargs: kwargs
                with patch.object(self.flow_module, "AMiTClient", return_value=self.client):
                    if outcome == "cancelled":
                        with self.assertRaises(asyncio.CancelledError):
                            await options.async_step_init()
                    elif outcome in ("connect_failed", "discovery_failed"):
                        with self.assertLogs(self.flow_module.__name__, level="ERROR"):
                            result = await options.async_step_init()
                        self.assertEqual(result["errors"], {"base": "cannot_connect"})
                    else:
                        result = await options.async_step_init()
                        self.assertEqual(result["errors"], {})
                self.client.disconnect.assert_awaited_once()
                if outcome == "connect_failed":
                    self.client.load_variables.assert_not_awaited()

    async def test_config_validation_does_not_require_wid_4000_or_int16(self):
        import struct

        for probe_response in (short_frame(status=2), long_frame(struct.pack("<f", 22.5))):
            with self.subTest(probe_response=probe_response.hex()):
                client = self.protocol.AMiTClient("plc.invalid")
                client._connected = True
                client.connect = AsyncMock(return_value=True)
                client.disconnect = AsyncMock()

                async def reply(frame):
                    if frame[7] == 1:
                        return probe_response
                    index = struct.unpack_from("<I", frame, 8)[0] - 0xFFFD0000
                    data = bytearray(26)
                    if index == 0:
                        struct.pack_into("<H", data, 0, 1)
                        data[2] = 2
                        data[3] = 4
                        struct.pack_into("<HH", data, 4, 1, 1)
                        struct.pack_into("<H", data, 8, 5000)
                        data[12:17] = b"Valid"
                    return long_frame(bytes(data), function=0x83)

                client._send_receive = AsyncMock(side_effect=reply)
                with patch.object(self.flow_module, "AMiTClient", return_value=client):
                    info = await self.flow_module.validate_connection(
                        self.hass, {"host": "plc.invalid", "target": "generic"},
                    )
                self.assertEqual(info["variables"], [{"wid": 5000, "name": "Valid", "type": "Float", "writable": True}])
                client.disconnect.assert_awaited_once()

    async def test_runtime_writable_set_excludes_readonly_and_unsupported_variables(self):
        readonly = self.protocol.Variable("TE01", 4002, self.protocol.VarType.FLOAT, writable=False)
        unsupported = self.protocol.Variable("Array", 4003, self.protocol.VarType.ARRAY)
        self.client.load_variables.return_value.extend([readonly, unsupported])
        self.entry.data["variables"] = ["4001", "4002", "4003"]
        self.entry.data["writable_variables"] = ["4001", "4002", "4003", "9999"]
        await self.integration.async_setup_entry(self.hass, self.entry)
        runtime = self.hass.data["amit"][self.entry.entry_id]
        self.assertEqual(runtime["writable_wids"], {4001})
        self.assertIn(readonly, runtime["variables"])

    async def test_service_obeys_writable_selection_and_handles_zero_wid_and_name(self):
        control = self.protocol.Variable("Control", 0, self.protocol.VarType.INT16)
        readonly = self.protocol.Variable("Locked", 4002, self.protocol.VarType.FLOAT, writable=False)
        self.client.load_variables.return_value = [control, self.variable, readonly]
        self.client.write_variable = AsyncMock(return_value=True)
        self.entry.data.update({
            "target": "generic", "variables": ["0", "4001", "4002"],
            "writable_variables": ["0", "4002"],
        })
        handlers = {}
        self.hass.services.has_service.return_value = False
        self.hass.services.async_register.side_effect = lambda domain, name, handler: handlers.update({name: handler})
        await self.integration.async_setup_entry(self.hass, self.entry)
        runtime = self.hass.data["amit"][self.entry.entry_id]
        runtime["coordinator"].async_request_refresh = AsyncMock()

        for target in ({"wid": 4001}, {"wid": 4002}, {"name": "Locked"}, {"wid": 9999}):
            with self.subTest(target=target):
                with self.assertLogs(self.integration.__name__, level="ERROR"):
                    await handlers["write_variable"](SimpleNamespace(data={
                        "entry_id": self.entry.entry_id, "value": 42, **target,
                    }))
                self.client.write_variable.assert_not_awaited()

        await handlers["write_variable"](SimpleNamespace(data={
            "entry_id": self.entry.entry_id, "wid": 0, "value": 42,
        }))
        self.client.write_variable.assert_awaited_once_with(control, 42)
        self.client.write_variable.reset_mock()
        await handlers["write_variable"](SimpleNamespace(data={
            "entry_id": self.entry.entry_id, "name": "Control", "value": 43,
        }))
        self.client.write_variable.assert_awaited_once_with(control, 43)

    async def register_write_service(self):
        """Create one loaded PLC with a writable value, without network I/O."""
        self.hass.data["amit"].clear()
        self.entry.data["writable_variables"] = ["4001"]
        self.client.write_variable = AsyncMock(return_value=True)
        handlers = {}
        self.hass.services.has_service.return_value = False
        self.hass.services.async_register.side_effect = lambda domain, name, handler: handlers.update({name: handler})
        await self.integration.async_setup_entry(self.hass, self.entry)
        runtime = self.hass.data["amit"][self.entry.entry_id]
        runtime["coordinator"].async_request_refresh = AsyncMock()
        return handlers["write_variable"], runtime

    async def test_explicit_unavailable_or_invalid_plc_never_falls_back(self):
        handler, runtime = await self.register_write_service()
        other_client = SimpleNamespace(write_variable=AsyncMock(return_value=True))
        for loaded_count in (1, 2):
            if loaded_count == 2:
                self.hass.data["amit"]["other_entry"] = dict(runtime, client=other_client)
            for target in ("unavailable_plc", "", None, 123, [], {}):
                with self.subTest(loaded_count=loaded_count, target=target):
                    with self.assertRaisesRegex(Exception, "Requested PLC is not loaded"):
                        await handler(SimpleNamespace(data={
                            "entry_id": target, "wid": 4001, "value": 42,
                        }))
                    self.client.write_variable.assert_not_awaited()
                    other_client.write_variable.assert_not_awaited()
                    runtime["coordinator"].async_request_refresh.assert_not_awaited()

    async def test_omitted_entry_id_still_selects_single_loaded_plc(self):
        handler, runtime = await self.register_write_service()
        await handler(SimpleNamespace(data={"wid": 4001, "value": 42}))
        self.client.write_variable.assert_awaited_once_with(self.variable, 42)
        runtime["coordinator"].async_request_refresh.assert_awaited_once()

    async def test_omitted_entry_id_with_multiple_or_no_loaded_plcs_never_writes(self):
        handler, runtime = await self.register_write_service()
        other_client = SimpleNamespace(write_variable=AsyncMock(return_value=True))
        self.hass.data["amit"]["other_entry"] = dict(runtime, client=other_client)
        for loaded_count in (2, 0):
            if loaded_count == 0:
                self.hass.data["amit"].clear()
            with self.subTest(loaded_count=loaded_count):
                with self.assertLogs(self.integration.__name__, level="ERROR"):
                    await handler(SimpleNamespace(data={"wid": 4001, "value": 42}))
                self.client.write_variable.assert_not_awaited()
                other_client.write_variable.assert_not_awaited()

    async def test_explicit_valid_entry_id_selects_only_that_plc(self):
        handler, runtime = await self.register_write_service()
        other_client = SimpleNamespace(write_variable=AsyncMock(return_value=True))
        other_coordinator = SimpleNamespace(async_request_refresh=AsyncMock())
        self.hass.data["amit"]["other_entry"] = dict(
            runtime, client=other_client, coordinator=other_coordinator,
        )
        await handler(SimpleNamespace(data={"entry_id": "other_entry", "wid": 4001, "value": 42}))
        other_client.write_variable.assert_awaited_once_with(self.variable, 42)
        other_coordinator.async_request_refresh.assert_awaited_once()
        self.client.write_variable.assert_not_awaited()
        runtime["coordinator"].async_request_refresh.assert_not_awaited()

    async def test_monitor_reuses_ordinary_poll_without_extra_requests(self):
        await self.integration.async_setup_entry(self.hass, self.entry)
        runtime = self.hass.data["amit"][self.entry.entry_id]
        monitor = runtime["monitor"]
        self.addAsyncCleanup(monitor.async_close)
        events = []
        monitor.subscribe(events.append)
        self.client.read_variable.reset_mock()
        await runtime["coordinator"].update_method()
        self.client.read_variable.assert_awaited_once_with(self.variable)
        self.assertEqual(events[0]["sample"]["value"], 123)
        self.assertIsNone(monitor._task)

    async def test_entry_lifecycle_updates_optional_panel(self):
        with patch.object(self.integration, "async_update_panel", new_callable=AsyncMock) as update:
            await self.integration.async_setup_entry(self.hass, self.entry)
            update.assert_awaited_once_with(self.hass)
            await self.integration.async_unload_entry(self.hass, self.entry)
            self.assertEqual(update.await_count, 2)

    async def test_setup_rollback_updates_optional_panel_after_cleanup(self):
        self.hass.config_entries.async_forward_entry_setups.side_effect = RuntimeError("platform failed")
        with patch.object(self.integration, "async_update_panel", new_callable=AsyncMock) as update:
            with self.assertRaisesRegex(RuntimeError, "platform failed"):
                await self.integration.async_setup_entry(self.hass, self.entry)
            update.assert_awaited_once_with(self.hass)

    async def test_monitor_keeps_polling_without_enabled_entities_and_releases_it(self):
        await self.integration.async_setup_entry(self.hass, self.entry)
        runtime = self.hass.data["amit"][self.entry.entry_id]
        monitor, coordinator = runtime["monitor"], runtime["coordinator"]
        self.addAsyncCleanup(monitor.async_close)
        self.client.read_variable.reset_mock()
        await coordinator.async_poll_if_listening()
        self.client.read_variable.assert_not_awaited()
        events = []
        first = monitor.subscribe(events.append)
        second = monitor.subscribe(Mock())
        self.assertEqual(len(coordinator.listeners), 1)
        await coordinator.async_poll_if_listening()
        self.client.read_variable.assert_awaited_once_with(self.variable)
        self.assertEqual(events[-1]["sample"]["value"], 123)
        first()
        self.assertEqual(len(coordinator.listeners), 1)
        second()
        self.assertEqual(coordinator.listeners, {})
        await coordinator.async_poll_if_listening()
        self.assertEqual(self.client.read_variable.await_count, 1)
        again = monitor.subscribe(Mock())
        await coordinator.async_poll_if_listening()
        self.assertEqual(self.client.read_variable.await_count, 2)
        again()

    async def test_monitor_and_entity_polling_listeners_are_independent(self):
        await self.integration.async_setup_entry(self.hass, self.entry)
        runtime = self.hass.data["amit"][self.entry.entry_id]
        monitor, coordinator = runtime["monitor"], runtime["coordinator"]
        self.addAsyncCleanup(monitor.async_close)
        remove_entity = coordinator.async_add_listener(Mock())
        remove_monitor = monitor.subscribe(Mock())
        self.assertEqual(len(coordinator.listeners), 2)
        remove_entity()
        await coordinator.async_poll_if_listening()
        self.assertEqual(len(coordinator.listeners), 1)
        remove_entity = coordinator.async_add_listener(Mock())
        remove_monitor()
        self.assertEqual(len(coordinator.listeners), 1)
        self.client.read_variable.reset_mock()
        await coordinator.async_poll_if_listening()
        self.client.read_variable.assert_awaited_once_with(self.variable)
        remove_monitor = monitor.subscribe(Mock())
        await monitor.async_close()
        self.assertEqual(len(coordinator.listeners), 1)
        remove_monitor()  # Repeated WebSocket cleanup remains safe.
        self.assertEqual(len(coordinator.listeners), 1)
        remove_entity()

    async def test_partial_read_error_does_not_set_global_monitor_backoff(self):
        second = self.protocol.Variable("Good", 4002, self.protocol.VarType.INT16)
        self.entry.data["variables"].append("4002")
        self.client.load_variables.return_value.append(second)
        await self.integration.async_setup_entry(self.hass, self.entry)
        runtime = self.hass.data["amit"][self.entry.entry_id]
        self.addAsyncCleanup(runtime["monitor"].async_close)
        runtime["monitor"].subscribe(Mock())
        self.client.read_variable.side_effect = [RuntimeError("PLC rejected read"), 42]
        with self.assertLogs(self.integration.__name__, level="WARNING"):
            result = await runtime["coordinator"].update_method()
        self.assertEqual(result, {4001: None, 4002: 42})
        self.assertEqual(runtime["monitor"]._retry_after, 0)
        self.client.read_variable.side_effect = [TimeoutError("offline"), 42]
        with self.assertLogs(self.integration.__name__, level="WARNING"):
            await runtime["coordinator"].update_method()
        self.assertGreater(runtime["monitor"]._retry_after, 0)

    async def test_failed_unload_keeps_monitor_until_platforms_can_unload(self):
        await self.integration.async_setup_entry(self.hass, self.entry)
        monitor = self.hass.data["amit"][self.entry.entry_id]["monitor"]
        self.addAsyncCleanup(monitor.async_close)
        events = []
        monitor.subscribe(events.append)
        self.hass.config_entries.async_unload_platforms.return_value = False
        self.assertFalse(await self.integration.async_unload_entry(self.hass, self.entry))
        self.assertFalse(monitor.closed)
        monitor.record(self.variable, 8)
        self.assertEqual(events[-1]["sample"]["value"], 8)
        self.client.disconnect.assert_not_awaited()
        self.hass.config_entries.async_unload_platforms.return_value = True
        self.assertTrue(await self.integration.async_unload_entry(self.hass, self.entry))
        self.assertTrue(monitor.closed)
        self.assertEqual(events[-1]["kind"], "unavailable")

    async def test_setup_rollback_closes_monitor_attached_by_platform(self):
        events = []
        monitors = []
        async def fail_platform_setup(*args):
            monitor = self.hass.data["amit"][self.entry.entry_id]["monitor"]
            monitors.append(monitor)
            monitor.subscribe(events.append)
            raise RuntimeError("platform failed")
        self.hass.config_entries.async_forward_entry_setups.side_effect = fail_platform_setup
        with self.assertRaisesRegex(RuntimeError, "platform failed"):
            await self.integration.async_setup_entry(self.hass, self.entry)
        self.assertTrue(monitors[0].closed)
        self.assertEqual(events[-1]["kind"], "unavailable")
        self.assert_clean_failure()

    async def test_reload_button_updates_monitor_catalog(self):
        await self.integration.async_setup_entry(self.hass, self.entry)
        runtime = self.hass.data["amit"][self.entry.entry_id]
        self.hass.services.async_call = AsyncMock()
        changed = self.protocol.Variable("Changed", 4001, self.protocol.VarType.ARRAY)
        self.client.load_variables.return_value = [changed]
        await self.button_module.AMiTReloadButton(self.hass, self.entry).async_press()
        self.assertEqual(runtime["all_variables"], [changed])
        catalog = runtime["monitor"].snapshot()["variables"]
        self.assertEqual(catalog[0]["name"], "Changed")
        self.assertFalse(catalog[0]["readable"])

    async def test_reload_service_updates_each_monitor_catalog(self):
        self.hass.data["amit"].clear()
        handlers = {}
        self.hass.services.has_service.return_value = False
        self.hass.services.async_register.side_effect = lambda domain, name, handler: handlers.update({name: handler})
        self.hass.config_entries.async_get_entry = Mock(return_value=self.entry)
        await self.integration.async_setup_entry(self.hass, self.entry)
        changed = self.protocol.Variable("Changed", 4001, self.protocol.VarType.ARRAY)
        self.client.load_variables.return_value = [changed]
        await handlers["reload_variables"](SimpleNamespace(data={}))
        runtime = self.hass.data["amit"][self.entry.entry_id]
        self.assertEqual(runtime["all_variables"], [changed])
        self.assertEqual(runtime["monitor"].snapshot()["variables"][0]["name"], "Changed")


if __name__ == "__main__":
    unittest.main()
