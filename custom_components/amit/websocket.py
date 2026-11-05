"""Authenticated live monitor commands. No PLC writes or stored history."""
from __future__ import annotations

import asyncio
from hashlib import sha256
import hmac
import json
from secrets import token_bytes, token_hex
from time import time

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er

from .const import CONF_VARIABLES, DOMAIN, MONITOR_ADDITIONS
from .config_flow import preview_variable_addition
from .frontend import async_update_panel

_PREVIEW_KEY = "amit_monitor_preview_key"
_PREVIEW_SECONDS = 300


def _preview_signature(hass, connection, entry, data, snapshot, preview) -> str:
    """Bind an opaque preview to its user and current configuration, not samples."""
    key = hass.data.get(_PREVIEW_KEY)
    if key is None:
        key = hass.data[_PREVIEW_KEY] = token_bytes(32)
    payload = {
        "user_id": connection.user.id, "entry_id": preview["entry_id"],
        "data": dict(entry.data), "options": dict(getattr(entry, "options", {})),
        "catalog": snapshot["variables"],
        "definitions": [(v.wid, v.name, int(v.var_type), v.writable) for v in data["all_variables"]],
        "monitored": [v.wid for v in data["variables"]],
        "writable": sorted(data["writable_wids"]),
        "preview": {key: value for key, value in preview.items() if key != "preview_id"},
    }
    content = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hmac.new(key, content, sha256).hexdigest()


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
    websocket_api.async_register_command(hass, websocket_preview_add)
    websocket_api.async_register_command(hass, websocket_confirm_add)
    websocket_api.async_register_command(hass, websocket_addition_status)
    websocket_api.async_register_command(hass, websocket_matrix_read)


@websocket_api.websocket_command({
    vol.Required("type"): "amit/monitor/read_matrix",
    vol.Required("entry_id"): str,
    vol.Required("runtime_id"): str,
    vol.Required("wid"): int,
    vol.Required("revision"): int,
    vol.Required("row"): int,
    vol.Required("col"): int,
    vol.Required("rows"): int,
    vol.Required("cols"): int,
})
@websocket_api.require_admin
@callback
def websocket_matrix_read(hass, connection, msg) -> None:
    """Read one catalog matrix window without changing configuration or polling."""
    data = hass.data.get(DOMAIN, {}).get(msg["entry_id"], {})
    monitor = data.get("monitor")
    if monitor is None or monitor.closed:
        connection.send_error(msg["id"], "not_found", "Requested PLC is not loaded")
        return
    # HA calls subscription cleanup when the socket closes. Register this
    # temporary cancellation hook only for the duration of the one-shot read.
    task = None
    active = True

    @callback
    def cancel():
        nonlocal active
        active = False
        if task is not None:
            task.cancel()

    connection.subscriptions[msg["id"]] = cancel

    async def read():
        try:
            result = await monitor.read_matrix(
                msg["runtime_id"], msg["wid"], msg["revision"],
                msg["row"], msg["col"], msg["rows"], msg["cols"],
            )
        except asyncio.CancelledError:
            if monitor.closed and active:
                connection.send_error(msg["id"], "not_found", "Requested PLC was unloaded")
            elif active:
                raise
        except ValueError as err:
            connection.send_error(msg["id"], str(err), "Cannot read this matrix window")
        except (OSError, RuntimeError):
            connection.send_error(msg["id"], "read_error", "PLC matrix read failed")
        else:
            connection.send_result(msg["id"], result)
        finally:
            if connection.subscriptions.get(msg["id"]) is cancel:
                connection.subscriptions.pop(msg["id"])

    # Install cleanup before scheduling, including on HA versions whose tasks
    # start on the next event-loop turn rather than eagerly.
    coroutine = read()
    try:
        task = hass.async_create_background_task(coroutine, "AMiT matrix read")
    except Exception:
        coroutine.close()
        connection.subscriptions.pop(msg["id"], None)
        connection.send_error(msg["id"], "read_error", "Cannot schedule matrix read")


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
            item = {"entry_id": entry_id, "title": entry.title if entry else "AMiT PLC"}
            if identification := data.get("identification"):
                item["identification"] = identification
            entries.append(item)
    connection.send_result(msg["id"], entries)


