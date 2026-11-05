"""Monitor API tests with HA command/connection boundary substitutes."""
import asyncio
from functools import wraps
import importlib
import json
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from test_backups import HAStubTestCase, module


def command(schema):
    def decorate(handler):
        handler.schema = schema
        return handler
    return decorate


def require_admin(handler):
    @wraps(handler)
    def checked(hass, connection, msg):
        if not connection.user.is_admin:
            raise PermissionError("Unauthorized")
        return handler(hass, connection, msg)
    return checked


class WebSocketTests(HAStubTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.api = module("homeassistant.components.websocket_api",
                         websocket_command=command, require_admin=require_admin,
                         async_register_command=Mock())
        context = patch.dict(sys.modules, {"homeassistant.components.websocket_api": cls.api})
        context.start()
        cls.addClassCleanup(context.stop)
        cls.websocket = importlib.import_module("_amit_backup_tests.websocket")
        cls.monitor_module = importlib.import_module("_amit_backup_tests.monitor")

    def setUp(self):
        self.variable = self.protocol.Variable("Value", 0, self.protocol.VarType.INT16)
        self.client = SimpleNamespace(read_variable=AsyncMock(), write_variable=AsyncMock())
        self.entry = SimpleNamespace(title="Test PLC", data={"password": "private-secret"},
                                     state=self.websocket.ConfigEntryState.LOADED)
        self.registry_entries = {}
        self.registry_listeners = {}
        self.registry = SimpleNamespace(async_get=self.registry_entries.get)
        self.registry_api = SimpleNamespace(
            EVENT_ENTITY_REGISTRY_UPDATED="entity_registry_updated",
            async_get=Mock(return_value=self.registry),
            async_entries_for_config_entry=Mock(side_effect=lambda registry, entry_id: [
                entity for entity in self.registry_entries.values()
                if entity.config_entry_id == entry_id]),
        )
        context = patch.object(self.websocket, "er", self.registry_api)
        context.start()
        self.addCleanup(context.stop)

        def listen(event_type, listener):
            self.assertEqual(event_type, "entity_registry_updated")
            token = object()
            self.registry_listeners[token] = listener
            return lambda: self.registry_listeners.pop(token)

        self.hass = SimpleNamespace(
            data={"amit": {}},
            bus=SimpleNamespace(async_listen=Mock(side_effect=listen)),
            async_create_background_task=lambda coro, name: asyncio.create_task(coro, name=name),
            config_entries=SimpleNamespace(async_get_entry=Mock(return_value=self.entry),
                                           async_update_entry=Mock(), async_reload=AsyncMock()),
        )
        self.monitor = self.monitor_module.AMiTMonitor(
            self.hass, self.client, [self.variable], [self.variable], 30,
        )
        self.hass.data["amit"]["first"] = {"monitor": self.monitor, "all_variables": [self.variable],
                                           "variables": [self.variable], "writable_wids": set()}
        self.addAsyncCleanup(self.monitor.async_close)
        self.connection = self.connection_stub()
        self.api.async_register_command.reset_mock()

    def connection_stub(self):
        connection = SimpleNamespace(user=SimpleNamespace(is_admin=True, id="admin"), subscriptions={},
                                     send_result=Mock(), send_event=Mock(), send_error=Mock())
        def close():
            for unsubscribe in list(connection.subscriptions.values()):
                unsubscribe()
            connection.subscriptions.clear()
        self.addCleanup(close)
        return connection

    def registry_entity(self, entity_id="sensor.custom", unique_id="first_0",
                        entry_id="first", name="Room temperature", original_name="Value",
                        disabled_by=None, platform="amit"):
        entity = SimpleNamespace(entity_id=entity_id, unique_id=unique_id,
                                 config_entry_id=entry_id, name=name, original_name=original_name,
                                 disabled_by=disabled_by, platform=platform)
        self.registry_entries[entity_id] = entity
        return entity

    def registry_event(self, entity_id="sensor.custom", action="update", **data):
        for listener in list(self.registry_listeners.values()):
            listener(SimpleNamespace(data={"entity_id": entity_id, "action": action, **data}))

    def subscribe(self, connection=None, entry_id="first", msg_id=1):
        self.websocket.websocket_subscribe(self.hass, connection or self.connection,
                                          {"id": msg_id, "entry_id": entry_id})

    def matrix_setup(self):
        self.matrix = self.protocol.Variable("Matrix", 3, self.protocol.VarType.MATRIX_INT16,
                                             writable=False, rows=20, cols=20,
                                             station=4, metadata_version=1)
        self.client.read_matrix_block = AsyncMock(return_value=[[1, 2], [3, 4]])
        self.monitor.update_catalog([self.variable, self.matrix])
        return self.matrix_message()

    def matrix_message(self, **changes):
        revision = next(v["revision"] for v in self.monitor.snapshot()["variables"] if v["wid"] == 3)
        return {"id": 10, "entry_id": "first", "runtime_id": self.monitor.runtime_id,
                "wid": 3, "revision": revision, "row": 0, "col": 0, "rows": 2, "cols": 2,
                **changes}

    async def matrix_read(self, message, connection=None):
        tasks = []
        def schedule(coro, name):
            task = asyncio.create_task(coro, name=name)
            tasks.append(task)
            return task
        with patch.object(self.hass, "async_create_background_task", side_effect=schedule):
            self.websocket.websocket_matrix_read(self.hass, connection or self.connection, message)
        for task in tasks:
            await task

    async def test_matrix_read_returns_only_window_and_safe_metadata(self):
        message = self.matrix_setup()
        self.client.read_matrix_block.return_value = [[1, float("nan")], [float("inf"), -2]]
        await self.matrix_read(message)
        result = self.connection.send_result.call_args.args[1]
        self.assertEqual(result["values"], [[1, None], [None, -2]])
        self.assertEqual(result["runtime_id"], self.monitor.runtime_id)
        self.assertEqual(result["revision"], message["revision"])
        self.assertTrue(result["timestamp"])
        self.assertNotIn("private-secret", json.dumps(result, allow_nan=False))
        self.assertEqual(self.connection.subscriptions, {})
        self.assertEqual(self.monitor.snapshot()["samples"], [])
        self.client.read_matrix_block.assert_awaited_once_with(self.matrix, 0, 0, 2, 2)
        self.client.write_variable.assert_not_awaited()
        self.hass.config_entries.async_update_entry.assert_not_called()
        self.hass.config_entries.async_reload.assert_not_awaited()

    async def test_matrix_metadata_does_not_enable_scalar_subscription_or_entities(self):
        self.matrix_setup()
        self.subscribe()
        matrix = self.connection.send_event.call_args.args[1]["variables"][1]
        self.assertTrue(matrix["matrix_readable"])
        self.assertFalse(matrix["readable"])
        self.assertFalse(matrix["configured"])
        self.assertEqual((matrix["rows"], matrix["cols"], matrix["station"], matrix["metadata_version"]),
                         (20, 20, 4, 1))
        self.assertEqual(self.monitor.snapshot()["intervals"], {0: 30})
        await asyncio.sleep(0)
        self.client.read_matrix_block.assert_not_awaited()
        self.websocket.websocket_subscribe(self.hass, self.connection,
            {"id": 2, "entry_id": "first", "wids": [3]})
        self.assertEqual(self.connection.send_error.call_args.args[1], "invalid_request")

    async def test_matrix_validation_and_admin_gate_never_read_plc(self):
        message = self.matrix_setup()
        self.connection.user.is_admin = False
        with self.assertRaises(PermissionError):
            await self.matrix_read(message)
        self.connection.user.is_admin = True
        for changes, code in (
            ({"entry_id": "missing"}, "not_found"),
            ({"runtime_id": "old"}, "stale_selection"),
            ({"revision": -1}, "stale_selection"), ({"wid": 99}, "stale_selection"),
            ({"wid": True}, "invalid_request"), ({"revision": False}, "invalid_request"),
            ({"row": -1}, "invalid_request"), ({"col": 20}, "invalid_request"),
            ({"rows": 0}, "invalid_request"), ({"cols": True}, "invalid_request"),
            ({"rows": 20, "cols": 20}, "invalid_request"),
            ({"row": 19, "rows": 2}, "invalid_request"),
            ({"row": "0"}, "invalid_request"),
            ({"wid": 0, "revision": self.monitor.snapshot()["variables"][0]["revision"]}, "unsupported_type"),
        ):
            with self.subTest(changes=changes):
                await self.matrix_read({**message, **changes})
                self.assertEqual(self.connection.send_error.call_args.args[1], code)
                self.assertEqual(self.connection.subscriptions, {})
        self.client.read_matrix_block.assert_not_awaited()

    async def test_matrix_concurrent_panels_and_rate_limit_are_shared(self):
        message = self.matrix_setup()
        entered, release = asyncio.Event(), asyncio.Event()
        async def read(*args):
            entered.set()
            await release.wait()
            return [[1, 2], [3, 4]]
        self.client.read_matrix_block.side_effect = read
        task = asyncio.create_task(self.matrix_read(message))
        await entered.wait()
        second = self.connection_stub()
        await self.matrix_read({**message, "id": 11}, second)
        self.assertEqual(second.send_error.call_args.args[1], "busy")
        self.assertEqual(self.client.read_matrix_block.await_count, 1)
        release.set()
        await task
        await self.matrix_read({**message, "id": 12}, second)
        self.assertEqual(second.send_error.call_args.args[1], "busy")
        with patch.object(self.monitor_module, "monotonic", return_value=self.monitor._matrix_after + .01):
            await self.matrix_read({**message, "id": 13}, second)
        self.assertEqual(self.client.read_matrix_block.await_count, 2)

    async def test_matrix_respects_normal_reads_and_connection_recovery(self):
        message = self.matrix_setup()
        with self.monitor.normal_reads():
            await self.matrix_read(message)
        self.assertEqual(self.connection.send_error.call_args.args[1], "busy")
        self.client.read_matrix_block.assert_not_awaited()
        self.client.read_matrix_block.side_effect = TimeoutError("private detail")
        await self.matrix_read(message)
        self.assertEqual(self.connection.send_error.call_args.args[1], "read_error")
        self.assertNotIn("private detail", str(self.connection.send_error.call_args))
        with patch.object(self.monitor_module, "monotonic", return_value=self.monitor._matrix_after + .01):
            await self.matrix_read(message)
        self.assertEqual(self.connection.send_error.call_args.args[1], "busy")
        self.assertEqual(self.client.read_matrix_block.await_count, 1)

    async def test_matrix_catalog_change_discards_pending_result(self):
        message = self.matrix_setup()
        async def read(*args):
            changed = self.protocol.Variable("Matrix", 3, self.protocol.VarType.MATRIX_INT16,
                                             rows=10, cols=20, station=4, metadata_version=1)
            self.monitor.update_catalog([self.variable, changed])
            return [[1, 2], [3, 4]]
        self.client.read_matrix_block.side_effect = read
        await self.matrix_read(message)
        self.assertEqual(self.connection.send_error.call_args.args[1], "stale_selection")
        self.connection.send_result.assert_not_called()
        self.assertNotEqual(self.matrix_message()["revision"], message["revision"])

    async def test_matrix_disconnect_cancels_read_and_cleans_up(self):
        message = self.matrix_setup()
        entered = asyncio.Event()
        async def read(*args):
            entered.set()
            await asyncio.Event().wait()
        self.client.read_matrix_block.side_effect = read
        task = asyncio.create_task(self.matrix_read(message))
        await entered.wait()
        self.connection.subscriptions[message["id"]]()
        await task
        self.assertIsNone(self.monitor._matrix_task)
        self.assertEqual(self.connection.subscriptions, {})
        self.connection.send_result.assert_not_called()
        self.connection.send_error.assert_not_called()

    async def test_matrix_disconnect_before_task_starts_never_reads_plc(self):
        message = self.matrix_setup()
        tasks = []
        def schedule(coro, name):
            task = asyncio.create_task(coro, name=name)
            tasks.append(task)
            return task
        with patch.object(self.hass, "async_create_background_task", side_effect=schedule):
            self.websocket.websocket_matrix_read(self.hass, self.connection, message)
        self.connection.subscriptions[message["id"]]()
        self.connection.subscriptions.clear()
        with self.assertRaises(asyncio.CancelledError):
            await tasks[0]
        self.client.read_matrix_block.assert_not_awaited()
        self.assertIsNone(self.monitor._matrix_task)

    async def test_matrix_schedule_failure_releases_connection_cleanup(self):
        message = self.matrix_setup()
        with patch.object(self.hass, "async_create_background_task", side_effect=RuntimeError):
            self.websocket.websocket_matrix_read(self.hass, self.connection, message)
        self.assertEqual(self.connection.subscriptions, {})
        self.assertEqual(self.connection.send_error.call_args.args[1], "read_error")
        self.client.read_matrix_block.assert_not_awaited()

    @unittest.skipUnless(hasattr(asyncio, "eager_task_factory"), "Requires Python 3.12+")
    async def test_matrix_eager_task_leaves_no_cleanup_after_completion(self):
        message = self.matrix_setup()
        loop = asyncio.get_running_loop()
        factory = loop.get_task_factory()
        try:
            loop.set_task_factory(asyncio.eager_task_factory)
            self.websocket.websocket_matrix_read(self.hass, self.connection, message)
        finally:
            loop.set_task_factory(factory)
        self.connection.send_result.assert_called_once()
        self.assertEqual(self.connection.subscriptions, {})
        self.assertIsNone(self.monitor._matrix_task)

    async def test_matrix_unload_cancels_read_and_rejects_future_requests(self):
        message = self.matrix_setup()
        entered = asyncio.Event()
        async def read(*args):
            entered.set()
            await asyncio.Event().wait()
        self.client.read_matrix_block.side_effect = read
        task = asyncio.create_task(self.matrix_read(message))
        await entered.wait()
        await self.monitor.async_close()
        await task
        self.assertEqual(self.connection.send_error.call_args.args[1], "not_found")
        self.assertIsNone(self.monitor._matrix_task)
        self.assertEqual(self.connection.subscriptions, {})
        await self.matrix_read(message)
        self.assertEqual(self.client.read_matrix_block.await_count, 1)

    async def test_matrix_requests_do_not_block_another_plc(self):
        message = self.matrix_setup()
        other_client = SimpleNamespace(read_matrix_block=AsyncMock(return_value=[[7]]))
        other = self.monitor_module.AMiTMonitor(self.hass, other_client, [self.matrix], [], 30)
        self.addAsyncCleanup(other.async_close)
        self.hass.data["amit"]["second"] = {"monitor": other}
        with self.monitor.normal_reads():
            await self.matrix_read(message)
            await self.matrix_read({**message, "id": 11, "entry_id": "second",
                "runtime_id": other.runtime_id, "revision": other.snapshot()["variables"][0]["revision"],
                "rows": 1, "cols": 1})
        self.assertEqual(self.connection.send_result.call_args.args[1]["values"], [[7]])
        self.client.read_matrix_block.assert_not_awaited()

    async def test_registration_is_separate_from_loading_or_unloading_plcs(self):
        self.websocket.async_register_commands(self.hass)
        self.assertEqual(self.api.async_register_command.call_count, 6)
        handlers = [c.args[1] for c in self.api.async_register_command.call_args_list]
        self.assertEqual(handlers, [self.websocket.websocket_list,
                                    self.websocket.websocket_subscribe, self.websocket.websocket_preview_add,
                                    self.websocket.websocket_confirm_add, self.websocket.websocket_addition_status,
                                    self.websocket.websocket_matrix_read])

    async def test_nonadmin_cannot_list_or_subscribe(self):
        self.connection.user.is_admin = False
        for handler, msg in ((self.websocket.websocket_list, {"id": 1}),
                             (self.websocket.websocket_subscribe, {"id": 2, "entry_id": "first"}),
                             (self.websocket.websocket_preview_add, {"id": 3, "entry_id": "first"}),
                             (self.websocket.websocket_confirm_add, {"id": 4, "entry_id": "first"}),
                             (self.websocket.websocket_addition_status, {"id": 5, "entry_id": "first"})):
            with self.assertRaises(PermissionError):
                handler(self.hass, self.connection, msg)
        self.assertEqual(self.connection.subscriptions, {})
        self.connection.send_result.assert_not_called()
        self.client.read_variable.assert_not_awaited()
        self.registry_api.async_get.assert_not_called()
        self.hass.bus.async_listen.assert_not_called()

    async def test_list_omits_secrets_unavailable_and_closed_entries(self):
        self.hass.data["amit"]["unavailable"] = {"client": self.client}
        self.websocket.websocket_list(self.hass, self.connection, {"id": 1})
        result = self.connection.send_result.call_args.args[1]
        self.assertEqual(result, [{"entry_id": "first", "title": "Test PLC"}])
        self.assertNotIn("private-secret", json.dumps(result))
        await self.monitor.async_close()
        self.websocket.websocket_list(self.hass, self.connection, {"id": 2})
        self.assertEqual(self.connection.send_result.call_args.args[1], [])

    async def test_unknown_plc_does_not_fall_back_to_loaded_one(self):
        self.subscribe(entry_id="missing")
        self.connection.send_error.assert_called_once_with(
            1, "not_found", "Requested PLC is not loaded")
        self.assertEqual(self.connection.subscriptions, {})
        self.client.read_variable.assert_not_awaited()

    async def test_snapshot_precedes_new_samples_and_is_not_measurement_history(self):
        self.subscribe()
        self.connection.send_result.assert_called_once_with(1)
        snapshot = self.connection.send_event.call_args.args[1]
        self.assertEqual(snapshot["kind"], "snapshot")
        self.assertEqual(snapshot["samples"], [])
        self.assertEqual(snapshot["variables"][0]["wid"], 0)
        self.monitor.record(self.variable, 5)
        event = self.connection.send_event.call_args.args[1]
        self.assertEqual(event["kind"], "sample")
        self.assertEqual(event["sample"]["value"], 5)
        second = self.connection_stub()
        self.subscribe(connection=second)
        self.assertEqual(second.send_event.call_args.args[1]["samples"], [event["sample"]])
        self.assertEqual(second.send_event.call_count, 1)
        self.client.read_variable.assert_not_awaited()

    async def test_custom_subscription_ack_precedes_interval_snapshot(self):
        self.websocket.websocket_subscribe(self.hass, self.connection,
            {"id": 1, "entry_id": "first", "interval": 2.5, "wids": [0]})
        self.connection.send_result.assert_called_once_with(1)
        self.connection.send_event.assert_called_once()
        self.assertEqual(self.connection.send_event.call_args.args[1]["intervals"], {0: 2.5})
        self.connection.subscriptions.pop(1)()
        self.assertEqual(self.monitor.snapshot()["intervals"], {0: 30})

    async def test_invalid_request_releases_registry_listener(self):
        for options in ({"interval": True}, {"interval": 121}, {"interval": "2"},
                        {"interval": float("nan")}, {"interval": 10**400},
                        {"interval": -(10**400)}, {"wids": [99]}, {"wids": [True]}):
            self.websocket.websocket_subscribe(self.hass, self.connection,
                {"id": 1, "entry_id": "first", **options})
            self.assertEqual(self.connection.send_error.call_args.args[1], "invalid_request")
            self.assertEqual(self.connection.subscriptions, {})
            self.assertEqual(self.registry_listeners, {})
            self.assertEqual(self.monitor._listeners, {})
        self.connection.send_result.assert_not_called()

    async def test_interval_requests_are_isolated_by_plc(self):
        other = self.monitor_module.AMiTMonitor(
            self.hass, self.client, [self.variable], [self.variable], 60)
        self.addAsyncCleanup(other.async_close)
        self.hass.data["amit"]["second"] = {"monitor": other}
        self.websocket.websocket_subscribe(self.hass, self.connection,
            {"id": 1, "entry_id": "first", "interval": 1})
        self.subscribe(entry_id="second", msg_id=2)
        self.assertEqual(self.monitor.snapshot()["intervals"], {0: 1})
        self.assertEqual(other.snapshot()["intervals"], {0: 60})
        await self.monitor.async_close()
        self.assertEqual(set(self.connection.subscriptions), {2})

    async def test_connection_cleanup_restores_remaining_viewer_interval(self):
        second = self.connection_stub()
        self.websocket.websocket_subscribe(self.hass, self.connection,
            {"id": 1, "entry_id": "first", "interval": 1})
        self.websocket.websocket_subscribe(self.hass, second,
            {"id": 2, "entry_id": "first", "interval": 10})
        self.connection.subscriptions.pop(1)()
        self.assertEqual(self.monitor.snapshot()["intervals"], {0: 10})
        self.assertEqual(second.send_event.call_args.args[1]["kind"], "intervals")
        second.subscriptions.pop(2)()
        self.assertEqual(self.monitor.snapshot()["intervals"], {0: 30})

    @unittest.skipUnless(hasattr(asyncio, "eager_task_factory"), "Requires Python 3.12+")
    async def test_eager_worker_cannot_send_samples_before_subscription_ack(self):
        extra = self.protocol.Variable("Extra", 2, self.protocol.VarType.FLOAT)
        monitor = self.monitor_module.AMiTMonitor(self.hass, self.client, [extra], [], 30)
        self.addAsyncCleanup(monitor.async_close)
        self.hass.data["amit"]["first"]["monitor"] = monitor
        self.client.read_variable.side_effect = ConnectionError("disconnected")
        order = []
        self.connection.send_result.side_effect = lambda *args: order.append("ack")
        self.connection.send_event.side_effect = lambda msg_id, event: order.append(event["kind"])
        loop = asyncio.get_running_loop()
        factory = loop.get_task_factory()
        try:
            loop.set_task_factory(asyncio.eager_task_factory)
            self.subscribe()
        finally:
            loop.set_task_factory(factory)
        self.assertEqual(order, ["ack", "snapshot"])
        await asyncio.sleep(0)
        self.assertEqual(order, ["ack", "snapshot", "sample"])

    async def test_unsubscribe_and_connection_close_release_last_values(self):
        self.subscribe()
        second = self.connection_stub()
        self.subscribe(connection=second)
        self.monitor.record(self.variable, 5)
        self.connection.subscriptions.pop(1)()
        self.assertEqual(len(self.monitor.snapshot()["samples"]), 1)
        # Model HA's ActiveConnection close callback.
        for unsubscribe in list(second.subscriptions.values()):
            unsubscribe()
        second.subscriptions.clear()
        self.assertEqual(self.monitor.snapshot()["samples"], [])
        third = self.connection_stub()
        self.subscribe(connection=third)
        self.assertEqual(third.send_event.call_args.args[1]["samples"], [])

    async def test_same_wid_on_two_plcs_is_isolated(self):
        other = self.monitor_module.AMiTMonitor(
            self.hass, self.client, [self.variable], [self.variable], 30)
        self.addAsyncCleanup(other.async_close)
        self.hass.data["amit"]["second"] = {"monitor": other}
        self.subscribe()
        self.subscribe(entry_id="second", msg_id=2)
        self.monitor.record(self.variable, 5)
        other.record(self.variable, 9)
        events = [c.args for c in self.connection.send_event.call_args_list
                  if c.args[1]["kind"] == "sample"]
        self.assertEqual([(msg_id, e["sample"]["value"]) for msg_id, e in events],
                         [(1, 5), (2, 9)])
        self.assertNotEqual(events[0][1]["runtime_id"], events[1][1]["runtime_id"])
        await self.monitor.async_close()
        self.assertEqual(set(self.connection.subscriptions), {2})
        self.assertFalse(other.closed)
        self.client.write_variable.assert_not_awaited()

    async def test_unload_notifies_viewer_and_removes_connection_subscription(self):
        self.subscribe()
        await self.monitor.async_close()
        self.assertEqual(self.connection.subscriptions, {})
        self.assertEqual(self.connection.send_event.call_args.args[1]["kind"], "unavailable")
        self.subscribe(msg_id=2)
        self.connection.send_error.assert_called_once_with(
            2, "not_found", "Requested PLC is not loaded")

    async def test_snapshot_lists_all_supported_entity_identities_and_disabled_entries(self):
        self.entry.data["variables"] = ["0"]
        self.registry_entity()
        self.registry_entity("number.other_name", "first_0_number", name=None,
                             original_name="Original number", disabled_by="user")
        self.registry_entity("switch.control", "first_0_switch", name=None, original_name=None)
        self.registry_entity("binary_sensor.state", "first_0_binary", name="State")
        self.subscribe()
        variable = self.connection.send_event.call_args.args[1]["variables"][0]
        self.assertTrue(variable["configured"])
        entities = variable["entities"]
        self.assertEqual([e["entity_id"] for e in entities], sorted(self.registry_entries))
        self.assertEqual(entities[1], {"entity_id": "number.other_name", "name": "Original number",
                                      "custom_name": None, "disabled": True})
        self.assertEqual(entities[2]["custom_name"], "Room temperature")
        self.assertEqual(entities[3]["name"], "Value")
        self.assertNotIn("private-secret", json.dumps(variable))

    async def test_configured_selection_is_independent_of_registry_existence(self):
        extra = self.protocol.Variable("No entity", 2, self.protocol.VarType.FLOAT)
        array = self.protocol.Variable("Array", 3, self.protocol.VarType.ARRAY)
        self.monitor.update_catalog([self.variable, extra, array])
        self.registry_entity(disabled_by="integration")
        self.entry.data["variables"] = ["2"]
        self.subscribe()
        variables = self.connection.send_event.call_args.args[1]["variables"]
        self.assertEqual([v["configured"] for v in variables], [False, True, False])
        self.assertTrue(variables[0]["entities"][0]["disabled"])
        self.assertEqual(variables[1]["entities"], [])
        self.connection.subscriptions.pop(1)()
        self.entry.data["variables"] = []  # Setup uses all readable variables as its fallback.
        self.subscribe(msg_id=2)
        self.assertEqual([v["configured"] for v in self.connection.send_event.call_args.args[1]["variables"]],
                         [True, True, False])

    async def test_exact_identity_matching_rejects_other_plcs_platforms_and_buttons(self):
        self.registry_entity()
        self.registry_entity("sensor.second", "second_0", entry_id="second")
        self.registry_entity("sensor.foreign", "first_0", platform="other")
        self.registry_entity("sensor.wrong_suffix", "first_0_number")
        self.registry_entity("sensor.wrong_prefix", "not_first_0")
        self.registry_entity("sensor.other_variable", "first_99")
        self.registry_entity("button.reload", "first_reload_variables", name="Reload")
        self.registry_entity("sensor.numeric_part", "first_99_0")
        self.subscribe()
        entities = self.connection.send_event.call_args.args[1]["variables"][0]["entities"]
        self.assertEqual([e["entity_id"] for e in entities], ["sensor.custom"])

    async def test_registry_changes_are_metadata_only_and_keep_samples_and_revisions(self):
        entity = self.registry_entity()
        self.subscribe()
        self.monitor.record(self.variable, 5)
        before = self.monitor.snapshot()
        for name, disabled_by in (("Renamed", None), (None, "user"), ("Value", None)):
            entity.name, entity.disabled_by = name, disabled_by
            self.registry_event(changes={"name": "Previous"})
            event = self.connection.send_event.call_args.args[1]
            self.assertEqual(event, {"kind": "entity_metadata", "runtime_id": self.monitor.runtime_id,
                             "variables": [{"wid": 0, "configured": True, "entities": [{
                                 "entity_id": "sensor.custom", "name": name or "Value",
                                 "custom_name": name, "disabled": disabled_by is not None}]}]})
            self.assertEqual(self.monitor.snapshot(), before)
        self.client.read_variable.assert_not_awaited()
        self.client.write_variable.assert_not_awaited()

    async def test_entity_id_rename_and_removal_use_previous_binding(self):
        entity = self.registry_entity()
        self.subscribe()
        del self.registry_entries[entity.entity_id]
        entity.entity_id = "sensor.renamed"
        self.registry_entries[entity.entity_id] = entity
        self.registry_event(entity.entity_id, old_entity_id="sensor.custom")
        event = self.connection.send_event.call_args.args[1]
        self.assertEqual(event["kind"], "entity_metadata")
        self.assertEqual(event["variables"][0]["entities"][0]["entity_id"], "sensor.renamed")
        del self.registry_entries[entity.entity_id]
        self.registry_event(entity.entity_id, action="remove")
        self.assertEqual(self.connection.send_event.call_args.args[1]["variables"],
                         [{"wid": 0, "configured": True, "entities": []}])

    async def test_created_entity_and_catalog_replacement_refresh_metadata(self):
        self.subscribe()
        self.registry_entity()
        self.registry_event(action="create")
        self.assertEqual(self.connection.send_event.call_args.args[1]["kind"], "entity_metadata")
        new = self.protocol.Variable("New", 2, self.protocol.VarType.FLOAT)
        self.registry_entity("number.new", "first_2_number", name="New label")
        self.monitor.update_catalog([new])
        catalog = self.connection.send_event.call_args.args[1]
        self.assertEqual(catalog["kind"], "catalog")
        self.assertEqual([v["wid"] for v in catalog["variables"]], [2])
        self.assertEqual(catalog["variables"][0]["entities"][0]["name"], "New label")
        self.registry_entries["number.new"].name = "Latest label"
        self.registry_event("number.new")
        changes = self.connection.send_event.call_args.args[1]["variables"]
        self.assertEqual([v["wid"] for v in changes], [2])
        self.assertEqual(changes[0]["entities"][0]["name"], "Latest label")

    async def test_unrelated_and_unchanged_registry_events_do_not_emit(self):
        self.registry_entity()
        self.subscribe()
        count = self.registry_api.async_entries_for_config_entry.call_count
        self.registry_entity("sensor.second", "second_0", entry_id="second")
        self.registry_event("sensor.second")
        self.assertEqual(self.registry_api.async_entries_for_config_entry.call_count, count)
        self.registry_event(changes={"icon": "mdi:test"})
        self.assertEqual(self.connection.send_event.call_count, 1)

    async def test_registry_updates_stay_isolated_between_plcs_with_the_same_wid(self):
        self.registry_entity()
        other_entity = self.registry_entity("sensor.second", "second_0", entry_id="second")
        other = self.monitor_module.AMiTMonitor(
            self.hass, self.client, [self.variable], [self.variable], 30)
        self.addAsyncCleanup(other.async_close)
        self.hass.data["amit"]["second"] = {"monitor": other}
        self.subscribe()
        self.subscribe(entry_id="second", msg_id=2)
        self.connection.send_event.reset_mock()
        other_entity.name = "Other room"
        self.registry_event("sensor.second")
        self.assertEqual(self.connection.send_event.call_count, 1)
        msg_id, event = self.connection.send_event.call_args.args
        self.assertEqual(msg_id, 2)
        self.assertEqual(event["runtime_id"], other.runtime_id)

    async def test_unsubscribe_and_unload_release_registry_listeners_once(self):
        self.registry_entity()
        self.subscribe()
        second = self.connection_stub()
        self.subscribe(connection=second)
        self.assertEqual(len(self.registry_listeners), 2)
        stale_callback = next(iter(self.registry_listeners.values()))
        unsubscribe = self.connection.subscriptions.pop(1)
        unsubscribe()
        unsubscribe()
        self.assertEqual(len(self.registry_listeners), 1)
        self.connection.send_event.reset_mock()
        self.registry_entries["sensor.custom"].name = "Changed"
        stale_callback(SimpleNamespace(data={"entity_id": "sensor.custom"}))
        self.connection.send_event.assert_not_called()
        self.registry_event()
        self.assertEqual(second.send_event.call_args.args[1]["kind"], "entity_metadata")
        await self.monitor.async_close()
        self.assertEqual(self.registry_listeners, {})
        self.assertEqual(second.subscriptions, {})

    async def test_failed_initial_send_releases_both_subscriptions(self):
        self.connection.send_event.side_effect = RuntimeError("Connection closed")
        with self.assertRaisesRegex(RuntimeError, "Connection closed"):
            self.subscribe()
        self.assertEqual(self.registry_listeners, {})
        self.assertEqual(self.monitor._listeners, {})
        self.assertEqual(self.connection.subscriptions, {})

    async def test_failed_unload_notification_still_releases_registry_listener(self):
        self.subscribe()
        self.connection.send_event.side_effect = RuntimeError("Connection closed")
        await self.monitor.async_close()
        self.assertEqual(self.registry_listeners, {})
        self.assertEqual(self.connection.subscriptions, {})

    def addition_setup(self):
        self.extra = self.protocol.Variable("New", 1, self.protocol.VarType.FLOAT, value=987654.25)
        self.array = self.protocol.Variable("Array", 2, self.protocol.VarType.ARRAY)
        self.entry.data.update(target="generic", variables=["0"], writable_variables=["0", "1"], scan_interval=30)
        self.monitor.update_catalog([self.variable, self.extra, self.array])
        self.hass.data["amit"]["first"].update(all_variables=[self.variable, self.extra, self.array],
                                               writable_wids={0})
        self.registry_entity()

    def addition_message(self, wids=(1,)):
        catalog = {v["wid"]: v for v in self.monitor.snapshot()["variables"]}
        return {"id": 99, "type": "amit/monitor/preview_add", "entry_id": "first",
                "runtime_id": self.monitor.runtime_id,
                "variables": [{"wid": wid, "revision": catalog[wid]["revision"]} for wid in wids]}

    def addition_preview(self, message=None, connection=None):
        connection = connection or self.connection
        connection.send_result.reset_mock()
        connection.send_error.reset_mock()
        self.websocket.websocket_preview_add(self.hass, connection, message or self.addition_message())
        return connection.send_result.call_args.args[1] if connection.send_result.called else None

    def confirmation_setup(self, wids=(1,)):
        self.addition_setup()
        self.tasks = []

        def create_task(coro, name):
            task = asyncio.create_task(coro, name=name)
            self.tasks.append(task)
            return task

        self.hass.async_create_background_task = create_task
        self.hass.config_entries.async_update_entry.side_effect = lambda entry, *, data: setattr(entry, "data", data)
        message = self.addition_message(wids)
        preview = self.addition_preview(message)
        return {**message, "type": "amit/monitor/confirm_add", "expires_at": preview["expires_at"],
                "preview_id": preview["preview_id"]}

    def confirm_addition(self, message):
        self.connection.send_result.reset_mock()
        self.connection.send_error.reset_mock()
        self.websocket.websocket_confirm_add(self.hass, self.connection, message)
        return self.connection.send_result.call_args.args[1] if self.connection.send_result.called else None

    def addition_status(self, operation, connection=None):
        connection = connection or self.connection
        connection.send_result.reset_mock()
        connection.send_error.reset_mock()
        self.websocket.websocket_addition_status(self.hass, connection, {
            "id": 100, "entry_id": operation["entry_id"], "operation_id": operation["operation_id"]})
        return connection.send_result.call_args.args[1] if connection.send_result.called else None

    async def replacement_runtime(self, entry_id):
        self.assertEqual(entry_id, "first")
        await self.monitor.async_close()
        replacement = self.monitor_module.AMiTMonitor(
            self.hass, self.client, [self.variable, self.extra], [self.variable, self.extra], 30)
        self.addAsyncCleanup(replacement.async_close)
        self.hass.data["amit"]["first"]["monitor"] = replacement
        self.entry.state = self.websocket.ConfigEntryState.LOADED
        return True

    async def test_confirm_saves_additively_before_reloading_only_the_selected_entry(self):
        message = self.confirmation_setup()
        self.entry.data["custom_names"] = {"0": "Custom"}
        message.update({key: self.addition_preview()[key] for key in ("preview_id", "expires_at")})
        original = dict(self.entry.data)
        other = {"monitor": SimpleNamespace(closed=False)}
        self.hass.data["amit"]["second"] = other
        self.hass.config_entries.async_reload.side_effect = self.replacement_runtime
        operation = self.confirm_addition(message)
        self.assertEqual(operation["status"], "saved")
        self.assertTrue(operation["saved"])
        self.hass.config_entries.async_reload.assert_not_awaited()
        self.assertEqual(self.entry.data, {**original, "variables": ["0", "1"], "writable_variables": ["0"]})
        await asyncio.gather(*self.tasks)
        self.assertEqual(self.addition_status(operation)["status"], "loaded")
        self.hass.config_entries.async_reload.assert_awaited_once_with("first")
        self.assertIs(self.hass.data["amit"]["second"], other)
        self.client.write_variable.assert_not_awaited()
        self.client.read_variable.assert_not_awaited()
        encoded = json.dumps(self.addition_status(operation))
        for hidden in ("private-secret", "_configuration", "custom_names", "_user_id", "preview_id"):
            self.assertNotIn(hidden, encoded)

    async def test_confirm_rejects_changed_configuration_catalog_registry_and_user(self):
        for change in ("data", "options", "catalog", "registry", "user", "writable", "runtime"):
            with self.subTest(change=change):
                self.setUp()
                message = self.confirmation_setup()
                if change == "data":
                    self.entry.data["scan_interval"] = 60
                elif change == "options":
                    self.entry.options = {"changed": True}
                elif change == "catalog":
                    self.extra.name = "Changed"
                    self.monitor.update_catalog([self.variable, self.extra, self.array])
                elif change == "registry":
                    self.registry_entity("sensor.new", "first_1")
                elif change == "user":
                    self.connection.user.id = "other-admin"
                elif change == "writable":
                    self.hass.data["amit"]["first"]["writable_wids"].clear()
                else:
                    message["runtime_id"] = "old-runtime"
                before = json.dumps(self.entry.data, sort_keys=True)
                self.assertIsNone(self.confirm_addition(message))
                self.assertIn(self.connection.send_error.call_args.args[1], ("stale_preview", "stale_selection"))
                self.assertEqual(json.dumps(self.entry.data, sort_keys=True), before)
                self.hass.config_entries.async_update_entry.assert_not_called()
                self.hass.config_entries.async_reload.assert_not_awaited()

    async def test_confirm_rejects_expired_tampered_and_invalid_selections(self):
        message = self.confirmation_setup()
        cases = [({"expires_at": 0}, "expired_preview"),
                 ({"expires_at": True}, "expired_preview"),
                 ({"expires_at": message["expires_at"] + 1000}, "expired_preview"),
                 ({"preview_id": "wrong"}, "stale_preview"),
                 ({"preview_id": "ž"}, "stale_preview"),
                 ({"variables": []}, "invalid_selection"),
                 ({"variables": [{"wid": 2, "revision": 3}]}, "invalid_selection")]
        for patch_data, code in cases:
            with self.subTest(patch_data=patch_data):
                self.assertIsNone(self.confirm_addition({**message, **patch_data}))
                self.assertEqual(self.connection.send_error.call_args.args[1], code)
        self.hass.config_entries.async_update_entry.assert_not_called()
        self.assertEqual(self.tasks, [])

    async def test_confirm_is_atomic_for_two_requests_and_does_not_replay_after_reload(self):
        message = self.confirmation_setup()
        self.hass.config_entries.async_reload.side_effect = self.replacement_runtime
        first = self.confirm_addition(message)
        self.assertIsNone(self.confirm_addition(message))
        self.assertEqual(self.connection.send_error.call_args.args[1], "busy")
        await asyncio.gather(*self.tasks)
        self.assertEqual(self.addition_status(first)["status"], "loaded")
        self.assertIsNone(self.confirm_addition(message))
        self.assertEqual(self.connection.send_error.call_args.args[1], "stale_selection")
        self.hass.config_entries.async_update_entry.assert_called_once()
        self.hass.config_entries.async_reload.assert_awaited_once()

    async def test_confirm_noop_does_not_save_reload_or_enable_disabled_entities(self):
        message = self.confirmation_setup((0,))
        self.entry.data["writable_variables"] = ["0"]
        self.registry_entries["sensor.custom"].disabled_by = "user"
        preview = self.addition_preview(self.addition_message((0,)))
        message.update(preview_id=preview["preview_id"], expires_at=preview["expires_at"])
        result = self.confirm_addition(message)
        self.assertEqual(result["status"], "unchanged")
        self.assertFalse(result["saved"])
        self.assertEqual(self.registry_entries["sensor.custom"].disabled_by, "user")
        self.hass.config_entries.async_update_entry.assert_not_called()
        self.assertEqual(self.tasks, [])

    async def test_confirm_preserves_all_mode_and_removes_stale_write_permissions(self):
        message = self.confirmation_setup()
        self.entry.data["variables"] = []
        preview = self.addition_preview()
        message.update(preview_id=preview["preview_id"], expires_at=preview["expires_at"])
        operation = self.confirm_addition(message)
        self.assertEqual(self.entry.data["variables"], [])
        self.assertEqual(self.entry.data["writable_variables"], ["0"])
        await asyncio.gather(*self.tasks)
        self.assertTrue(self.addition_status(operation)["saved"])

    async def test_failed_save_does_not_start_reload(self):
        message = self.confirmation_setup()
        before = dict(self.entry.data)
        self.hass.config_entries.async_update_entry.side_effect = ValueError("Cannot save")
        self.assertIsNone(self.confirm_addition(message))
        self.assertEqual(self.connection.send_error.call_args.args[1], "save_failed")
        self.assertEqual(self.entry.data, before)
        self.assertEqual(self.tasks, [])

    async def test_reload_failure_keeps_saved_configuration_and_reports_failure(self):
        for failure in (False, RuntimeError("Reload failed"), asyncio.CancelledError()):
            with self.subTest(failure=type(failure).__name__):
                self.setUp()
                message = self.confirmation_setup()
                if failure is False:
                    self.hass.config_entries.async_reload.return_value = False
                else:
                    self.hass.config_entries.async_reload.side_effect = failure
                operation = self.confirm_addition(message)
                await asyncio.gather(*self.tasks, return_exceptions=True)
                result = self.addition_status(operation)
                self.assertEqual(result["status"], "failed")
                self.assertTrue(result["saved"])
                self.assertEqual(self.entry.data["variables"], ["0", "1"])
                self.assertEqual(self.entry.data["writable_variables"], ["0"])

    async def test_pending_reload_can_finish_later_and_status_survives_reconnection(self):
        message = self.confirmation_setup()

        async def pending(entry_id):
            await self.monitor.async_close()
            self.hass.data["amit"].pop(entry_id)
            self.entry.state = self.websocket.ConfigEntryState.SETUP_RETRY
            return False

        self.hass.config_entries.async_reload.side_effect = pending
        operation = self.confirm_addition(message)
        await asyncio.gather(*self.tasks)
        reconnected = self.connection_stub()
        self.assertEqual(self.addition_status(operation, reconnected)["status"], "pending")
        self.hass.data["amit"]["first"] = {}
        await self.replacement_runtime("first")
        self.assertEqual(self.addition_status(operation, reconnected)["status"], "loaded")

    async def test_retry_does_not_report_loaded_before_entry_setup_finishes(self):
        message = self.confirmation_setup()

        async def retry(entry_id):
            self.entry.state = self.websocket.ConfigEntryState.SETUP_RETRY
            return False

        self.hass.config_entries.async_reload.side_effect = retry
        operation = self.confirm_addition(message)
        await asyncio.gather(*self.tasks)
        self.assertEqual(self.addition_status(operation)["status"], "pending")
        await self.replacement_runtime("first")
        for state in (self.websocket.ConfigEntryState.SETUP_IN_PROGRESS,
                      self.websocket.ConfigEntryState.SETUP_RETRY):
            with self.subTest(state=state):
                self.entry.state = state
                result = self.addition_status(operation)
                self.assertEqual(result["status"], "pending")
                self.assertTrue(result["saved"])
                self.assertIsNone(result["error"])
        self.entry.state = self.websocket.ConfigEntryState.LOADED
        self.assertEqual(self.addition_status(operation)["status"], "loaded")

    async def test_retry_reports_terminal_entry_failure_with_or_without_a_new_monitor(self):
        message = self.confirmation_setup()
        operation = self.confirm_addition(message)
        await asyncio.gather(*self.tasks)
        baseline = dict(self.hass.data[self.websocket.MONITOR_ADDITIONS]["first"])
        await self.replacement_runtime("first")
        replacement = self.hass.data["amit"]["first"]["monitor"]
        for has_monitor in (False, True):
            for state in (self.websocket.ConfigEntryState.SETUP_ERROR,
                          self.websocket.ConfigEntryState.MIGRATION_ERROR,
                          self.websocket.ConfigEntryState.NOT_LOADED,
                          self.websocket.ConfigEntryState.FAILED_UNLOAD):
                with self.subTest(state=state, has_monitor=has_monitor):
                    self.hass.data[self.websocket.MONITOR_ADDITIONS]["first"] = dict(baseline)
                    self.hass.data["amit"]["first"]["monitor"] = replacement if has_monitor else None
                    self.entry.state = state
                    result = self.addition_status(operation)
                    self.assertEqual(result["status"], "failed")
                    self.assertEqual(result["error"], "reload_failed")
                    self.assertTrue(result["saved"])
                    self.assertEqual(self.entry.data["variables"], ["0", "1"])
        self.client.write_variable.assert_not_awaited()

    async def test_status_does_not_claim_success_after_another_configuration_change(self):
        message = self.confirmation_setup()
        operation = self.confirm_addition(message)
        await asyncio.gather(*self.tasks)
        self.entry.data["scan_interval"] = 60
        result = self.addition_status(operation)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error"], "configuration_changed")
        self.assertEqual(self.entry.data["scan_interval"], 60)

    async def test_task_creation_failure_still_reports_that_configuration_was_saved(self):
        message = self.confirmation_setup()
        self.hass.async_create_background_task = Mock(side_effect=RuntimeError("Task rejected"))
        operation = self.confirm_addition(message)
        self.assertEqual(operation["status"], "failed")
        self.assertTrue(operation["saved"])
        self.assertEqual(self.entry.data["variables"], ["0", "1"])
        self.hass.config_entries.async_reload.assert_not_awaited()

    async def test_configuration_changed_before_reload_starts_is_not_reloaded_or_overwritten(self):
        message = self.confirmation_setup()
        operation = self.confirm_addition(message)
        self.entry.data["variables"] = ["0"]
        self.entry.data["scan_interval"] = 60
        await asyncio.gather(*self.tasks)
        result = self.addition_status(operation)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error"], "configuration_changed")
        self.assertEqual(self.entry.data["variables"], ["0"])
        self.assertEqual(self.entry.data["scan_interval"], 60)
        self.hass.config_entries.async_reload.assert_not_awaited()

    async def test_reload_continues_without_original_connection_and_blocks_another_confirm(self):
        message = self.confirmation_setup()
        started, finish = asyncio.Event(), asyncio.Event()

        async def delayed_reload(entry_id):
            started.set()
            await finish.wait()
            return await self.replacement_runtime(entry_id)

        self.hass.config_entries.async_reload.side_effect = delayed_reload
        operation = self.confirm_addition(message)
        await started.wait()
        try:
            self.assertEqual(self.addition_status(operation)["status"], "reloading")
            self.assertIsNone(self.confirm_addition(message))
            self.assertEqual(self.connection.send_error.call_args.args[1], "busy")
            self.connection.send_result.side_effect = RuntimeError("Connection closed")
            self.connection.send_error.side_effect = RuntimeError("Connection closed")
        finally:
            finish.set()
            await asyncio.gather(*self.tasks)
        self.assertEqual(self.addition_status(operation, self.connection_stub())["status"], "loaded")
        self.hass.config_entries.async_reload.assert_awaited_once_with("first")

    async def test_operation_status_is_private_to_its_admin_and_entry(self):
        message = self.confirmation_setup()
        operation = self.confirm_addition(message)
        await asyncio.gather(*self.tasks)
        other = self.connection_stub()
        other.user.id = "other-admin"
        self.assertIsNone(self.addition_status(operation, other))
        self.assertIsNone(self.addition_status({**operation, "entry_id": "second"}))
        self.assertIsNone(self.addition_status({**operation, "operation_id": "unknown"}))
        self.assertEqual(self.connection.send_error.call_args.args[1], "not_found")

    async def test_addition_preview_is_read_only_and_omits_credentials_and_values(self):
        self.addition_setup()
        before = json.dumps(self.entry.data, sort_keys=True)
        result = self.addition_preview(self.addition_message((1, 0, 1)))
        self.assertEqual(result["added_wids"], [1])
        self.assertEqual(result["already_configured_wids"], [0])
        self.assertEqual(result["config_patch"], {"variables": ["0", "1"], "writable_variables": ["0"]})
        self.assertEqual(result["removed_write_wids"], [1])
        self.assertTrue(result["requires_reload"])
        self.assertEqual(result["entry_id"], "first")
        self.assertEqual(result["runtime_id"], self.monitor.runtime_id)
        self.assertEqual(len(result["preview_id"]), 64)
        self.assertEqual(result["variables"][0]["entities"][0]["custom_name"], "Room temperature")
        encoded = json.dumps(result)
        for hidden in ("private-secret", "987654.25", '"password"', '"samples"', '"value"'):
            self.assertNotIn(hidden, encoded)
        self.assertEqual(json.dumps(self.entry.data, sort_keys=True), before)
        self.hass.config_entries.async_update_entry.assert_not_called()
        self.hass.config_entries.async_reload.assert_not_awaited()
        self.client.read_variable.assert_not_awaited()
        self.client.write_variable.assert_not_awaited()
        self.assertEqual(self.monitor._listeners, {})

    async def test_addition_preview_includes_existing_variable_that_becomes_readable(self):
        self.addition_setup()
        previous = self.protocol.Variable("PreviouslyArray", 0, self.protocol.VarType.ARRAY)
        current = self.protocol.Variable("NowNumeric", 0, self.protocol.VarType.FLOAT)
        self.entry.data["writable_variables"] = []
        before = json.dumps(self.entry.data, sort_keys=True)
        self.registry_entries.clear()
        self.hass.data["amit"]["first"].update(
            variables=[previous], all_variables=[current, self.extra], writable_wids=set())
        self.monitor.update_catalog([current, self.extra])

        result = self.addition_preview()

        self.assertEqual(result["added_wids"], [1])
        self.assertEqual(result["newly_monitored_wids"], [0, 1])
        self.assertEqual([v["wid"] for v in result["variables"]], [0, 1])
        self.assertEqual(result["variables"][0]["name"], "NowNumeric")
        self.assertEqual(result["config_patch"], {"variables": ["0", "1"], "writable_variables": []})
        self.assertTrue(result["requires_reload"])
        self.assertEqual(json.dumps(self.entry.data, sort_keys=True), before)
        self.assertFalse(previous.is_readable())
        self.hass.config_entries.async_update_entry.assert_not_called()
        self.hass.config_entries.async_reload.assert_not_awaited()
        self.client.read_variable.assert_not_awaited()
        self.client.write_variable.assert_not_awaited()

    async def test_addition_preview_preserves_all_mode_and_shows_full_implicit_effect(self):
        self.addition_setup()
        self.entry.data["variables"] = []
        other = self.protocol.Variable("Implicit", 3, self.protocol.VarType.FLOAT, writable=False)
        self.hass.data["amit"]["first"]["all_variables"].append(other)
        self.monitor.update_catalog(self.hass.data["amit"]["first"]["all_variables"])
        result = self.addition_preview()
        self.assertEqual(result["selection_mode"], "all")
        self.assertEqual(result["config_patch"]["variables"], [])
        self.assertEqual(result["added_wids"], [])
        self.assertEqual(result["newly_monitored_wids"], [1, 3])
        self.assertEqual([v["wid"] for v in result["variables"]], [1, 3])
        self.assertEqual(result["config_patch"]["writable_variables"], ["0"])

    async def test_already_added_preview_is_noop_and_preserves_disabled_registry_entities(self):
        self.addition_setup()
        self.entry.data["writable_variables"] = ["0"]
        self.registry_entries["sensor.custom"].disabled_by = "user"
        result = self.addition_preview(self.addition_message((0,)))
        self.assertFalse(result["requires_reload"])
        self.assertEqual(result["added_wids"], [])
        self.assertTrue(result["variables"][0]["entities"][0]["disabled"])
        self.assertEqual(result["config_patch"]["variables"], ["0"])

    async def test_addition_preview_rejects_empty_unknown_and_unsupported_selection_as_a_whole(self):
        self.addition_setup()
        invalid = [[], [{"wid": 999, "revision": 1}], [{"wid": True, "revision": 2}],
                   [{"wid": 1, "revision": True}], self.addition_message((2,))["variables"],
                   self.addition_message()["variables"] + [{"wid": 999, "revision": 1}]]
        for variables in invalid:
            with self.subTest(variables=variables):
                message = {**self.addition_message(), "variables": variables}
                self.assertIsNone(self.addition_preview(message))
                self.assertEqual(self.connection.send_error.call_args.args[1], "invalid_selection")
        self.hass.config_entries.async_update_entry.assert_not_called()
        self.client.read_variable.assert_not_awaited()

    async def test_addition_preview_rejects_old_runtime_and_changed_variable_definition(self):
        self.addition_setup()
        old = self.addition_message()
        self.assertIsNone(self.addition_preview({**old, "runtime_id": "old-runtime"}))
        self.assertEqual(self.connection.send_error.call_args.args[1], "stale_selection")
        renamed = self.protocol.Variable("Changed", 1, self.protocol.VarType.FLOAT)
        self.monitor.update_catalog([self.variable, renamed, self.array])
        self.assertIsNone(self.addition_preview(old))
        self.assertEqual(self.connection.send_error.call_args.args[1], "stale_selection")

    async def test_addition_preview_unknown_closed_or_missing_entry_never_falls_back(self):
        self.addition_setup()
        message = self.addition_message()
        self.assertIsNone(self.addition_preview({**message, "entry_id": "missing"}))
        self.assertEqual(self.connection.send_error.call_args.args[1], "not_found")
        self.hass.config_entries.async_get_entry.return_value = None
        self.assertIsNone(self.addition_preview(message))
        self.hass.config_entries.async_get_entry.return_value = self.entry
        await self.monitor.async_close()
        self.assertIsNone(self.addition_preview(message))
        self.client.read_variable.assert_not_awaited()

    async def test_preview_fingerprint_tracks_configuration_user_and_registry_but_not_samples(self):
        self.addition_setup()
        unsubscribe = self.monitor.subscribe(Mock())
        with patch.object(self.websocket, "time", return_value=1000.75):
            first = self.addition_preview()
            self.assertEqual(first["expires_at"], 1300)
            self.monitor.record(self.variable, 123)
            self.assertEqual(self.addition_preview()["preview_id"], first["preview_id"])
            self.entry.data["scan_interval"] = 60
            configured = self.addition_preview()
            self.assertNotEqual(configured["preview_id"], first["preview_id"])
            self.connection.user.id = "other-admin"
            user_changed = self.addition_preview()
            self.assertNotEqual(user_changed["preview_id"], configured["preview_id"])
            self.registry_entries["sensor.custom"].name = "Renamed in HA"
            # Include that binding in the reviewed variables.
            before = self.addition_preview(self.addition_message((0, 1)))
            self.registry_entries["sensor.custom"].disabled_by = "user"
            self.assertNotEqual(self.addition_preview(self.addition_message((0, 1)))["preview_id"], before["preview_id"])
        unsubscribe()
        self.client.read_variable.assert_not_awaited()

    async def test_preview_fingerprint_tracks_readonly_policy_and_other_catalog_changes(self):
        self.addition_setup()
        with patch.object(self.websocket, "time", return_value=1000):
            first = self.addition_preview()
            self.extra.writable = False
            self.assertNotEqual(self.addition_preview()["preview_id"], first["preview_id"])
            first = self.addition_preview()
            third = self.protocol.Variable("Another", 3, self.protocol.VarType.FLOAT)
            self.hass.data["amit"]["first"]["all_variables"].append(third)
            self.monitor.update_catalog(self.hass.data["amit"]["first"]["all_variables"])
            self.assertNotEqual(self.addition_preview()["preview_id"], first["preview_id"])

    async def test_addition_preview_is_bound_to_one_plc_even_when_wids_match(self):
        self.addition_setup()
        other_variable = self.protocol.Variable("Other PLC", 1, self.protocol.VarType.FLOAT)
        other = self.monitor_module.AMiTMonitor(self.hass, self.client, [self.variable, other_variable], [self.variable], 30)
        self.addAsyncCleanup(other.async_close)
        self.hass.data["amit"]["second"] = {"monitor": other, "all_variables": [self.variable, other_variable],
                                           "variables": [self.variable], "writable_wids": set()}
        other_entry = SimpleNamespace(data={"target": "generic", "variables": ["0"]})
        self.hass.config_entries.async_get_entry.side_effect = {"first": self.entry, "second": other_entry}.get
        message = {**self.addition_message(), "entry_id": "second"}
        self.assertIsNone(self.addition_preview(message))
        result = self.addition_preview({**message, "runtime_id": other.runtime_id,
            "variables": [{"wid": 1, "revision": other.snapshot()["variables"][1]["revision"]}]})
        self.assertEqual(result["entry_id"], "second")
        self.assertEqual(result["variables"][0]["name"], "Other PLC")
        self.hass.config_entries.async_update_entry.assert_not_called()


if __name__ == "__main__":
    unittest.main()
