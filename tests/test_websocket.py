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
        self.entry = SimpleNamespace(title="Test PLC", data={"password": "private-secret"})
        self.hass = SimpleNamespace(
            data={"amit": {}},
            async_create_background_task=lambda coro, name: asyncio.create_task(coro, name=name),
            config_entries=SimpleNamespace(async_get_entry=Mock(return_value=self.entry)),
        )
        self.monitor = self.monitor_module.AMiTMonitor(
            self.hass, self.client, [self.variable], [self.variable], 30,
        )
        self.hass.data["amit"]["first"] = {"monitor": self.monitor}
        self.addAsyncCleanup(self.monitor.async_close)
        self.connection = self.connection_stub()
        self.api.async_register_command.reset_mock()

    def connection_stub(self):
        connection = SimpleNamespace(user=SimpleNamespace(is_admin=True), subscriptions={},
                                     send_result=Mock(), send_event=Mock(), send_error=Mock())
        self.addCleanup(connection.subscriptions.clear)
        return connection

    def subscribe(self, connection=None, entry_id="first", msg_id=1):
        self.websocket.websocket_subscribe(self.hass, connection or self.connection,
                                          {"id": msg_id, "entry_id": entry_id})

    async def test_registration_is_separate_from_loading_or_unloading_plcs(self):
        self.websocket.async_register_commands(self.hass)
        self.assertEqual(self.api.async_register_command.call_count, 2)
        handlers = [c.args[1] for c in self.api.async_register_command.call_args_list]
        self.assertEqual(handlers, [self.websocket.websocket_list,
                                    self.websocket.websocket_subscribe])

    async def test_nonadmin_cannot_list_or_subscribe(self):
        self.connection.user.is_admin = False
        for handler, msg in ((self.websocket.websocket_list, {"id": 1}),
                             (self.websocket.websocket_subscribe, {"id": 2, "entry_id": "first"})):
            with self.assertRaises(PermissionError):
                handler(self.hass, self.connection, msg)
        self.assertEqual(self.connection.subscriptions, {})
        self.connection.send_result.assert_not_called()
        self.client.read_variable.assert_not_awaited()

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


if __name__ == "__main__":
    unittest.main()