@websocket_api.websocket_command({
    vol.Required("type"): "amit/monitor/preview_add",
    vol.Required("entry_id"): str,
    vol.Required("runtime_id"): str,
    vol.Required("variables"): [{vol.Required("wid"): int, vol.Required("revision"): int}],
})
@websocket_api.require_admin
@callback
def websocket_preview_add(hass, connection, msg) -> None:
    """Preview permanent additions. No configuration, reload, or PLC requests."""
    try:
        _, _, result = _addition_preview(hass, connection, msg, int(time()) + _PREVIEW_SECONDS)
    except ValueError as err:
        connection.send_error(msg["id"], str(err), "Cannot prepare this selection")
        return
    connection.send_result(msg["id"], result)


@callback
def _addition_preview(hass, connection, msg, expires_at):
    """Rebuild the same proposal for preview and atomic confirmation."""
    data = hass.data.get(DOMAIN, {}).get(msg["entry_id"], {})
    monitor = data.get("monitor")
    entry = hass.config_entries.async_get_entry(msg["entry_id"])
    if monitor is None or monitor.closed or entry is None:
        raise ValueError("not_found")
    snapshot = monitor.snapshot()
    if msg["runtime_id"] != snapshot["runtime_id"]:
        raise ValueError("stale_selection")
    requested = msg["variables"]
    if not isinstance(requested, list) or not requested or len(requested) > 65536:
        raise ValueError("invalid_selection")
    catalog = {v["wid"]: v for v in snapshot["variables"]}
    for item in requested:
        if (not isinstance(item, dict) or type(item.get("wid")) is not int
                or type(item.get("revision")) is not int or item["wid"] not in catalog):
            raise ValueError("invalid_selection")
        if item["revision"] != catalog[item["wid"]]["revision"]:
            raise ValueError("stale_selection")
    try:
        proposal = preview_variable_addition(
            dict(entry.data), data["all_variables"], [v["wid"] for v in requested],
            data["variables"], data["writable_wids"],
        )
    except (ValueError, TypeError) as err:
        code = "invalid_selection" if str(err) == "invalid_selection" else "invalid_configuration"
        raise ValueError(code) from err
    metadata = _entity_metadata(hass, er.async_get(hass), msg["entry_id"], snapshot["variables"])
    overview = set(proposal["requested_wids"]) | set(proposal["newly_monitored_wids"])
    missing = [wid for wid in proposal["requested_wids"] if not metadata[wid]["entities"]]
    result = {
        **proposal, "entry_id": msg["entry_id"], "runtime_id": monitor.runtime_id,
        "expires_at": expires_at,
        "missing_entity_wids": missing,
        "requires_reload": bool(proposal["added_wids"] or proposal["newly_monitored_wids"]
                                or proposal["removed_write_wids"] or missing),
        "variables": [dict(v, **metadata[v["wid"]]) for v in snapshot["variables"] if v["wid"] in overview],
    }
    result["preview_id"] = _preview_signature(hass, connection, entry, data, snapshot, result)
    return entry, data, result


