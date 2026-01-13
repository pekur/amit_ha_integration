"""Config flow for AMiT integration."""
from __future__ import annotations

import asyncio
import logging
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
        timeout=5.0,  # Longer timeout for initial connection
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
        
        # Load variables to get count
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
            {"name": v.name, "wid": v.wid, "type": v.type_name, "writable": v.writable}
            for v in variables if v.is_readable()
        ]
    }


class AMiTConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for AMiT."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize flow."""
        self._data: dict[str, Any] = {}
        self._variables: list[dict] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step - connection settings."""
        errors: dict[str, str] = {}
        
        if user_input is not None:
            try:
                info = await validate_connection(self.hass, user_input)
                self._data = user_input
                self._variables = info["variables"]
                
                # Go to variable selection
                return await self.async_step_variables()
                
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
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
        """Handle variable selection step."""
        if user_input is not None:
            selected = user_input.get("selected_variables", [])
            self._data[CONF_VARIABLES] = selected
            
            return self.async_create_entry(
                title=f"AMiT PLC ({self._data[CONF_HOST]})",
                data=self._data,
            )

        # Build options for multi-select
        options = {
            str(v["wid"]): f"{v['name']} ({v['type']}) [WID:{v['wid']}]"
            for v in self._variables
        }
        
        # Pre-select temperature and setpoint variables
        default_selected = [
            str(v["wid"]) for v in self._variables
            if v["name"].startswith(("TE", "Teoko", "Zad", "Komf", "TTUV", "TVENK"))
        ]

        return self.async_show_form(
            step_id="variables",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        "selected_variables",
                        default=default_selected
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                selector.SelectOptionDict(value=k, label=v)
                                for k, v in options.items()
                            ],
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

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle variable selection - this is the main options step."""
        errors: dict[str, str] = {}
        
        if user_input is not None:
            selected = user_input.get("selected_variables", [])
            new_scan_interval = user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            
            # Update config entry with new variables and scan interval
            new_data = dict(self.config_entry.data)
            new_data[CONF_VARIABLES] = selected
            new_data[CONF_SCAN_INTERVAL] = new_scan_interval
            self.hass.config_entries.async_update_entry(
                self.config_entry, data=new_data
            )
            
            # Reload the integration to apply changes
            await self.hass.config_entries.async_reload(self.config_entry.entry_id)
            
            return self.async_create_entry(title="", data={})

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
                    {"name": v.name, "wid": v.wid, "type": v.type_name, "writable": v.writable}
                    for v in variables if v.is_readable()
                ]
                _LOGGER.info(f"Options flow loaded {len(self._variables)} variables")
                
            except Exception as e:
                _LOGGER.error(f"Failed to load variables: {e}")
                errors["base"] = "cannot_connect"
                # Show form with just scan interval if we can't load variables
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

        # Build options for multi-select
        options = [
            selector.SelectOptionDict(
                value=str(v["wid"]), 
                label=f"{v['name']} ({v['type']}) [WID:{v['wid']}]"
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


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""
