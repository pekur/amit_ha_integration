"""Offline backup regressions: python -m unittest discover -s tests -v.

Load the production modules with lightweight substitutes for unavailable HA,
voluptuous and aiofiles dependencies. These tests exercise backup behavior,
not HA's form validation or integration lifecycle.
"""
import importlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch


class FlowStub:
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__()

    def async_show_form(self, **kwargs):
        return {"type": "form", **kwargs}

    def async_create_entry(self, **kwargs):
        return {"type": "create_entry", **kwargs}

    async def async_set_unique_id(self, unique_id):
        self.unique_id = unique_id

    def _abort_if_unique_id_configured(self):
        pass


class Field:
    def __init__(self, schema, default=None):
        self.schema = schema
        self.default = lambda: default


class AsyncFile:
    def __init__(self, *args, **kwargs):
        self.file = open(*args, **kwargs)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.file.close()

    async def write(self, value):
        self.file.write(value)


class CoordinatorEntityStub:
    def __init__(self, coordinator):
        self.coordinator = coordinator


class EntityStub:
    _attr_device_class = None
    _attr_native_unit_of_measurement = None
    _attr_state_class = None
    _attr_capability_attributes = None

    @property
    def capability_attributes(self):
        return self._attr_capability_attributes


def module(name, **attributes):
    result = ModuleType(name)
    result.__dict__.update(attributes)
    return result


