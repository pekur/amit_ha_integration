"""Number platform for AMiT integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, SETPOINT_PREFIXES
from .protocol import Variable, VarType

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up AMiT number entities."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    client = data["client"]
    variables = data["variables"]
    
    entities = []
    
    for variable in variables:
        # Create number entities for writable numeric variables
        if variable.is_readable() and variable.writable:
            if variable.var_type in (VarType.FLOAT, VarType.INT16, VarType.INT32):
                # Skip measurement-like variables
                if not _is_measurement(variable):
                    entities.append(AMiTNumber(coordinator, client, variable, entry))
    
    async_add_entities(entities)


def _is_measurement(variable: Variable) -> bool:
    """Check if variable is a measurement (not a setpoint)."""
    name = variable.name
    # These are measurements, not setpoints
    measurement_prefixes = (
        'TE', 'Teoko', 'pokoj', 'koupl', 'CO2_', 'Trek',
        'Stav', 'status', 'Por', 'ALARM'
    )
    return name.startswith(measurement_prefixes)


class AMiTNumber(CoordinatorEntity, NumberEntity):
    """Representation of an AMiT number (setpoint)."""

    def __init__(
        self,
        coordinator,
        client,
        variable: Variable,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator)
        self._variable = variable
        self._client = client
        self._entry = entry
        
        self._attr_unique_id = f"{entry.entry_id}_{variable.wid}_number"
        self._attr_name = variable.name
        self._attr_mode = NumberMode.BOX
        
        # Set appropriate min/max based on variable name
        if self._is_temperature_setpoint():
            self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
            self._attr_native_min_value = 5.0
            self._attr_native_max_value = 35.0
            self._attr_native_step = 0.5
        elif variable.var_type == VarType.FLOAT:
            self._attr_native_min_value = -1000.0
            self._attr_native_max_value = 1000.0
            self._attr_native_step = 0.1
        elif variable.var_type == VarType.INT16:
            self._attr_native_min_value = -32768
            self._attr_native_max_value = 32767
            self._attr_native_step = 1
        else:  # INT32
            self._attr_native_min_value = -2147483648
            self._attr_native_max_value = 2147483647
            self._attr_native_step = 1
        
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"AMiT PLC ({entry.data['host']})",
            manufacturer="AMiT",
            model="PLC",
        )

    def _is_temperature_setpoint(self) -> bool:
        """Check if this is a temperature setpoint."""
        name = self._variable.name
        return name.startswith(('Zad', 'Komf', 'Utl', 'komf', 'utl', 'ZADANA', 'Hmax', 'Hmin', 'Hposun'))

    @property
    def native_value(self) -> float | int | None:
        """Return the current value."""
        value = self.coordinator.data.get(self._variable.wid)
        if value is None:
            return None
        
        if self._variable.var_type == VarType.FLOAT:
            return round(value, 2)
        return value

    async def async_set_native_value(self, value: float) -> None:
        """Set new value."""
        try:
            success = await self._client.write_variable(self._variable, value)
            if success:
                _LOGGER.info(f"Set {self._variable.name} to {value}")
                await self.coordinator.async_request_refresh()
            else:
                _LOGGER.error(f"Failed to set {self._variable.name}")
        except Exception as e:
            _LOGGER.error(f"Error setting {self._variable.name}: {e}")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        return {
            "wid": self._variable.wid,
            "variable_type": self._variable.type_name,
        }
