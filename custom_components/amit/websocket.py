"""Authenticated live monitor commands. No PLC writes or stored history."""
from __future__ import annotations

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN


@callback
def async_register_commands(hass: HomeAssistant) -> None:
    """Register once during integration setup, independently of PLC entries."""
    websocket_api.async_register_command(hass, websocket_list)
    websocket_api.async_register_command(hass, websocket_subscribe)


@websocket_api.websocket_command({vol.Required("type"): "amit/monitor/list"})
@websocket_api.require_admin
@callback
def websocket_list(hass, connection, msg) -> None:
    """List loaded PLCs without connection settings or credentials."""
    entries = []
    for entry_id, data in hass.data.get(DOMAIN, {}).items():
        monitor = data.get("monitor")
        if monitor is not None and not monitor.closed:
            entry = hass.config_entries.async_get_entry(entry_id)
            entries.append({"entry_id": entry_id,
                            "title": entry.title if entry else "AMiT PLC"})
    connection.send_result(msg["id"], entries)


@websocket_api.websocket_command({
    vol.Required("type"): "amit/monitor/subscribe",
    vol.Required("entry_id"): str,
})
@websocket_api.require_admin
@callback
def websocket_subscribe(hass, connection, msg) -> None:
    """Send a snapshot, then new reads until unsubscribe or connection close."""
    data = hass.data.get(DOMAIN, {}).get(msg["entry_id"], {})
    monitor = data.get("monitor")
    if monitor is None or monitor.closed:
        connection.send_error(msg["id"], "not_found", "Requested PLC is not loaded")
        return

    @callback
    def forward(event: dict) -> None:
        connection.send_event(msg["id"], event)
        if event["kind"] == "unavailable":
            unsubscribe = connection.subscriptions.pop(msg["id"], None)
            if unsubscribe is not None:
                unsubscribe()

    # No await: snapshot, registration and acknowledgement are atomic in HA's loop.
    snapshot = monitor.snapshot()
    connection.subscriptions[msg["id"]] = monitor.subscribe(forward)
    connection.send_result(msg["id"])
    connection.send_event(msg["id"], snapshot)
