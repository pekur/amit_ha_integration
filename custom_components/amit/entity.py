"""Base entity for AMiT integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, CONF_HOST


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
        self._attr_device_info = get_device_info(entry)
