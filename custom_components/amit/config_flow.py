"""Config flow for AMiT integration."""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import selector

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
    DEFAULT_PORT,
    DEFAULT_STATION_ADDR,
    DEFAULT_CLIENT_ADDR,
    DEFAULT_PASSWORD,
    DEFAULT_SCAN_INTERVAL,
)
from .protocol import AMiTClient

_LOGGER = logging.getLogger(__name__)


async def validate_connection(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect."""
    _LOGGER.info(f"Validating connection to {data[CONF_HOST]}:{data.get(CONF_PORT, DEFAULT_PORT)}")
    
    client = AMiTClient(
        host=data[CONF_HOST],
        port=data.get(CONF_PORT, DEFAULT_PORT),
        station_addr=data.get(CONF_STATION_ADDR, DEFAULT_STATION_ADDR),
        client_addr=data.get(CONF_CLIENT_ADDR, DEFAULT_CLIENT_ADDR),
        password=data.get(CONF_PASSWORD, DEFAULT_PASSWORD),
        timeout=5.0,
    )
    
    variables = []
    
    try:
        _LOGGER.debug("Creating connection...")
        connected = await client.connect()
        if not connected:
            raise CannotConnect("Failed to create connection")
        
        _LOGGER.debug("Connection established, testing...")
        
        if not await client.test_connection():
            raise CannotConnect("Connection test failed - no response from PLC")
        
        _LOGGER.info("Connection test passed, loading variables...")
        
        variables = await client.load_variables()
        
        _LOGGER.info(f"Successfully loaded {len(variables)} variables from PLC")
        
    except asyncio.TimeoutError as e:
        _LOGGER.error(f"Timeout connecting to PLC: {e}")
        raise CannotConnect("Timeout connecting to PLC")
    except TimeoutError as e:
        _LOGGER.error(f"Timeout: {e}")
        raise CannotConnect(f"Timeout: {e}")
    except OSError as e:
        _LOGGER.error(f"Network error: {e}")
        raise CannotConnect(f"Network error: {e}")
    except CannotConnect:
        raise
    except Exception as e:
        _LOGGER.exception(f"Unexpected connection error: {e}")
        raise CannotConnect(str(e))
    finally:
        await client.disconnect()
    
    return {
        "title": f"AMiT PLC ({data[CONF_HOST]})",
        "variable_count": len(variables),
        "variables": [
            {"name": v.name, "wid": v.wid, "type": v.type_name}
            for v in variables if v.is_readable()
        ]
    }


class AMiTConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for AMiT."""

    VERSION = 2  # Bumped version due to config structure change

    def __init__(self) -> None:
        """Initialize flow."""
        self._data: dict[str, Any] = {}
        self._variables: list[dict] = []
        self._import_data: dict[str, Any] | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step - choose new config or import."""
        if user_input is not None:
            if user_input.get("setup_type") == "import":
                return await self.async_step_import_select()
            else:
                return await self.async_step_connection()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required("setup_type", default="new"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                selector.SelectOptionDict(value="new", label="New configuration"),
                                selector.SelectOptionDict(value="import", label="Import from backup"),
                            ],
                            mode=selector.SelectSelectorMode.LIST,
                        )
                    ),
                }
            ),
        )

    async def async_step_import_select(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle backup file selection."""
        errors: dict[str, str] = {}
        
        if user_input is not None:
            selected_file = user_input.get("backup_file")
            if selected_file:
                try:
                    # Load the backup file
                    backup_path = Path(self.hass.config.config_dir) / "www" / "amit" / selected_file
                    with open(backup_path, "r", encoding="utf-8") as f:
                        self._import_data = json.load(f)
                    
                    # Pre-fill connection data from backup
                    conn = self._import_data.get("plc_connection", {})
                    self._data = {
                        CONF_HOST: conn.get("host", ""),
                        CONF_PORT: conn.get("port", DEFAULT_PORT),
                        CONF_STATION_ADDR: conn.get("station_addr", DEFAULT_STATION_ADDR),
                        CONF_CLIENT_ADDR: conn.get("client_addr", DEFAULT_CLIENT_ADDR),
                        CONF_PASSWORD: DEFAULT_PASSWORD,  # Password not stored in backup for security
                        CONF_SCAN_INTERVAL: self._import_data.get("scan_interval", DEFAULT_SCAN_INTERVAL),
                    }
                    
                    return await self.async_step_import_confirm()
                    
                except FileNotFoundError:
                    errors["base"] = "file_not_found"
                except json.JSONDecodeError:
                    errors["base"] = "invalid_file"
                except Exception as e:
                    _LOGGER.exception(f"Error loading backup: {e}")
                    errors["base"] = "unknown"
        
        # Find available backup files
        www_amit_dir = Path(self.hass.config.config_dir) / "www" / "amit"
        backup_files = []
        
        if www_amit_dir.exists():
            backup_files = sorted(
                [f.name for f in www_amit_dir.glob("amit_export_*.json") | www_amit_dir.glob("amit_*.json")],
                reverse=True  # Newest first
            )
        
        if not backup_files:
            return self.async_show_form(
                step_id="import_select",
                data_schema=vol.Schema({}),
                errors={"base": "no_backups"},
                description_placeholders={"backup_count": "0"},
            )
        
        options = [
            selector.SelectOptionDict(value=f, label=f)
            for f in backup_files
        ]
        
        return self.async_show_form(
            step_id="import_select",
            data_schema=vol.Schema(
                {
                    vol.Required("backup_file"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=options,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
            errors=errors,
            description_placeholders={"backup_count": str(len(backup_files))},
        )

    async def async_step_import_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm import and optionally adjust connection settings."""
        errors: dict[str, str] = {}
        
        if user_input is not None:
            # Update connection data with user input
            self._data[CONF_HOST] = user_input[CONF_HOST]
            self._data[CONF_PORT] = user_input.get(CONF_PORT, DEFAULT_PORT)
            self._data[CONF_STATION_ADDR] = user_input.get(CONF_STATION_ADDR, DEFAULT_STATION_ADDR)
            self._data[CONF_CLIENT_ADDR] = user_input.get(CONF_CLIENT_ADDR, DEFAULT_CLIENT_ADDR)
            self._data[CONF_PASSWORD] = user_input.get(CONF_PASSWORD, DEFAULT_PASSWORD)
            self._data[CONF_SCAN_INTERVAL] = user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            
            try:
                # Test connection
                info = await validate_connection(self.hass, self._data)
                self._variables = info["variables"]
                
                # Match variables from backup with current PLC variables
                current_wids = {str(v["wid"]) for v in self._variables}
                
                # Get WIDs from backup
                backup_monitored = self._import_data.get("monitored_variables", [])
                backup_writable = self._import_data.get("writable_variables", [])
                
                monitored_wids = [str(v["wid"]) for v in backup_monitored if str(v["wid"]) in current_wids]
                writable_wids = [str(v["wid"]) for v in backup_writable if str(v["wid"]) in current_wids]
                
                # All variables to monitor (both monitored and writable)
                all_selected = list(set(monitored_wids + writable_wids))
                
                self._data[CONF_VARIABLES] = all_selected
                self._data[CONF_WRITABLE_VARIABLES] = writable_wids
                
                # Extract custom names from backup
                custom_names = {}
                for var in backup_monitored + backup_writable:
                    if var.get("custom_name") and str(var["wid"]) in current_wids:
                        custom_names[str(var["wid"])] = var["custom_name"]
                
                if custom_names:
                    self._data[CONF_CUSTOM_NAMES] = custom_names
                    _LOGGER.info(f"Import: found {len(custom_names)} custom entity names")
                
                # Extract custom entity_ids from backup
                custom_entity_ids = {}
                for var in backup_monitored + backup_writable:
                    if var.get("entity_id") and str(var["wid"]) in current_wids:
                        # Store the full entity_id (e.g., "sensor.bs_teplota_tuv")
                        custom_entity_ids[str(var["wid"])] = var["entity_id"]
                
                if custom_entity_ids:
                    self._data[CONF_CUSTOM_ENTITY_IDS] = custom_entity_ids
                    _LOGGER.info(f"Import: found {len(custom_entity_ids)} custom entity IDs")
                
                # Calculate stats for summary
                total_backup = len(backup_monitored) + len(backup_writable)
                total_restored = len(all_selected)
                
                _LOGGER.info(f"Import: restored {total_restored}/{total_backup} variables from backup")
                
                return self.async_create_entry(
                    title=f"AMiT PLC ({self._data[CONF_HOST]})",
                    data=self._data,
                )
                
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception during import")
                errors["base"] = "unknown"
        
        # Show form with pre-filled data from backup
        monitored_count = len(self._import_data.get("monitored_variables", []))
        writable_count = len(self._import_data.get("writable_variables", []))
        
        return self.async_show_form(
            step_id="import_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST, default=self._data.get(CONF_HOST, "")): str,
                    vol.Optional(CONF_PORT, default=self._data.get(CONF_PORT, DEFAULT_PORT)): int,
                    vol.Optional(CONF_STATION_ADDR, default=self._data.get(CONF_STATION_ADDR, DEFAULT_STATION_ADDR)): int,
                    vol.Optional(CONF_CLIENT_ADDR, default=self._data.get(CONF_CLIENT_ADDR, DEFAULT_CLIENT_ADDR)): int,
                    vol.Optional(CONF_PASSWORD, default=DEFAULT_PASSWORD): int,
                    vol.Optional(CONF_SCAN_INTERVAL, default=self._data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)): int,
                }
            ),
            errors=errors,
            description_placeholders={
                "monitored_count": str(monitored_count),
                "writable_count": str(writable_count),
            },
        )

    async def async_step_connection(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the connection settings step."""
        errors: dict[str, str] = {}
        
        if user_input is not None:
            try:
                info = await validate_connection(self.hass, user_input)
                self._data = user_input
                self._variables = info["variables"]
                
                return await self.async_step_variables()
                
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="connection",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST): str,
                    vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
                    vol.Optional(CONF_STATION_ADDR, default=DEFAULT_STATION_ADDR): int,
                    vol.Optional(CONF_CLIENT_ADDR, default=DEFAULT_CLIENT_ADDR): int,
                    vol.Optional(CONF_PASSWORD, default=DEFAULT_PASSWORD): int,
                    vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): int,
                }
            ),
            errors=errors,
        )

    async def async_step_variables(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle variable selection step - select variables to monitor (read-only)."""
        if user_input is not None:
            selected = user_input.get("selected_variables", [])
            self._data[CONF_VARIABLES] = selected
            
            # Go to writable selection
            return await self.async_step_writable()

        # Build options for multi-select
        options = [
            selector.SelectOptionDict(
                value=str(v["wid"]),
                label=f"{v['name']} ({v['type']})"
            )
            for v in self._variables
        ]

        return self.async_show_form(
            step_id="variables",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        "selected_variables",
                        default=[]  # Empty by default
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=options,
                            multiple=True,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
            description_placeholders={
                "variable_count": str(len(self._variables))
            },
        )

    async def async_step_writable(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle writable variable selection step - select variables to control."""
        if user_input is not None:
            writable = user_input.get("writable_variables", [])
            self._data[CONF_WRITABLE_VARIABLES] = writable
            
            return self.async_create_entry(
                title=f"AMiT PLC ({self._data[CONF_HOST]})",
                data=self._data,
            )

        # Only show variables that were selected for monitoring
        selected_wids = set(self._data.get(CONF_VARIABLES, []))
        
        # Filter to only selected variables
        selected_vars = [v for v in self._variables if str(v["wid"]) in selected_wids]
        
        options = [
            selector.SelectOptionDict(
                value=str(v["wid"]),
                label=f"{v['name']} ({v['type']})"
            )
            for v in selected_vars
        ]

        return self.async_show_form(
            step_id="writable",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        "writable_variables",
                        default=[]  # Empty by default
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=options,
                            multiple=True,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
            description_placeholders={
                "selected_count": str(len(selected_vars))
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> AMiTOptionsFlow:
        """Get the options flow for this handler."""
        return AMiTOptionsFlow(config_entry)


class AMiTOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for AMiT."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._variables: list[dict] = []
        self._selected_variables: list[str] = []

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle variable selection - select variables to monitor."""
        errors: dict[str, str] = {}
        
        if user_input is not None:
            selected = user_input.get("selected_variables", [])
            new_scan_interval = user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            
            self._selected_variables = selected
            
            # Store scan interval for later
            self._scan_interval = new_scan_interval
            
            # Go to writable selection
            return await self.async_step_writable()

        # Load variables from PLC
        if not self._variables:
            try:
                data = self.config_entry.data
                client = AMiTClient(
                    host=data[CONF_HOST],
                    port=data.get(CONF_PORT, DEFAULT_PORT),
                    station_addr=data.get(CONF_STATION_ADDR, DEFAULT_STATION_ADDR),
                    client_addr=data.get(CONF_CLIENT_ADDR, DEFAULT_CLIENT_ADDR),
                    password=data.get(CONF_PASSWORD, DEFAULT_PASSWORD),
                    timeout=5.0,
                )
                
                await client.connect()
                variables = await client.load_variables()
                await client.disconnect()
                
                self._variables = [
                    {"name": v.name, "wid": v.wid, "type": v.type_name}
                    for v in variables if v.is_readable()
                ]
                _LOGGER.info(f"Options flow loaded {len(self._variables)} variables")
                
            except Exception as e:
                _LOGGER.error(f"Failed to load variables: {e}")
                errors["base"] = "cannot_connect"
                return self.async_show_form(
                    step_id="init",
                    data_schema=vol.Schema(
                        {
                            vol.Optional(
                                CONF_SCAN_INTERVAL,
                                default=self.config_entry.data.get(
                                    CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                                ),
                            ): int,
                        }
                    ),
                    errors=errors,
                    description_placeholders={"variable_count": "0"},
                )

        # Build options
        options = [
            selector.SelectOptionDict(
                value=str(v["wid"]),
                label=f"{v['name']} ({v['type']})"
            )
            for v in self._variables
        ]
        
        # Current selection
        current_selected = [
            str(wid) for wid in self.config_entry.data.get(CONF_VARIABLES, [])
        ]

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        "selected_variables",
                        default=current_selected
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=options,
                            multiple=True,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Optional(
                        CONF_SCAN_INTERVAL,
                        default=self.config_entry.data.get(
                            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                        ),
                    ): int,
                }
            ),
            description_placeholders={
                "variable_count": str(len(self._variables))
            },
            errors=errors,
        )

    async def async_step_writable(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle writable variable selection."""
        if user_input is not None:
            writable = user_input.get("writable_variables", [])
            
            # Update config entry
            new_data = dict(self.config_entry.data)
            new_data[CONF_VARIABLES] = self._selected_variables
            new_data[CONF_WRITABLE_VARIABLES] = writable
            new_data[CONF_SCAN_INTERVAL] = self._scan_interval
            
            self.hass.config_entries.async_update_entry(
                self.config_entry, data=new_data
            )
            
            # Reload integration
            await self.hass.config_entries.async_reload(self.config_entry.entry_id)
            
            return self.async_create_entry(title="", data={})

        # Only show selected variables
        selected_wids = set(self._selected_variables)
        selected_vars = [v for v in self._variables if str(v["wid"]) in selected_wids]
        
        options = [
            selector.SelectOptionDict(
                value=str(v["wid"]),
                label=f"{v['name']} ({v['type']})"
            )
            for v in selected_vars
        ]
        
        # Current writable selection
        current_writable = [
            str(wid) for wid in self.config_entry.data.get(CONF_WRITABLE_VARIABLES, [])
            if str(wid) in selected_wids  # Only keep if still selected
        ]

        return self.async_show_form(
            step_id="writable",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        "writable_variables",
                        default=current_writable
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=options,
                            multiple=True,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
            description_placeholders={
                "selected_count": str(len(selected_vars))
            },
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""
