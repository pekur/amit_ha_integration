"""Binary sensor platform for AMiT integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import AMiTEntity
from .heuristics import is_binary_state, get_binary_sensor_device_class
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
    writable_wids = data["writable_wids"]
    
    entities = []
    
    for variable in variables:
        # Create binary sensor only if:
        # 1. Variable is NOT in writable_wids
        # 2. Variable is INT16 with binary state name
        if variable.wid not in writable_wids:
            if variable.var_type == VarType.INT16 and is_binary_state(variable.name):
                entities.append(AMiTBinarySensor(coordinator, variable, entry))
    
    async_add_entities(entities)

class AMiTBinarySensor(AMiTEntity, BinarySensorEntity):
    """Representation of an AMiT binary sensor."""

    def __init__(
        self,
        coordinator,
        variable: Variable,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, entry)
        self._variable = variable

        self._attr_unique_id = f"{entry.entry_id}_{variable.wid}_binary"
        self._attr_name = variable.name

        # Determine device class
        self._attr_device_class = get_binary_sensor_device_class(variable.name)

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
