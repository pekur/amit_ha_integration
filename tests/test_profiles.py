"""Profile classification and writable-selection regressions without HA/PLC."""
import importlib
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from test_backups import HAStubTestCase


class ProfileEntityTests(HAStubTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.platforms = {
            name: importlib.import_module(f"_amit_backup_tests.{name}")
            for name in ("sensor", "number", "switch", "binary_sensor")
        }

    def variable(self, name, wid, var_type=None, *, writable=True):
        return self.protocol.Variable(
            name, wid, var_type if var_type is not None else self.protocol.VarType.FLOAT,
            writable=writable,
        )

    async def entities(self, variables, writable=(), *, profile="generic", values=None):
        entry_data = {"host": "plc.invalid"}
        if profile is not None:
            entry_data["target"] = profile
        entry = SimpleNamespace(entry_id="entry", data=entry_data)
        coordinator = SimpleNamespace(data=values or {}, async_request_refresh=AsyncMock())
        client = SimpleNamespace(write_variable=AsyncMock(return_value=True))
        hass = SimpleNamespace(data={"amit": {entry.entry_id: {
            "variables": variables, "writable_wids": set(writable),
            "coordinator": coordinator, "client": client,
        }}})
        result = {}
        for name, platform in self.platforms.items():
            result[name] = []
            await platform.async_setup_entry(hass, entry, result[name].extend)
        return result, client

    async def test_generic_temperature_like_name_keeps_numeric_value_and_no_unit(self):
        result, _ = await self.entities([self.variable("Tlak", 1)], values={1: 150.25})
        sensor, = result["sensor"]
        self.assertEqual(sensor.native_value, 150.25)
        self.assertIsNone(sensor._attr_device_class)
        self.assertIsNone(sensor._attr_native_unit_of_measurement)
        self.assertEqual(sensor._attr_unique_id, "entry_1")

    async def test_generic_switch_and_alarm_names_stay_numeric(self):
        variables = [
            self.variable("ZapCounter", 1, self.protocol.VarType.INT16),
            self.variable("PorCounter", 2, self.protocol.VarType.INT16),
        ]
        result, client = await self.entities(variables, [1], values={1: 123, 2: 456})
        self.assertEqual(result["switch"], [])
        self.assertEqual(result["binary_sensor"], [])
        number, = result["number"]
        sensor, = result["sensor"]
        self.assertEqual(number.native_value, 123)
        self.assertEqual(sensor.native_value, 456)
        self.assertEqual(number._attr_native_step, 1)
        self.assertEqual(number._attr_native_min_value, -32768)
        self.assertEqual(number._attr_unique_id, "entry_1_number")
        await number.async_set_native_value(123)
        client.write_variable.assert_awaited_once_with(variables[0], 123)

    async def test_generic_setpoint_offset_and_measurement_names_have_plain_limits(self):
        variables = [self.variable(name, wid) for wid, name in enumerate(("Zad_UT1", "Hposun1", "TE01"), 1)]
        result, _ = await self.entities(variables, [1, 2, 3])
        self.assertEqual(len(result["number"]), 3)
        for number in result["number"]:
            self.assertIsNone(number._attr_native_unit_of_measurement)
            self.assertEqual((number._attr_native_min_value, number._attr_native_max_value), (-1000, 1000))

    async def test_biosuntec_and_legacy_entries_keep_classification_and_identifiers(self):
        for profile in ("biosuntec", None, "unknown"):
            with self.subTest(profile=profile):
                variables = [
                    self.variable("TE01", 1, writable=False),
                    self.variable("Por01", 2, self.protocol.VarType.INT16, writable=False),
                    self.variable("Zad_UT1", 3),
                    self.variable("Zap_UT1", 4, self.protocol.VarType.INT16),
                    self.variable("Hposun1", 5),
                ]
                result, _ = await self.entities(variables, [3, 4, 5], profile=profile, values={1: 22.5})
                self.assertEqual([entity._attr_unique_id for entity in result["sensor"]], ["entry_1"])
                self.assertEqual([entity._attr_unique_id for entity in result["binary_sensor"]], ["entry_2_binary"])
                self.assertEqual([entity._attr_unique_id for entity in result["switch"]], ["entry_4_switch"])
                self.assertEqual([entity._attr_unique_id for entity in result["number"]], ["entry_3_number", "entry_5_number"])
                self.assertEqual(result["sensor"][0]._attr_native_unit_of_measurement, "°C")
                self.assertEqual(result["binary_sensor"][0]._attr_device_class, "problem")
                self.assertEqual(result["number"][0]._attr_native_min_value, 5)
                self.assertEqual(result["number"][0]._attr_native_max_value, 35)
                self.assertEqual(result["number"][1]._attr_native_min_value, -10)

    async def test_invalid_legacy_writable_selection_keeps_readonly_measurements(self):
        variables = [
            self.variable("TE01", 1, writable=False),
            self.variable("Por01", 2, self.protocol.VarType.INT16, writable=False),
        ]
        result, client = await self.entities(variables, [1, 2], profile="biosuntec")
        self.assertEqual(len(result["sensor"]), 1)
        self.assertEqual(len(result["binary_sensor"]), 1)
        self.assertEqual(result["number"], [])
        self.assertEqual(result["switch"], [])
        client.write_variable.assert_not_awaited()

    async def test_biosuntec_still_filters_disconnected_temperature(self):
        result, _ = await self.entities([self.variable("TE01", 1)], profile="biosuntec", values={1: 146.19})
        self.assertIsNone(result["sensor"][0].native_value)

    async def test_non_scalar_variables_never_create_entities(self):
        variable = self.variable("ZapArray", 1, self.protocol.VarType.ARRAY)
        result, _ = await self.entities([variable], [1], profile="biosuntec")
        self.assertTrue(all(not entities for entities in result.values()))

    async def test_variable_name_preserves_existing_attributes_and_entity_identity(self):
        cases = [
            ("sensor", "AMiTSensor", "TE01", self.protocol.VarType.FLOAT, "", {"variable_type": "Float"}),
            ("number", "AMiTNumber", "Zad_UT1", self.protocol.VarType.FLOAT, "_number", {"variable_type": "Float"}),
            ("switch", "AMiTSwitch", "Zap_UT1", self.protocol.VarType.INT16, "_switch", {"raw_value": 1}),
            ("binary_sensor", "AMiTBinarySensor", "Por01", self.protocol.VarType.INT16, "_binary", {"raw_value": 1}),
        ]
        for profile in ("generic", "biosuntec", None):
            for platform, class_name, name, var_type, suffix, attributes in cases:
                with self.subTest(platform=platform, profile=profile):
                    variable = self.variable(name, 0, var_type)
                    data = {"host": "plc.invalid"}
                    if profile is not None:
                        data["target"] = profile
                    entry = SimpleNamespace(entry_id="entry", data=data)
                    coordinator = SimpleNamespace(data={0: 1})
                    client = SimpleNamespace(read_variable=AsyncMock(), write_variable=AsyncMock())
                    args = [coordinator]
                    if platform in ("number", "switch"):
                        args.append(client)
                    entity = getattr(self.platforms[platform], class_name)(*args, variable, entry)
                    expected = {"wid": 0, "variable_name": name, **attributes}
                    self.assertEqual(entity.extra_state_attributes, expected)
                    self.assertEqual(entity._attr_name, name)
                    self.assertEqual(entity._attr_unique_id, f"entry_0{suffix}")
                    entity._attr_name = "Custom entity name"
                    entity.entity_id = f"{platform}.renamed"
                    self.assertEqual(entity.extra_state_attributes, expected)
                    client.read_variable.assert_not_awaited()
                    client.write_variable.assert_not_awaited()


class WritableFlowTests(HAStubTestCase):
    def setUp(self):
        self.variables = [
            {"name": "TE01", "wid": 1, "type": "Float", "writable": False},
            {"name": "Zad_UT1", "wid": 2, "type": "Float", "writable": True},
            {"name": "Unselected", "wid": 3, "type": "Float", "writable": True},
            {"name": "Unknown", "wid": 4, "type": "Float"},
        ]
        self.entry = SimpleNamespace(entry_id="entry", data={
            "host": "plc.invalid", "variables": ["1", "2", "4"],
            "writable_variables": ["1", "2", "4"],
        })
        self.hass = SimpleNamespace(config_entries=SimpleNamespace(
            async_update_entry=Mock(), async_reload=AsyncMock(),
        ))

    def new_flow(self):
        flow = self.flow_module.AMiTConfigFlow()
        flow.hass = self.hass
        flow._data = dict(self.entry.data)
        flow._variables = self.variables
        return flow

    def options_flow(self):
        flow = self.flow_module.AMiTOptionsFlow(self.entry)
        flow.config_entry = self.entry
        flow.hass = self.hass
        flow._variables = self.variables
        flow._selected_variables = self.entry.data["variables"]
        flow._scan_interval = 30
        return flow

    @staticmethod
    def selector(form):
        return next((key, value) for key, value in form["data_schema"].items() if key.schema == "writable_variables")

    async def test_new_and_options_forms_offer_only_selected_writable_variables(self):
        for flow in (self.new_flow(), self.options_flow()):
            with self.subTest(flow=type(flow).__name__):
                form = await flow.async_step_writable()
                key, selector = self.selector(form)
                self.assertEqual([option["value"] for option in selector.options], ["2"])
                self.assertNotIn("1", key.default())
                self.assertNotIn("4", key.default())

    async def test_new_flow_filters_injected_readonly_unselected_and_unknown_wids(self):
        result = await self.new_flow().async_step_writable({"writable_variables": ["1", "2", "3", "4", "999"]})
        self.assertEqual(result["data"]["writable_variables"], ["2"])
        self.assertEqual(result["data"]["variables"], ["1", "2", "4"])

    async def test_options_filters_injected_writable_selection_before_reload(self):
        await self.options_flow().async_step_writable({"writable_variables": ["1", "2", "3", "4", "999"]})
        saved = self.hass.config_entries.async_update_entry.call_args.kwargs["data"]
        self.assertEqual(saved["writable_variables"], ["2"])
        self.assertEqual(saved["variables"], ["1", "2", "4"])
        self.hass.config_entries.async_reload.assert_awaited_once_with("entry")

    async def test_import_downgrades_readonly_control_to_monitored_and_keeps_names(self):
        flow = self.new_flow()
        flow._import_data = {"writable_variables": [
            {"wid": 1, "custom_name": "Temperature", "entity_id": "sensor.saved"},
            {"wid": 2},
        ]}
        with patch.object(self.flow_module, "validate_connection", AsyncMock(return_value={"variables": self.variables})):
            result = await flow.async_step_import_confirm({"host": "plc.invalid"})
        self.assertEqual(set(result["data"]["variables"]), {"1", "2"})
        self.assertEqual(result["data"]["writable_variables"], ["2"])
        self.assertEqual(result["data"]["custom_names"], {"1": "Temperature"})
        self.assertEqual(result["data"]["custom_entity_ids"], {"1": "sensor.saved"})

    async def test_generic_writable_measurement_prefix_is_not_biosuntec_locked(self):
        flow = self.new_flow()
        flow._data["target"] = "generic"
        flow._variables = [dict(self.variables[0], writable=True)]
        result = await flow.async_step_writable({"writable_variables": ["1"]})
        self.assertEqual(result["data"]["writable_variables"], ["1"])


if __name__ == "__main__":
    unittest.main()
