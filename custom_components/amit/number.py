"""Number platform for AMiT integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
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
            if variable.var_type == VarType.INT16 and _is_switch_control(variable):
                # This goes to switch platform
                continue
            entities.append(AMiTNumber(coordinator, client, variable, entry))
    
    async_add_entities(entities)


def _is_switch_control(variable: Variable) -> bool:
    """Check if INT16 variable should be a switch (on/off control)."""
    name = variable.name
    switch_prefixes = (
        'Zap', 'Povol', 'RUC', 'AUT', 'Blok', 'zapni',
    )
    exclude_prefixes = ('ZapodH', 'Zapod_', 'ZapodTL')
    
    if name.startswith(exclude_prefixes):
        return False
    return name.startswith(switch_prefixes)


class AMiTNumber(CoordinatorEntity, NumberEntity):
    """Representation of an AMiT number (setpoint or writable value)."""

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
        
        # Set appropriate min/max based on variable type and name
        if self._is_offset_value():
            # Offset/hysteresis values - small range around zero
            self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
            self._attr_native_min_value = -10.0
            self._attr_native_max_value = 10.0
            self._attr_native_step = 0.1
        elif self._is_temperature_value():
            self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
            self._attr_native_min_value = -50.0
            self._attr_native_max_value = 100.0
            self._attr_native_step = 0.1
        elif self._is_temperature_setpoint():
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

    def _is_offset_value(self) -> bool:
        """Check if this is an offset/hysteresis value (small range around zero)."""
        name = self._variable.name
        # Hposun = offset, Hyst = hysteresis, posun = offset, dT = delta temperature
        return name.startswith(('Hposun', 'hposun', 'Hyst', 'hyst', 'posun', 'Posun', 'dT', 'delta'))

    def _is_temperature_setpoint(self) -> bool:
        """Check if this is a temperature setpoint."""
        name = self._variable.name
        # Note: Hposun removed - it's handled by _is_offset_value()
        return name.startswith(('Zad', 'Komf', 'Utl', 'komf', 'utl', 'ZADANA', 'Hmax', 'Hmin'))

    def _is_temperature_value(self) -> bool:
        """Check if this is a temperature value."""
        name = self._variable.name
        temp_prefixes = ('TE', 'Teoko', 'Trek', 'TTUV', 'TPRIV', 'TVENK', 'pokoj', 'koupl', 'T1p')
        if name.startswith(temp_prefixes):
            return True
        if name.startswith('T') and not name.startswith(('Tpr', 'Tlovl', 'test', 'Typ', 'Tim')):
            if self._variable.var_type == VarType.FLOAT:
                return True
        return False

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