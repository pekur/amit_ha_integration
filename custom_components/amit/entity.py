"""Base entity for AMiT integration."""
from __future__ import annotations

from typing import Any
import re

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, CONF_HOST, CONF_TARGET, DEFAULT_TARGET
from .targets import EntityRules, get_target


def get_entity_rules(entry: ConfigEntry) -> EntityRules | None:
    """Resolve classification rules, including the legacy Biosuntec fallback."""
    return get_target(entry.data.get(CONF_TARGET, DEFAULT_TARGET)).entity_rules


def format_identification(system=None, application=None) -> dict:
    """Keep device text readable without guessing component version meanings."""
    result = {}
    for key, fields in (("system", system), ("application", application)):
        if fields is not None:
            result[key] = [" ".join("".join(c if c.isprintable() else " " for c in field).split())
                           for field in fields]
    fields = result.get("system", [])
    if len(fields) == 3:
        candidate = fields[1].split(" - ", 1)[0]
        if fields[0].startswith("AMiT") and re.fullmatch(r"AMi[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*", candidate):
            result["model"] = candidate
        result["sw_version"] = " · ".join(value for value in fields[1:] if value)
    return result


def get_device_info(entry: ConfigEntry, hass=None) -> DeviceInfo:
    """Return device info shared by all entities of a config entry."""
    info = DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=f"AMiT PLC ({entry.data[CONF_HOST]})",
        manufacturer="AMiT",
        model="PLC",
    )
    if hass is not None:
        identification = hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get("identification", {})
        # Optional identification must not erase a previously known model/version.
        previous = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, entry.entry_id)})
        for key in ("model", "sw_version"):
            value = identification.get(key) or (getattr(previous, key, None) if previous else None)
            if value:
                info[key] = value
    return info


class AMiTEntity(CoordinatorEntity):
    """Base class for AMiT entities that use the coordinator."""

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        """Initialize base entity."""
        super().__init__(coordinator)
        self._entry = entry
        self._rules = get_entity_rules(entry)
        self._attr_device_info = get_device_info(entry, getattr(coordinator, "hass", None))

    @property
    def capability_attributes(self) -> dict[str, Any]:
        """Keep the PLC name available when readings are unavailable."""
        return {**(super().capability_attributes or {}), "variable_name": self._variable.name}