class HAStubTestCase(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        # A private package loads the actual modules without running HA setup.
        package = "_amit_backup_tests"
        root = Path(__file__).resolve().parents[1] / "custom_components" / "amit"
        selectors = SimpleNamespace(
            SelectOptionDict=dict,
            SelectSelectorConfig=lambda **kwargs: SimpleNamespace(**kwargs),
            SelectSelector=lambda config: config,
            SelectSelectorMode=SimpleNamespace(DROPDOWN="dropdown", LIST="list"),
        )
        registry = SimpleNamespace(
            async_get=lambda hass: None,
            async_entries_for_config_entry=lambda registry, entry_id: [],
        )
        config_entries = module(
            "homeassistant.config_entries", ConfigFlow=FlowStub,
            OptionsFlow=FlowStub, ConfigEntry=SimpleNamespace,
            ConfigEntryState=SimpleNamespace(
                LOADED="loaded", SETUP_RETRY="setup_retry", SETUP_IN_PROGRESS="setup_in_progress",
                SETUP_ERROR="setup_error", MIGRATION_ERROR="migration_error", NOT_LOADED="not_loaded",
                FAILED_UNLOAD="failed_unload"),
        )
        substitutes = {
            package: module(package, __path__=[str(root)]),
            "voluptuous": module(
                "voluptuous", Schema=lambda schema: schema,
                Required=Field, Optional=Field,
            ),
            "aiofiles": module("aiofiles", open=AsyncFile),
            "homeassistant": module("homeassistant", config_entries=config_entries),
            "homeassistant.config_entries": config_entries,
            "homeassistant.core": module(
                "homeassistant.core", HomeAssistant=object, callback=lambda fn: fn,
            ),
            "homeassistant.const": module(
                "homeassistant.const", UnitOfTemperature=SimpleNamespace(CELSIUS="°C"),
                Platform=SimpleNamespace(
                    SENSOR="sensor", NUMBER="number", BINARY_SENSOR="binary_sensor",
                    SWITCH="switch", BUTTON="button",
                ),
            ),
            "homeassistant.data_entry_flow": module(
                "homeassistant.data_entry_flow", FlowResult=dict,
            ),
            "homeassistant.exceptions": module(
                "homeassistant.exceptions", HomeAssistantError=Exception,
            ),
            "homeassistant.helpers": module(
                "homeassistant.helpers", selector=selectors, entity_registry=registry,
            ),
            "homeassistant.helpers.entity_platform": module(
                "homeassistant.helpers.entity_platform", AddEntitiesCallback=object,
            ),
            "homeassistant.helpers.entity": module(
                "homeassistant.helpers.entity", DeviceInfo=dict,
            ),
            "homeassistant.helpers.update_coordinator": module(
                "homeassistant.helpers.update_coordinator", CoordinatorEntity=CoordinatorEntityStub,
            ),
            "homeassistant.components": module("homeassistant.components"),
            "homeassistant.components.button": module(
                "homeassistant.components.button", ButtonEntity=object,
            ),
            "homeassistant.components.binary_sensor": module(
                "homeassistant.components.binary_sensor", BinarySensorEntity=EntityStub,
                BinarySensorDeviceClass=SimpleNamespace(PROBLEM="problem", HEAT="heat", RUNNING="running"),
            ),
            "homeassistant.components.sensor": module(
                "homeassistant.components.sensor", SensorEntity=EntityStub,
                SensorDeviceClass=SimpleNamespace(TEMPERATURE="temperature"),
                SensorStateClass=SimpleNamespace(MEASUREMENT="measurement"),
            ),
            "homeassistant.components.number": module(
                "homeassistant.components.number", NumberEntity=EntityStub,
                NumberMode=SimpleNamespace(BOX="box"),
            ),
            "homeassistant.components.switch": module(
                "homeassistant.components.switch", SwitchEntity=EntityStub,
            ),
        }
        context = patch.dict(sys.modules, substitutes)
        context.start()
        cls.addClassCleanup(context.stop)
        cls.flow_module = importlib.import_module(f"{package}.config_flow")
        cls.button_module = importlib.import_module(f"{package}.button")
        cls.protocol = importlib.import_module(f"{package}.protocol")


class BackupTests(HAStubTestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.backups = self.directory / "www" / "amit"
        self.hass = SimpleNamespace(
            config=SimpleNamespace(config_dir=str(self.directory)),
            services=SimpleNamespace(async_call=AsyncMock()),
        )

    def flow(self):
        flow = self.flow_module.AMiTConfigFlow()
        flow.hass = self.hass
        return flow

    @staticmethod
    def field(form, name):
        return next(
            (key, value) for key, value in form["data_schema"].items()
            if key.schema == name
        )

    def write_backup(self, data, filename="amit_backup.json"):
        self.backups.mkdir(parents=True, exist_ok=True)
        (self.backups / filename).write_text(json.dumps(data), encoding="utf-8")
        return filename

    async def test_lists_both_backup_names_once_in_reverse_order(self):
        for name in ("amit_export_20260101.json", "amit_legacy.json", "other.json"):
            self.write_backup({}, name)
        form = await self.flow().async_step_import_select()
        self.assertEqual(form["errors"], {})
        self.assertEqual(form["description_placeholders"]["backup_count"], "2")
        _, selector = self.field(form, "backup_file")
        self.assertEqual(
            [option["value"] for option in selector.options],
            ["amit_legacy.json", "amit_export_20260101.json"],
        )

    async def test_missing_and_empty_backup_directory(self):
        for exists in (False, True):
            with self.subTest(exists=exists):
                if exists:
                    self.backups.mkdir(parents=True)
                form = await self.flow().async_step_import_select()
                self.assertEqual(form["errors"], {"base": "no_backups"})

    async def test_import_prefills_saved_profile_and_legacy_default(self):
        for profile in (None, "biosuntec", "generic"):
            with self.subTest(profile=profile):
                backup = {"plc_connection": {"host": "plc.invalid"}}
                if profile is not None:
                    backup["target"] = profile
                filename = self.write_backup(backup)
                flow = self.flow()
                form = await flow.async_step_import_select({"backup_file": filename})
                self.assertEqual(form["step_id"], "import_confirm")
                self.assertEqual(flow._data["target"], profile or "biosuntec")
                key, _ = self.field(form, "target")
                self.assertEqual(key.default(), profile or "biosuntec")

    async def test_confirm_uses_selected_profile_before_connection_validation(self):
        for saved, selected in (("biosuntec", "generic"), ("generic", "biosuntec")):
            with self.subTest(saved=saved, selected=selected):
                filename = self.write_backup({
                    "plc_connection": {"host": "plc.invalid"}, "target": saved,
                    "monitored_variables": [{
                        "wid": 100, "custom_name": "Custom", "entity_id": "sensor.custom",
                    }],
                    "writable_variables": [{"wid": 4001}],
                })
                flow = self.flow()
                await flow.async_step_import_select({"backup_file": filename})
                seen = []

                async def validate(hass, data):
                    seen.append(data["target"])
                    return {"variables": [{"wid": 100, "writable": False}, {"wid": 4001, "writable": True}]}

                with patch.object(self.flow_module, "validate_connection", validate):
                    result = await flow.async_step_import_confirm({
                        "host": "plc.invalid", "target": selected,
                    })
                self.assertEqual(seen, [selected])
                self.assertEqual(result["type"], "create_entry")
                self.assertEqual(result["data"]["target"], selected)
                self.assertEqual(set(result["data"]["variables"]), {"100", "4001"})
                self.assertEqual(result["data"]["writable_variables"], ["4001"])
                self.assertEqual(result["data"]["custom_names"], {"100": "Custom"})
                self.assertEqual(result["data"]["custom_entity_ids"], {"100": "sensor.custom"})

    async def test_export_import_round_trip_and_old_entry_default(self):
        for profile in (None, "biosuntec", "generic"):
            with self.subTest(profile=profile):
                entry_data = {"host": "plc.invalid", "password": 12345}
                if profile is not None:
                    entry_data["target"] = profile
                entry = SimpleNamespace(entry_id="test_entry", data=entry_data)
                variable = self.protocol.Variable("Sample", 100, self.protocol.VarType.INT16)
                self.hass.data = {"amit": {entry.entry_id: {
                    "variables": [variable], "writable_wids": set(),
                }}}
                await self.button_module.AMiTExportButton(self.hass, entry).async_press()
                path, = self.backups.glob("amit_export_*.json")
                exported = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(exported["target"], profile or "biosuntec")
                self.assertNotIn("password", exported)
                self.assertNotIn("password", exported["plc_connection"])
                self.assertEqual(exported["monitored_variables"][0]["wid"], 100)
                flow = self.flow()
                await flow.async_step_import_select({"backup_file": path.name})
                with patch.object(self.flow_module, "validate_connection", AsyncMock(
                    return_value={"variables": [{"wid": 100}]},
                )):
                    result = await flow.async_step_import_confirm({"host": "plc.invalid"})
                self.assertEqual(result["data"]["target"], profile or "biosuntec")
                self.assertEqual(result["data"]["variables"], ["100"])
                path.unlink()


if __name__ == "__main__":
    unittest.main()
