"""The AMiT PLC integration."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import timedelta, datetime
from pathlib import Path
from typing import Any

import aiofiles

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
    DEFAULT_PORT,
    DEFAULT_STATION_ADDR,
    DEFAULT_CLIENT_ADDR,
    DEFAULT_PASSWORD,
    DEFAULT_SCAN_INTERVAL,
    SERVICE_WRITE_VARIABLE,
    SERVICE_RELOAD_VARIABLES,
    SERVICE_EXPORT_CONFIG,
    PLATFORMS,
)
from .protocol import AMiTClient, Variable, VarType

_LOGGER = logging.getLogger(__name__)


async def _apply_custom_names(hass: HomeAssistant, entry: ConfigEntry, custom_names: dict[str, str]) -> None:
    """Apply custom entity names from import."""
    _LOGGER.info(f"Applying custom names: {custom_names}")
    
    ent_reg = er.async_get(hass)
    
    # Get all entities for this config entry
    entity_entries = er.async_entries_for_config_entry(ent_reg, entry.entry_id)
    
    _LOGGER.info(f"Found {len(entity_entries)} entities for config entry")
    
    applied_count = 0
    for entity_entry in entity_entries:
        _LOGGER.debug(f"Entity: {entity_entry.entity_id}, unique_id: {entity_entry.unique_id}")
        
        # unique_id formats:
        # - sensor: {entry_id}_{wid}
        # - number: {entry_id}_{wid}_number
        # - switch: {entry_id}_{wid}_switch
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
        
        if wid and wid in custom_names:
            custom_name = custom_names[wid]
            _LOGGER.info(f"Applying custom name '{custom_name}' to {entity_entry.entity_id} (WID: {wid})")
            # Update entity name in registry
            ent_reg.async_update_entity(
                entity_entry.entity_id,
                name=custom_name
            )
            applied_count += 1
    
    if applied_count > 0:
        _LOGGER.info(f"Applied {applied_count} custom entity names from backup")
    else:
        _LOGGER.warning(f"No custom names were applied. Custom names keys: {list(custom_names.keys())}")
        
    # Remove custom_names from config entry data (no longer needed)
    new_data = dict(entry.data)
    new_data.pop(CONF_CUSTOM_NAMES, None)
    hass.config_entries.async_update_entry(entry, data=new_data)


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
    
    # Load all variables
    all_variables = await client.load_variables()
    
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
    
    # Apply custom names from import (if any)
    custom_names = entry.data.get(CONF_CUSTOM_NAMES, {})
    if custom_names:
        await _apply_custom_names(hass, entry, custom_names)
    
    # Register services
    async def handle_write_variable(call: ServiceCall) -> None:
        """Handle write_variable service call."""
        wid = call.data.get("wid")
        name = call.data.get("name")
        value = call.data["value"]
        
        if wid:
            variable = variables_by_wid.get(int(wid))
        elif name:
            variable = variables_by_name.get(name)
        else:
            _LOGGER.error("Either 'wid' or 'name' must be provided")
            return
        
        if variable is None:
            _LOGGER.error(f"Variable not found: wid={wid}, name={name}")
            return
        
        try:
            success = await client.write_variable(variable, value)
            if success:
                _LOGGER.info(f"Wrote {value} to {variable.name}")
                await coordinator.async_request_refresh()
            else:
                _LOGGER.error(f"Failed to write to {variable.name}")
        except Exception as e:
            _LOGGER.error(f"Error writing to {variable.name}: {e}")
    
    async def handle_reload_variables(call: ServiceCall) -> None:
        """Handle reload_variables service call."""
        all_vars = await client.load_variables()
        hass.data[DOMAIN][entry.entry_id]["all_variables"] = all_vars
        _LOGGER.info(f"Reloaded {len(all_vars)} variables from PLC")
    
    async def handle_export_config(call: ServiceCall) -> None:
        """Handle export_config service call - export selected variables with custom names."""
        filename = call.data.get("filename", "amit_config_export.json")
        
        # Get entity registry
        ent_reg = er.async_get(hass)
        
        # Build export data
        export_data = {
            "export_date": datetime.now().isoformat(),
            "plc_connection": {
                "host": entry.data[CONF_HOST],
                "port": entry.data.get(CONF_PORT, DEFAULT_PORT),
                "station_addr": entry.data.get(CONF_STATION_ADDR, DEFAULT_STATION_ADDR),
                "client_addr": entry.data.get(CONF_CLIENT_ADDR, DEFAULT_CLIENT_ADDR),
            },
            "scan_interval": entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            "monitored_variables": [],
            "writable_variables": [],
        }
        
        # Get all entities for this config entry
        entity_entries = er.async_entries_for_config_entry(ent_reg, entry.entry_id)
        
        # Create lookup: wid -> entity info (extract WID from unique_id)
        entity_info_by_wid = {}
        for entity_entry in entity_entries:
            # Extract WID from unique_id (it's the numeric part)
            parts = entity_entry.unique_id.split("_")
            wid = None
            for part in reversed(parts):
                if part.isdigit():
                    wid = int(part)
                    break
            
            if wid:
                entity_info_by_wid[wid] = {
                    "entity_id": entity_entry.entity_id,
                    "custom_name": entity_entry.name,  # None if not customized
                    "original_name": entity_entry.original_name,
                    "platform": entity_entry.platform,
                    "disabled": entity_entry.disabled,
                }
        
        writable_wids = hass.data[DOMAIN][entry.entry_id]["writable_wids"]
        
        # Process all selected variables
        for variable in variables:
            ent_info = entity_info_by_wid.get(variable.wid)
            
            var_export = {
                "wid": variable.wid,
                "plc_name": variable.name,
                "var_type": variable.var_type.value if hasattr(variable.var_type, 'value') else variable.var_type,
                "type_name": variable.type_name,
            }
            
            if ent_info:
                var_export["entity_id"] = ent_info["entity_id"]
                if ent_info["custom_name"]:
                    var_export["custom_name"] = ent_info["custom_name"]
                var_export["original_name"] = ent_info["original_name"]
                var_export["disabled"] = ent_info["disabled"]
            
            # Add to appropriate list
            if variable.wid in writable_wids:
                var_export["writable"] = True
                export_data["writable_variables"].append(var_export)
            else:
                export_data["monitored_variables"].append(var_export)
        
        # Write to file in www folder for download access
        www_dir = Path(hass.config.config_dir) / "www" / "amit"
        www_dir.mkdir(parents=True, exist_ok=True)
        
        filename = call.data.get("filename", f"amit_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        export_path = www_dir / filename
        
        try:
            async with aiofiles.open(export_path, "w", encoding="utf-8") as f:
                await f.write(json.dumps(export_data, indent=2, ensure_ascii=False))
            
            _LOGGER.info(f"Exported AMiT config to {export_path}")
            _LOGGER.info(f"  - {len(export_data['monitored_variables'])} monitored variables")
            _LOGGER.info(f"  - {len(export_data['writable_variables'])} writable variables")
            
            # Create persistent notification with download link
            download_url = f"/local/amit/{filename}"
            await hass.services.async_call(
                "persistent_notification",
                "create",
                {
                    "title": "AMiT Export Complete",
                    "message": f"Configuration exported successfully!\n\n"
                              f"- {len(export_data['monitored_variables'])} monitored variables\n"
                              f"- {len(export_data['writable_variables'])} writable variables\n\n"
                              f"**[⬇️ Download {filename}]({download_url})**",
                    "notification_id": "amit_export",
                },
            )
        except Exception as e:
            _LOGGER.error(f"Failed to export config: {e}")
            raise
    
    hass.services.async_register(
        DOMAIN, SERVICE_WRITE_VARIABLE, handle_write_variable
    )
    hass.services.async_register(
        DOMAIN, SERVICE_RELOAD_VARIABLES, handle_reload_variables
    )
    hass.services.async_register(
        DOMAIN, SERVICE_EXPORT_CONFIG, handle_export_config
    )
    
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        data = hass.data[DOMAIN].pop(entry.entry_id)
        await data["client"].disconnect()
    
    return unload_ok
