"""Switch platform for AMiT integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .protocol import Variable, VarType

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up AMiT switch entities."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    client = data["client"]
    variables = data["variables"]
    
    entities = []
    
    for variable in variables:
        # Create switches for writable Int16 variables that look like on/off controls
        if variable.var_type == VarType.INT16 and variable.writable:
            if _is_switch_control(variable):
                entities.append(AMiTSwitch(coordinator, client, variable, entry))
    
    async_add_entities(entities)


def _is_switch_control(variable: Variable) -> bool:
    """Check if variable is an on/off control."""
    name = variable.name
    switch_prefixes = (
        'Zap',      # Enable/disable
        'Povol',    # Allow
        'RUC',      # Manual mode
        'AUT',      # Auto mode
        'Blok',     # Block
        'zapni',    # Turn on
    )
    # Exclude some that are not really switches
    exclude_prefixes = ('ZapodH', 'Zapod_', 'ZapodTL')
    
    if name.startswith(exclude_prefixes):
        return False
    return name.startswith(switch_prefixes)


class AMiTSwitch(CoordinatorEntity, SwitchEntity):
    """Representation of an AMiT switch."""

    def __init__(
        self,
        coordinator,
        client,
        variable: Variable,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._variable = variable
        self._client = client
        self._entry = entry
        
        self._attr_unique_id = f"{entry.entry_id}_{variable.wid}_switch"
        self._attr_name = variable.name
        
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"AMiT PLC ({entry.data['host']})",
            manufacturer="AMiT",
            model="PLC",
        )

    @property
    def is_on(self) -> bool | None:
        """Return true if switch is on."""
        value = self.coordinator.data.get(self._variable.wid)
        if value is None:
            return None
        return value != 0

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        try:
            success = await self._client.write_variable(self._variable, 1)
            if success:
                _LOGGER.info(f"Turned on {self._variable.name}")
                await self.coordinator.async_request_refresh()
            else:
                _LOGGER.error(f"Failed to turn on {self._variable.name}")
        except Exception as e:
            _LOGGER.error(f"Error turning on {self._variable.name}: {e}")

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        try:
            success = await self._client.write_variable(self._variable, 0)
            if success:
                _LOGGER.info(f"Turned off {self._variable.name}")
                await self.coordinator.async_request_refresh()
            else:
                _LOGGER.error(f"Failed to turn off {self._variable.name}")
        except Exception as e:
            _LOGGER.error(f"Error turning off {self._variable.name}: {e}")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        return {
            "wid": self._variable.wid,
            "raw_value": self.coordinator.data.get(self._variable.wid),
        }
