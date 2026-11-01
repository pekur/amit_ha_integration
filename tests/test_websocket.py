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


if __name__ == "__main__":
    unittest.main()
