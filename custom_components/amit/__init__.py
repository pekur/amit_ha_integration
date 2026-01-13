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

from .const import (
    DOMAIN,
    CONF_HOST,
    CONF_PORT,
    CONF_STATION_ADDR,
    CONF_CLIENT_ADDR,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_VARIABLES,
    DEFAULT_PORT,
    DEFAULT_STATION_ADDR,
    DEFAULT_CLIENT_ADDR,
    DEFAULT_PASSWORD,
    DEFAULT_SCAN_INTERVAL,
    SERVICE_WRITE_VARIABLE,
    SERVICE_RELOAD_VARIABLES,
    PLATFORMS,
)
from .protocol import AMiTClient, Variable, VarType

_LOGGER = logging.getLogger(__name__)


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
    }
    
    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
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
    
    hass.services.async_register(
        DOMAIN, SERVICE_WRITE_VARIABLE, handle_write_variable
    )
    hass.services.async_register(
        DOMAIN, SERVICE_RELOAD_VARIABLES, handle_reload_variables
    )
    
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        data = hass.data[DOMAIN].pop(entry.entry_id)
        await data["client"].disconnect()
    
    return unload_ok
