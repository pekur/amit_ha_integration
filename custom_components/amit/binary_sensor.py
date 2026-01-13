"""Binary sensor platform for AMiT integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
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
    """Set up AMiT binary sensor entities."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    variables = data["variables"]
    
    entities = []
    
    for variable in variables:
        # Create binary sensors for Int16 variables that look like boolean states
        if variable.var_type == VarType.INT16 and not variable.writable:
            if _is_binary_state(variable):
                entities.append(AMiTBinarySensor(coordinator, variable, entry))
    
    async_add_entities(entities)


def _is_binary_state(variable: Variable) -> bool:
    """Check if variable represents a binary state."""
    name = variable.name
    binary_prefixes = (
        'Por',      # Faults/errors
        'ALARM',    # Alarms  
        'HAVARIE',  # Critical errors
        'Odtavani', # Defrost state
        'Leto',     # Summer mode
        'TOPIT',    # Heating active
    )
    return name.startswith(binary_prefixes)


class AMiTBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Representation of an AMiT binary sensor."""

    def __init__(
        self,
        coordinator,
        variable: Variable,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._variable = variable
        self._entry = entry
        
        self._attr_unique_id = f"{entry.entry_id}_{variable.wid}_binary"
        self._attr_name = variable.name
        
        # Determine device class
        if variable.name.startswith(('Por', 'ALARM', 'HAVARIE')):
            self._attr_device_class = BinarySensorDeviceClass.PROBLEM
        elif variable.name.startswith('TOPIT'):
            self._attr_device_class = BinarySensorDeviceClass.HEAT
        elif variable.name.startswith('Odtavani'):
            self._attr_device_class = BinarySensorDeviceClass.RUNNING
        
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"AMiT PLC ({entry.data['host']})",
            manufacturer="AMiT",
            model="PLC",
        )

    @property
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
        value = self.coordinator.data.get(self._variable.wid)
        if value is None:
            return None
        return value != 0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        return {
            "wid": self._variable.wid,
            "raw_value": self.coordinator.data.get(self._variable.wid),
        }
