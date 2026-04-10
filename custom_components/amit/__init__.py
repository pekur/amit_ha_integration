"""The AMiT PLC integration."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers import entity_registry as er

from .const import (
    DOMAIN,
    CONF_HOST,
    CONF_PORT,
    CONF_STATION_ADDR,
    CONF_CLIENT_ADDR,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_VARIABLES,
    CONF_WRITABLE_VARIABLES,
    CONF_CUSTOM_NAMES,
    CONF_CUSTOM_ENTITY_IDS,
    CONF_TARGET,
    DEFAULT_PORT,
    DEFAULT_STATION_ADDR,
    DEFAULT_CLIENT_ADDR,
    DEFAULT_PASSWORD,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TARGET,
    SERVICE_WRITE_VARIABLE,
    SERVICE_RELOAD_VARIABLES,
    PLATFORMS,
)
from .targets import get_target
from .protocol import AMiTClient, Variable, VarType

_LOGGER = logging.getLogger(__name__)


async def _apply_custom_names_and_ids(
    hass: HomeAssistant, 
    entry: ConfigEntry, 
    custom_names: dict[str, str],
    custom_entity_ids: dict[str, str]
) -> None:
    """Apply custom entity names and entity_ids from import."""
    _LOGGER.info(f"Applying custom names: {len(custom_names)}, custom entity_ids: {len(custom_entity_ids)}")
    
    ent_reg = er.async_get(hass)
    
    # Get all entities for this config entry
    entity_entries = er.async_entries_for_config_entry(ent_reg, entry.entry_id)
    
    _LOGGER.info(f"Found {len(entity_entries)} entities for config entry")
    
    applied_names = 0
    applied_ids = 0
    
    for entity_entry in entity_entries:
        _LOGGER.debug(f"Entity: {entity_entry.entity_id}, unique_id: {entity_entry.unique_id}")
        
        # unique_id formats:
        # - sensor: {entry_id}_{wid}
        # - number: {entry_id}_{wid}_number
        # - switch: {entry_id}_{wid}_switch
        # - binary_sensor: {entry_id}_{wid}_binary
        # - button: {entry_id}_export_config, {entry_id}_reload_variables
        
        if "_" not in entity_entry.unique_id:
            continue
            
        parts = entity_entry.unique_id.split("_")
        
        # Try to extract WID - it's a numeric part
        wid = None
        for part in reversed(parts):
            if part.isdigit():
                wid = part
                break
        
        if not wid:
            continue
        
        # Prepare update kwargs
        update_kwargs = {}
        
        # Apply custom name if available
        if wid in custom_names:
            custom_name = custom_names[wid]
            _LOGGER.info(f"Will apply custom name '{custom_name}' to {entity_entry.entity_id} (WID: {wid})")
            update_kwargs["name"] = custom_name
            applied_names += 1
        
        # Apply custom entity_id if available
        if wid in custom_entity_ids:
            desired_entity_id = custom_entity_ids[wid]
            current_entity_id = entity_entry.entity_id
            
            # Extract just the object_id part (after the domain.)
            # e.g., "sensor.bs_teplota_tuv" -> we need to match domain
            if "." in desired_entity_id:
                desired_domain, desired_object_id = desired_entity_id.split(".", 1)
                current_domain = current_entity_id.split(".")[0]
                
                # Only change if domains match (sensor -> sensor, etc.)
                if desired_domain == current_domain and current_entity_id != desired_entity_id:
                    # Check if desired entity_id is available
                    existing = ent_reg.async_get(desired_entity_id)
                    if existing is None:
                        _LOGGER.info(f"Will change entity_id from '{current_entity_id}' to '{desired_entity_id}' (WID: {wid})")
                        update_kwargs["new_entity_id"] = desired_entity_id
                        applied_ids += 1
                    else:
                        _LOGGER.warning(f"Cannot change entity_id to '{desired_entity_id}' - already exists")
        
        # Apply updates if any
        if update_kwargs:
            try:
                ent_reg.async_update_entity(entity_entry.entity_id, **update_kwargs)
            except Exception as e:
                _LOGGER.error(f"Failed to update entity {entity_entry.entity_id}: {e}")
    
    if applied_names > 0:
        _LOGGER.info(f"Applied {applied_names} custom entity names from backup")
    if applied_ids > 0:
        _LOGGER.info(f"Applied {applied_ids} custom entity IDs from backup")
        
    if applied_names == 0 and applied_ids == 0:
        _LOGGER.warning(f"No custom names or IDs were applied. Names keys: {list(custom_names.keys())}, IDs keys: {list(custom_entity_ids.keys())}")
        
    # Remove custom_names and custom_entity_ids from config entry data (no longer needed)
    new_data = dict(entry.data)
    new_data.pop(CONF_CUSTOM_NAMES, None)
    new_data.pop(CONF_CUSTOM_ENTITY_IDS, None)
    hass.config_entries.async_update_entry(entry, data=new_data)


# Keep backward compatibility with old function name
async def _apply_custom_names(hass: HomeAssistant, entry: ConfigEntry, custom_names: dict[str, str]) -> None:
    """Apply custom entity names from import (backward compatibility)."""
    await _apply_custom_names_and_ids(hass, entry, custom_names, {})


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up AMiT from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    
    # Create client
    client = AMiTClient(
        host=entry.data[CONF_HOST],
        port=entry.data.get(CONF_PORT, DEFAULT_PORT),
        station_addr=entry.data.get(CONF_STATION_ADDR, DEFAULT_STATION_ADDR),
        client_addr=entry.data.get(CONF_CLIENT_ADDR, DEFAULT_CLIENT_ADDR),
        password=entry.data.get(CONF_PASSWORD, DEFAULT_PASSWORD),
    )
    
    await client.connect()
    
    # Resolve target profile for this config entry
    target = get_target(entry.data.get(CONF_TARGET, DEFAULT_TARGET))

    # Load all variables
    all_variables = await client.load_variables(
        is_readonly_fn=target.is_readonly_fn,
        wid_min=target.wid_min,
        wid_max=target.wid_max,
    )
    
    # Filter to selected variables
    selected_wids = set(int(w) for w in entry.data.get(CONF_VARIABLES, []))
    if selected_wids:
        variables = [v for v in all_variables if v.wid in selected_wids]
    else:
        # If none selected, use all readable
        variables = [v for v in all_variables if v.is_readable()]
    
    # Create variable lookup
    variables_by_wid = {v.wid: v for v in variables}
    variables_by_name = {v.name: v for v in variables}
    
    async def async_update_data() -> dict[int, Any]:
        """Fetch data from PLC."""
        try:
            data = {}
            for variable in variables:
                if variable.is_readable():
                    try:
                        value = await client.read_variable(variable)
                        variable.value = value
                        data[variable.wid] = value
                    except Exception as e:
                        _LOGGER.warning(f"Failed to read {variable.name}: {e}")
                        data[variable.wid] = None
                await asyncio.sleep(0.02)  # Small delay between reads
            return data
        except Exception as e:
            raise UpdateFailed(f"Error communicating with PLC: {e}")
    
    # Create coordinator
    scan_interval = entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DOMAIN,
        update_method=async_update_data,
        update_interval=timedelta(seconds=scan_interval),
    )
    
    # Fetch initial data
    await coordinator.async_config_entry_first_refresh()
    
    # Store data
    hass.data[DOMAIN][entry.entry_id] = {
        "client": client,
        "coordinator": coordinator,
        "variables": variables,
        "variables_by_wid": variables_by_wid,
        "variables_by_name": variables_by_name,
        "all_variables": all_variables,
        "writable_wids": set(int(w) for w in entry.data.get(CONF_WRITABLE_VARIABLES, [])),
    }
    
    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    # Apply custom names and entity_ids from import (if any)
    custom_names = entry.data.get(CONF_CUSTOM_NAMES, {})
    custom_entity_ids = entry.data.get(CONF_CUSTOM_ENTITY_IDS, {})
    if custom_names or custom_entity_ids:
        await _apply_custom_names_and_ids(hass, entry, custom_names, custom_entity_ids)
    
    # Register services only once (guard against multiple entries)
    if not hass.services.has_service(DOMAIN, SERVICE_WRITE_VARIABLE):

        async def handle_write_variable(call: ServiceCall) -> None:
            """Handle write_variable service call."""
            entry_id = call.data.get("entry_id")
            if entry_id and entry_id in hass.data[DOMAIN]:
                entry_data = hass.data[DOMAIN][entry_id]
            elif len(hass.data[DOMAIN]) == 1:
                entry_data = next(iter(hass.data[DOMAIN].values()))
            else:
                _LOGGER.error(
                    "Multiple PLCs configured — specify entry_id in service call"
                )
                return

            _client = entry_data["client"]
            _variables_by_wid = entry_data["variables_by_wid"]
            _variables_by_name = entry_data["variables_by_name"]
            _coordinator = entry_data["coordinator"]

            wid = call.data.get("wid")
            name = call.data.get("name")
            value = call.data["value"]

            if wid:
                variable = _variables_by_wid.get(int(wid))
            elif name:
                variable = _variables_by_name.get(name)
            else:
                _LOGGER.error("Either 'wid' or 'name' must be provided")
                return

            if variable is None:
                _LOGGER.error("Variable not found: wid=%s, name=%s", wid, name)
                return

            try:
                if variable.var_type == VarType.FLOAT:
                    value = float(value)
                elif variable.var_type in (VarType.INT16, VarType.INT32):
                    value = int(value)
            except (ValueError, TypeError):
                _LOGGER.error(
                    "Invalid value type for %s (%s): %s",
                    variable.name, variable.type_name, value,
                )
                return

            try:
                success = await _client.write_variable(variable, value)
                if success:
                    _LOGGER.info("Wrote %s to %s", value, variable.name)
                    await _coordinator.async_request_refresh()
                else:
                    _LOGGER.error("Failed to write to %s", variable.name)
            except Exception as e:
                _LOGGER.error("Error writing to %s: %s", variable.name, e)

        async def handle_reload_variables(call: ServiceCall) -> None:
            """Handle reload_variables service call."""
            for eid, entry_data in hass.data[DOMAIN].items():
                _client = entry_data["client"]
                _entry = hass.config_entries.async_get_entry(eid)
                _target = get_target(
                    _entry.data.get(CONF_TARGET, DEFAULT_TARGET) if _entry else DEFAULT_TARGET
                )
                all_vars = await _client.load_variables(
                    is_readonly_fn=_target.is_readonly_fn,
                    wid_min=_target.wid_min,
                    wid_max=_target.wid_max,
                )
                entry_data["all_variables"] = all_vars
                _LOGGER.info("Reloaded %d variables from PLC (entry %s)", len(all_vars), eid)

        hass.services.async_register(DOMAIN, SERVICE_WRITE_VARIABLE, handle_write_variable)
        hass.services.async_register(DOMAIN, SERVICE_RELOAD_VARIABLES, handle_reload_variables)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        data = hass.data[DOMAIN].pop(entry.entry_id)
        await data["client"].disconnect()

    # Unregister services when the last entry is removed
    if not hass.data[DOMAIN]:
        hass.services.async_remove(DOMAIN, SERVICE_WRITE_VARIABLE)
        hass.services.async_remove(DOMAIN, SERVICE_RELOAD_VARIABLES)

    return unload_ok
