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
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, TEMPERATURE_PREFIXES
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
    
    entities = []
    
    for variable in variables:
        # Only create sensors for readable, non-writable variables
        # or Float/Int variables that look like measurements
        if variable.is_readable():
            if not variable.writable or _is_measurement(variable):
                entities.append(AMiTSensor(coordinator, variable, entry))
    
    async_add_entities(entities)


def _is_measurement(variable: Variable) -> bool:
    """Check if variable is a measurement (temperature, etc.)."""
    return variable.name.startswith(TEMPERATURE_PREFIXES)


class AMiTSensor(CoordinatorEntity, SensorEntity):
    """Representation of an AMiT sensor."""

    def __init__(
        self,
        coordinator,
        variable: Variable,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._variable = variable
        self._entry = entry
        
        self._attr_unique_id = f"{entry.entry_id}_{variable.wid}"
        self._attr_name = variable.name
        
        # Determine device class and unit
        if self._is_temperature():
            self._attr_device_class = SensorDeviceClass.TEMPERATURE
            self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
            self._attr_state_class = SensorStateClass.MEASUREMENT
        elif variable.var_type == VarType.FLOAT:
            self._attr_state_class = SensorStateClass.MEASUREMENT
        
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"AMiT PLC ({entry.data['host']})",
            manufacturer="AMiT",
            model="PLC",
        )

    def _is_temperature(self) -> bool:
        """Check if this is a temperature sensor."""
        name = self._variable.name
        # Temperature variables typically start with T, TE, Teoko, etc.
        # and have values in reasonable temperature range
        if name.startswith(('TE', 'Teoko', 'Trek', 'TTUV', 'TPRIV', 'TVENK', 'pokoj', 'koupl', 'T')):
            # Check if it's actually a temperature (not Tpr, Tlovl, etc.)
            if name.startswith(('Tpr', 'Tlovl', 'test')):
                return False
            return True
        return False

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
            "writable": self._variable.writable,
        }
