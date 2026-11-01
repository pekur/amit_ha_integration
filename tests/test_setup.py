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
                        data[2] = 2
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







if __name__ == "__main__":
    unittest.main()
