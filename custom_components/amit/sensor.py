"""Sensor platform for AMiT integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import AMiTEntity
from .heuristics import is_binary_state, is_temperature
from .protocol import Variable, VarType

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up AMiT sensor entities."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    variables = data["variables"]
    writable_wids = data["writable_wids"]
    
    entities = []
    
    for variable in variables:
        # Create sensor only if:
        # 1. Variable is readable (numeric type)
        # 2. Variable is NOT marked as writable by user
        # 3. Variable is not BOOL type (those go to binary_sensor)
        if variable.is_readable() and variable.wid not in writable_wids:
            if variable.var_type != VarType.INT16 or not is_binary_state(variable.name):
                # Numeric sensors (not binary states)
                entities.append(AMiTSensor(coordinator, variable, entry))
    
    async_add_entities(entities)

class AMiTSensor(AMiTEntity, SensorEntity):
    """Representation of an AMiT sensor."""

    def __init__(
        self,
        coordinator,
        variable: Variable,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry)
        self._variable = variable

        self._attr_unique_id = f"{entry.entry_id}_{variable.wid}"
        self._attr_name = variable.name

        # Determine device class and unit
        if is_temperature(variable.name, variable.var_type):
            self._attr_device_class = SensorDeviceClass.TEMPERATURE
            self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
            self._attr_state_class = SensorStateClass.MEASUREMENT
        elif variable.var_type == VarType.FLOAT:
            self._attr_state_class = SensorStateClass.MEASUREMENT

    def _is_temperature(self) -> bool:
        """Check if this is a temperature sensor."""
        return is_temperature(self._variable.name, self._variable.var_type)

    @property
    def native_value(self) -> float | int | None:
        """Return the state of the sensor."""
        value = self.coordinator.data.get(self._variable.wid)
        if value is None:
            return None
        
        # Filter out invalid temperature readings (146.19 = disconnected sensor)
        if self._is_temperature() and isinstance(value, float):
            if value > 100 or value < -50:
                return None
        
        if self._variable.var_type == VarType.FLOAT:
            return round(value, 2)
        return value

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        return {
            "wid": self._variable.wid,
            "variable_type": self._variable.type_name,
        }
