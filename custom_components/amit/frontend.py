"""Optional monitor panel and its public, code-only JavaScript resource."""
from __future__ import annotations

import asyncio
from hashlib import sha256
import logging
from pathlib import Path

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)
_DATA = "amit_frontend"
_PANEL = "amit-monitor"
_RESOURCE = "/api/amit/monitor.js"


async def async_setup_frontend(hass) -> None:
    """Wait for the frontend without enabling it on headless installations."""
    from homeassistant.setup import async_when_setup

    if _DATA in hass.data:
        return
    hass.data[_DATA] = {"ready": False, "registered": False, "lock": asyncio.Lock()}

    async def register_resources(hass, component) -> None:
        from aiohttp import web
        from homeassistant.components.http import HomeAssistantView

        # Preload only packaged code, outside HA's event loop. PLC data is sent
        # exclusively by the administrator-only WebSocket commands.
        content = await hass.async_add_executor_job(
            (Path(__file__).parent / "frontend" / "monitor.js").read_bytes
        )

        class MonitorResource(HomeAssistantView):
            url = _RESOURCE
            name = "api:amit:monitor"
            requires_auth = False

            async def get(self, request):
                return web.Response(
                    body=content, content_type="application/javascript",
                    headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
                )

        hass.http.register_view(MonitorResource())
        state = hass.data[_DATA]
        state["module_url"] = f"{_RESOURCE}?v={sha256(content).hexdigest()[:16]}"
        state["ready"] = True
        await async_update_panel(hass)

    async_when_setup(hass, "frontend", register_resources)


async def async_update_panel(hass) -> None:
    """Show one panel for loaded PLCs; remove it after the last unload."""
    state = hass.data.get(_DATA)
    if state is None or not state["ready"]:
        return
    from homeassistant.components import frontend, panel_custom

    async with state["lock"]:
        loaded = any(
            data.get("monitor") is not None and not data["monitor"].closed
            for data in hass.data.get(DOMAIN, {}).values()
        )
        try:
            if loaded and not state["registered"]:
                await panel_custom.async_register_panel(
                    hass=hass, frontend_url_path=_PANEL,
                    webcomponent_name="amit-monitor-panel", sidebar_title="AMiT Monitor",
                    sidebar_icon="mdi:chart-timeline-variant", module_url=state["module_url"],
                    embed_iframe=False, require_admin=True,
                )
                state["registered"] = True
            elif not loaded and state["registered"]:
                frontend.async_remove_panel(hass, _PANEL)
                state["registered"] = False
        except Exception:
            # A failed optional panel must not prevent PLC setup or cleanup.
            _LOGGER.exception("Unable to update the AMiT monitor panel")
