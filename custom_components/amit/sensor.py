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
            if variable.var_type != VarType.INT16 or not _is_binary_state(variable):
                # Numeric sensors (not binary states)
                entities.append(AMiTSensor(coordinator, variable, entry))
    
    async_add_entities(entities)


def _is_binary_state(variable: Variable) -> bool:
    """Check if INT16 variable represents a binary state."""
    name = variable.name
    binary_prefixes = (
        'Por', 'ALARM', 'HAVARIE', 'Odtavani', 'Leto', 'TOPIT', 'Stav',
    )
    return name.startswith(binary_prefixes)


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
        temp_prefixes = ('TE', 'Teoko', 'Trek', 'TTUV', 'TPRIV', 'TVENK', 'pokoj', 'koupl', 'T1p')
        if name.startswith(temp_prefixes):
            return True
        # Generic T prefix for float types, excluding known non-temps
        if name.startswith('T') and not name.startswith(('Tpr', 'Tlovl', 'test', 'Typ', 'Tim')):
            if self._variable.var_type == VarType.FLOAT:
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
        }