def _configuration_signature(entry):
    return sha256(json.dumps(
        [dict(entry.data), dict(getattr(entry, "options", {}))],
        sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode()).hexdigest()


def _addition_result(operation):
    return {key: value for key, value in operation.items() if not key.startswith("_")}


@callback
def _refresh_addition_status(hass, operation):
    """A retryable setup can finish after the reload coroutine returns."""
    if operation["status"] not in ("pending", "loaded"):
        return
    entry = hass.config_entries.async_get_entry(operation["entry_id"])
    if entry is None or _configuration_signature(entry) != operation["_configuration"]:
        operation.update(status="failed", error="configuration_changed")
        return
    if entry.state in (ConfigEntryState.SETUP_RETRY, ConfigEntryState.SETUP_IN_PROGRESS):
        operation.update(status="pending", error=None)
        return
    if entry.state != ConfigEntryState.LOADED:
        operation.update(status="failed", error="reload_failed")
        return
    monitor = hass.data.get(DOMAIN, {}).get(operation["entry_id"], {}).get("monitor")
    if monitor is not None and not monitor.closed and monitor.runtime_id != operation["_runtime_id"]:
        operation.update(status="loaded", error=None)


async def _async_reload_addition(hass, operation):
    """Finish a saved change independently of the browser connection."""
    operation["status"] = "reloading"
    try:
        entry = hass.config_entries.async_get_entry(operation["entry_id"])
        if entry is None or _configuration_signature(entry) != operation["_configuration"]:
            operation.update(status="failed", error="configuration_changed")
            return
        reloaded = await hass.config_entries.async_reload(operation["entry_id"])
        entry = hass.config_entries.async_get_entry(operation["entry_id"])
        retrying = entry is not None and getattr(entry, "state", None) == ConfigEntryState.SETUP_RETRY
        operation.update(status="pending" if reloaded or retrying else "failed",
                         error=None if reloaded or retrying else "reload_failed")
        _refresh_addition_status(hass, operation)
    except asyncio.CancelledError:
        operation.update(status="failed", error="reload_cancelled")
        raise
    except Exception:
        operation.update(status="failed", error="reload_failed")
    finally:
        await async_update_panel(hass)


@websocket_api.websocket_command({
    vol.Required("type"): "amit/monitor/confirm_add",
    vol.Required("entry_id"): str,
    vol.Required("runtime_id"): str,
    vol.Required("variables"): [{vol.Required("wid"): int, vol.Required("revision"): int}],
    vol.Required("expires_at"): int,
    vol.Required("preview_id"): str,
})
@websocket_api.require_admin
@callback
def websocket_confirm_add(hass, connection, msg) -> None:
    """Validate and save in one event-loop turn, then reload only this entry."""
    operations = hass.data.setdefault(MONITOR_ADDITIONS, {})
    previous = operations.get(msg["entry_id"])
    if previous and previous["status"] in ("saved", "reloading"):
        connection.send_error(msg["id"], "busy", "A saved addition is still loading")
        return
    expires_at = msg["expires_at"]
    if type(expires_at) is not int or not time() < expires_at <= time() + _PREVIEW_SECONDS:
        connection.send_error(msg["id"], "expired_preview", "Prepare a new preview")
        return
    try:
        entry, _, preview = _addition_preview(hass, connection, msg, expires_at)
    except ValueError as err:
        connection.send_error(msg["id"], str(err), "Prepare a new preview")
        return
    if not isinstance(msg["preview_id"], str) or not hmac.compare_digest(
            msg["preview_id"].encode(), preview["preview_id"].encode()):
        connection.send_error(msg["id"], "stale_preview", "Prepare a new preview")
        return
    if not preview["requires_reload"]:
        connection.send_result(msg["id"], {"entry_id": msg["entry_id"], "status": "unchanged", "saved": False})
        return
    new_data = {**entry.data, **preview["config_patch"]}
    try:
        hass.config_entries.async_update_entry(entry, data=new_data)
    except Exception:
        connection.send_error(msg["id"], "save_failed", "Configuration was not saved")
        return
    operation = {
        "entry_id": msg["entry_id"], "operation_id": token_hex(16),
        "status": "saved", "saved": True, "error": None,
        "_user_id": connection.user.id, "_runtime_id": msg["runtime_id"],
        "_configuration": _configuration_signature(entry),
    }
    operations[msg["entry_id"]] = operation
    reload_task = _async_reload_addition(hass, operation)
    try:
        hass.async_create_background_task(reload_task, "AMiT entity addition")
    except Exception:
        reload_task.close()
        operation.update(status="failed", error="reload_failed")
    connection.send_result(msg["id"], _addition_result(operation))


@websocket_api.websocket_command({
    vol.Required("type"): "amit/monitor/addition_status",
    vol.Required("entry_id"): str,
    vol.Required("operation_id"): str,
})
@websocket_api.require_admin
@callback
def websocket_addition_status(hass, connection, msg) -> None:
    """Read a saved operation after reload or browser reconnection."""
    operation = hass.data.get(MONITOR_ADDITIONS, {}).get(msg["entry_id"])
    if (operation is None or operation["operation_id"] != msg["operation_id"]
            or operation["_user_id"] != connection.user.id):
        connection.send_error(msg["id"], "not_found", "Requested operation was not found")
        return
    _refresh_addition_status(hass, operation)
    connection.send_result(msg["id"], _addition_result(operation))


@websocket_api.websocket_command({
    vol.Required("type"): "amit/monitor/subscribe",
    vol.Required("entry_id"): str,
    vol.Optional("interval"): object,
    vol.Optional("wids"): object,
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
    ready = False

    def enrich(event):
        return dict(event, variables=[dict(v, **metadata[v["wid"]]) for v in variables])

    @callback
    def forward(event: dict) -> None:
        nonlocal variables, metadata
        if not active or not ready:
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
        unsubscribe_monitor = monitor.subscribe(
            forward, interval=msg.get("interval"), wids=msg.get("wids"))
    except ValueError as err:
        unsubscribe_registry()
        connection.send_error(msg["id"], "invalid_request", str(err))
        return
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
        snapshot = monitor.snapshot()
        connection.send_result(msg["id"])
        connection.send_event(msg["id"], enrich(snapshot))
        ready = True
    except Exception:
        connection.subscriptions.pop(msg["id"], None)
        unsubscribe()
        raise
