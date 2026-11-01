"""Authenticated live monitor commands. No PLC writes or stored history."""
from __future__ import annotations

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er

from .const import CONF_VARIABLES, DOMAIN


def _entity_metadata(hass, registry, entry_id, variables) -> dict:
    """Match exact entity identities within this PLC, never display names."""
    entry = hass.config_entries.async_get_entry(entry_id)
    selected = {int(wid) for wid in entry.data.get(CONF_VARIABLES, [])} if entry else set()
    metadata = {
        v["wid"]: {"wid": v["wid"], "configured": bool(entry) and (
            v["wid"] in selected if selected else v["readable"]), "entities": []}
        for v in variables
    }
    identities = {
        (domain, f"{entry_id}_{v['wid']}{suffix}"): v
        for v in variables
        for domain, suffix in (("sensor", ""), ("number", "_number"),
                               ("switch", "_switch"), ("binary_sensor", "_binary"))
    }
    for entity in er.async_entries_for_config_entry(registry, entry_id):
        if entity.platform != DOMAIN or entity.config_entry_id != entry_id:
            continue
        variable = identities.get((entity.entity_id.partition(".")[0], entity.unique_id))
        if variable is None:
            continue
        metadata[variable["wid"]]["entities"].append({
            "entity_id": entity.entity_id,
            "name": entity.name or entity.original_name or variable["name"],
            "custom_name": entity.name,
            "disabled": entity.disabled_by is not None,
        })
    for item in metadata.values():
        item["entities"].sort(key=lambda entity: entity["entity_id"])
    return metadata


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

    registry = er.async_get(hass)
    snapshot = monitor.snapshot()
    variables = snapshot["variables"]
    metadata = _entity_metadata(hass, registry, msg["entry_id"], variables)
    active = True

    def enrich(event):
        return dict(event, variables=[dict(v, **metadata[v["wid"]]) for v in variables])

    @callback
    def forward(event: dict) -> None:
        nonlocal variables, metadata
        if not active:
            return
        if event["kind"] == "catalog":
            variables = event["variables"]
            metadata = _entity_metadata(hass, registry, msg["entry_id"], variables)
            event = enrich(event)
        try:
            connection.send_event(msg["id"], event)
        finally:
            if event["kind"] == "unavailable":
                cleanup = connection.subscriptions.pop(msg["id"], None)
                if cleanup is not None:
                    cleanup()

    @callback
    def registry_updated(event) -> None:
        nonlocal metadata
        if not active:
            return
        entity_id = event.data["entity_id"]
        entity = registry.async_get(entity_id)
        known_ids = {e["entity_id"] for item in metadata.values() for e in item["entities"]}
        if not (entity_id in known_ids or event.data.get("old_entity_id") in known_ids
                or (entity is not None and entity.platform == DOMAIN
                    and entity.config_entry_id == msg["entry_id"])):
            return
        updated = _entity_metadata(hass, registry, msg["entry_id"], variables)
        changes = [item for wid, item in updated.items() if item != metadata[wid]]
        metadata = updated
        if changes:
            connection.send_event(msg["id"], {"kind": "entity_metadata",
                                  "runtime_id": monitor.runtime_id, "variables": changes})

    unsubscribe_registry = hass.bus.async_listen(er.EVENT_ENTITY_REGISTRY_UPDATED, registry_updated)
    try:
        unsubscribe_monitor = monitor.subscribe(forward)
    except Exception:
        unsubscribe_registry()
        raise

    @callback
    def unsubscribe() -> None:
        nonlocal active
        if active:
            active = False
            unsubscribe_registry()
            unsubscribe_monitor()

    # No await: snapshot, registration and acknowledgement are atomic in HA's loop.
    connection.subscriptions[msg["id"]] = unsubscribe
    try:
        connection.send_result(msg["id"])
        connection.send_event(msg["id"], enrich(snapshot))
    except Exception:
        connection.subscriptions.pop(msg["id"], None)
        unsubscribe()
        raise
