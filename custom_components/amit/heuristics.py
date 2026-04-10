"""
Biosuntec HVAC naming heuristics for AMiT PLC variables.

All knowledge about Biosuntec naming conventions lives here.
The protocol layer (protocol.py) has no dependency on this module.
"""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass

from .protocol import VarType

# ---------------------------------------------------------------------------
# Prefix tables (single source of truth)
# ---------------------------------------------------------------------------

_READONLY_PREFIXES = (
    "TE",       # Measured temperatures
    "TEPROST",  # Room temperatures
    "TEVEN",    # Outdoor temp
    "TTUV",     # DHW temperature
    "Trek",     # Recuperation temp
    "pokoj",    # Room sensors
    "Por",      # Faults/errors
    "ALARM",    # Alarms
    "Stav",     # States
    "status",   # Status
    "CO2_",     # CO2 sensors
    "koupl",    # Bathroom temps
    "Teoko",    # Circuit temps
)

_TEMPERATURE_PREFIXES = (
    "TE", "Teoko", "Trek", "TTUV", "TPRIV", "TVENK", "pokoj", "koupl", "T1p",
)

_TEMPERATURE_SETPOINT_PREFIXES = (
    "Zad", "Komf", "Utl", "komf", "utl", "ZADANA", "Hmax", "Hmin",
)

_OFFSET_PREFIXES = (
    "Hposun", "hposun", "Hyst", "hyst", "posun", "Posun", "dT", "delta",
)

_SWITCH_PREFIXES = (
    "Zap", "Povol", "RUC", "AUT", "Blok", "zapni",
)
_SWITCH_EXCLUDE_PREFIXES = ("ZapodH", "Zapod_", "ZapodTL")

_BINARY_STATE_PREFIXES = (
    "Por", "ALARM", "HAVARIE", "Odtavani", "Leto", "TOPIT", "Stav",
)

# These prefixes disqualify a "T…" name from being treated as a temperature
_TEMPERATURE_T_EXCLUDE = ("Tpr", "Tlovl", "test", "Typ", "Tim")


# ---------------------------------------------------------------------------
# Public heuristic functions
# ---------------------------------------------------------------------------

def is_readonly(name: str) -> bool:
    """Return True if the variable is considered read-only by Biosuntec convention."""
    return name.startswith(_READONLY_PREFIXES)


def is_temperature(name: str, var_type: VarType) -> bool:
    """Return True if the variable represents a temperature measurement."""
    if name.startswith(_TEMPERATURE_PREFIXES):
        return True
    # Generic "T…" prefix for float types, excluding known non-temperatures
    if name.startswith("T") and not name.startswith(_TEMPERATURE_T_EXCLUDE):
        if var_type == VarType.FLOAT:
            return True
    return False


def is_temperature_setpoint(name: str) -> bool:
    """Return True if the variable is a temperature setpoint."""
    return name.startswith(_TEMPERATURE_SETPOINT_PREFIXES)


def is_offset_value(name: str) -> bool:
    """Return True if the variable is an offset or hysteresis value."""
    return name.startswith(_OFFSET_PREFIXES)


def is_switch_control(name: str) -> bool:
    """Return True if the variable should be represented as a switch (on/off control)."""
    if name.startswith(_SWITCH_EXCLUDE_PREFIXES):
        return False
    return name.startswith(_SWITCH_PREFIXES)


def is_binary_state(name: str) -> bool:
    """Return True if the variable represents a binary state."""
    return name.startswith(_BINARY_STATE_PREFIXES)


def get_binary_sensor_device_class(name: str) -> BinarySensorDeviceClass | None:
    """Return the appropriate HA BinarySensorDeviceClass for a Biosuntec variable name."""
    if name.startswith(("Por", "ALARM", "HAVARIE")):
        return BinarySensorDeviceClass.PROBLEM
    if name.startswith("TOPIT"):
        return BinarySensorDeviceClass.HEAT
    if name.startswith("Odtavani"):
        return BinarySensorDeviceClass.RUNNING
    return None
