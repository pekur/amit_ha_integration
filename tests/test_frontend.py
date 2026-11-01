"""Optional panel registration and code-only resource boundary tests."""
import asyncio
import importlib
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from test_backups import HAStubTestCase, module


class FrontendTests(HAStubTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.frontend = importlib.import_module("_amit_backup_tests.frontend")

    def setUp(self):
        self.callbacks = []
        self.panel_api = SimpleNamespace(async_register_panel=AsyncMock())
        self.frontend_api = SimpleNamespace(async_remove_panel=Mock())
        substitutes = {
            "homeassistant.setup": module("homeassistant.setup", async_when_setup=
                lambda hass, component, cb: self.callbacks.append((component, cb))),
            "homeassistant.components.frontend": self.frontend_api,
            "homeassistant.components.panel_custom": self.panel_api,
            "homeassistant.components.http": module("homeassistant.components.http", HomeAssistantView=object),
            "aiohttp": module("aiohttp", web=SimpleNamespace(Response=lambda **kwargs: SimpleNamespace(**kwargs))),
        }
        context = patch.dict(sys.modules, substitutes)
        context.start()
        self.addCleanup(context.stop)
        self.hass = SimpleNamespace(
            data={"amit": {}}, http=SimpleNamespace(register_view=Mock()),
            async_add_executor_job=AsyncMock(side_effect=lambda fn: fn()),
        )

    def load_entry(self, name="first"):
        self.hass.data["amit"][name] = {"monitor": SimpleNamespace(closed=False)}

    async def frontend_ready(self):
        await self.callbacks[0][1](self.hass, "frontend")

    async def test_headless_setup_neither_reads_files_nor_enables_frontend(self):
        self.load_entry()
        await self.frontend.async_setup_frontend(self.hass)
        await self.frontend.async_setup_frontend(self.hass)
        await self.frontend.async_update_panel(self.hass)
        self.assertEqual(len(self.callbacks), 1)
        self.assertEqual(self.callbacks[0][0], "frontend")
        self.hass.async_add_executor_job.assert_not_awaited()
        self.panel_api.async_register_panel.assert_not_awaited()

    async def test_resource_is_preloaded_once_and_contains_only_packaged_code(self):
        self.load_entry()
        await self.frontend.async_setup_frontend(self.hass)
        await self.frontend_ready()
        self.hass.async_add_executor_job.assert_awaited_once()
        view = self.hass.http.register_view.call_args.args[0]
        first, second = await view.get(None), await view.get(None)
        expected = (Path(__file__).parents[1] / "custom_components/amit/frontend/monitor.js").read_bytes()
        self.assertEqual(first.body, expected)
        self.assertIs(first.body, second.body)
        self.assertFalse(view.requires_auth)
        self.assertEqual(view.url, "/api/amit/monitor.js")
        self.assertEqual(first.content_type, "application/javascript")
        self.assertEqual(first.headers["Cache-Control"], "no-store")
        call = self.panel_api.async_register_panel.call_args.kwargs
        self.assertTrue(call["require_admin"])
        self.assertFalse(call["embed_iframe"])
        self.assertEqual(call["webcomponent_name"], "amit-monitor-panel")
        self.assertRegex(call["module_url"], r"^/api/amit/monitor.js\?v=[a-f0-9]{16}$")

    async def test_deferred_frontend_detects_already_loaded_plcs(self):
        await self.frontend.async_setup_frontend(self.hass)
        self.load_entry()
        await self.frontend_ready()
        self.panel_api.async_register_panel.assert_awaited_once()

    async def test_ready_frontend_adds_one_panel_for_multiple_entries(self):
        await self.frontend.async_setup_frontend(self.hass)
        await self.frontend_ready()
        self.panel_api.async_register_panel.assert_not_awaited()
        self.load_entry()
        self.load_entry("second")
        await asyncio.gather(*(self.frontend.async_update_panel(self.hass) for _ in range(3)))
        self.panel_api.async_register_panel.assert_awaited_once()
        self.hass.data["amit"].pop("first")
        await self.frontend.async_update_panel(self.hass)
        self.frontend_api.async_remove_panel.assert_not_called()
        self.hass.data["amit"].pop("second")
        await self.frontend.async_update_panel(self.hass)
        self.frontend_api.async_remove_panel.assert_called_once_with(self.hass, "amit-monitor")
        self.load_entry("third")
        await self.frontend.async_update_panel(self.hass)
        self.assertEqual(self.panel_api.async_register_panel.await_count, 2)
        self.hass.http.register_view.assert_called_once()

    async def test_registration_error_does_not_replace_existing_panel_or_break_plc(self):
        self.load_entry()
        self.panel_api.async_register_panel.side_effect = ValueError("Panel path already exists")
        await self.frontend.async_setup_frontend(self.hass)
        with self.assertLogs(self.frontend.__name__, level="ERROR"):
            await self.frontend_ready()
        self.assertIn("first", self.hass.data["amit"])
        self.hass.data["amit"].clear()
        await self.frontend.async_update_panel(self.hass)
        self.frontend_api.async_remove_panel.assert_not_called()

    async def test_missing_asset_does_not_register_a_broken_panel(self):
        self.load_entry()
        self.hass.async_add_executor_job.side_effect = FileNotFoundError("Missing packaged asset")
        await self.frontend.async_setup_frontend(self.hass)
        # HA's async_when_setup wrapper logs callback exceptions separately
        # from integration setup; the substitute deliberately propagates it.
        with self.assertRaises(FileNotFoundError):
            await self.frontend_ready()
        self.assertIn("first", self.hass.data["amit"])
        self.hass.http.register_view.assert_not_called()
        self.panel_api.async_register_panel.assert_not_awaited()
