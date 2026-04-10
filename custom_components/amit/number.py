"""Number platform for AMiT integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import AMiTEntity
from .heuristics import is_switch_control, is_offset_value, is_temperature_setpoint, is_temperature
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
    writable_wids = data["writable_wids"]
    
    entities = []
    
    for variable in variables:
        # Create number entity only if:
        # 1. Variable is in writable_wids (user marked it as writable)
        # 2. Variable is readable (numeric type)
        # 3. Variable is NOT a switch-like INT16 (those go to switch platform)
        if variable.wid in writable_wids and variable.is_readable():
            if variable.var_type == VarType.INT16 and is_switch_control(variable.name):
                # This goes to switch platform
                continue
            entities.append(AMiTNumber(coordinator, client, variable, entry))
    
    async_add_entities(entities)

class AMiTNumber(AMiTEntity, NumberEntity):
    """Representation of an AMiT number (setpoint or writable value)."""

    def __init__(
        self,
        coordinator,
        client,
        variable: Variable,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator, entry)
        self._variable = variable
        self._client = client

        self._attr_unique_id = f"{entry.entry_id}_{variable.wid}_number"
        self._attr_name = variable.name
        self._attr_mode = NumberMode.BOX
        
        # Set appropriate min/max based on variable type and name
        if is_offset_value(variable.name):
            # Offset/hysteresis values - small range around zero
            self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
            self._attr_native_min_value = -10.0
            self._attr_native_max_value = 10.0
            self._attr_native_step = 0.1
        elif is_temperature(variable.name, variable.var_type):
            self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
            self._attr_native_min_value = -50.0
            self._attr_native_max_value = 100.0
            self._attr_native_step = 0.1
        elif is_temperature_setpoint(variable.name):
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