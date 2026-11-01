"""Base entity for AMiT integration."""
from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, CONF_HOST, CONF_TARGET, DEFAULT_TARGET
from .targets import EntityRules, get_target


def get_entity_rules(entry: ConfigEntry) -> EntityRules | None:
    """Resolve classification rules, including the legacy Biosuntec fallback."""
    return get_target(entry.data.get(CONF_TARGET, DEFAULT_TARGET)).entity_rules


def get_device_info(entry: ConfigEntry) -> DeviceInfo:
    """Return device info shared by all entities of a config entry."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=f"AMiT PLC ({entry.data[CONF_HOST]})",
        manufacturer="AMiT",
        model="PLC",
    )


class AMiTEntity(CoordinatorEntity):
    """Base class for AMiT entities that use the coordinator."""

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        """Initialize base entity."""
        super().__init__(coordinator)
        self._entry = entry
        self._rules = get_entity_rules(entry)
        self._attr_device_info = get_device_info(entry)

    @property
    def capability_attributes(self) -> dict[str, Any]:
        """Keep the PLC name available when readings are unavailable."""
        return {**(super().capability_attributes or {}), "variable_name": self._variable.name}
