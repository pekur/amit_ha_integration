"""
Target-profile registry for the AMiT integration.

Each TargetProfile describes a specific product / installation type that uses
an AMiT PLC.  The profile bundles the parameters that are passed to
``AMiTClient.load_variables()`` so that ``protocol.py`` stays free of any
product-specific knowledge.

Adding support for a new product = adding one TargetProfile entry here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .heuristics import is_readonly as _biosuntec_is_readonly


@dataclass(frozen=True)
class TargetProfile:
    """Describes a product-specific AMiT variable-loading policy."""

    key: str
    """Stable identifier stored in config entries (never rename once released)."""

    name: str
    """Human-readable display name shown in the HA config flow."""

    description: str
    """Short description shown as a hint in the HA config flow."""

    is_readonly_fn: Callable[[str], bool] | None = field(
        default=None, hash=False, compare=False
    )
    """Optional callable that returns True for variables that should be read-only.
    ``None`` means all variables are treated as writable at the protocol level."""

    wid_min: int | None = None
    """Lower bound for variable WID filtering (inclusive).  ``None`` = no limit."""

    wid_max: int | None = None
    """Upper bound for variable WID filtering (inclusive).  ``None`` = no limit."""


# ---------------------------------------------------------------------------
# Known target profiles
# ---------------------------------------------------------------------------

BIOSUNTEC = TargetProfile(
    key="biosuntec",
    name="Biosuntec HVAC",
    description="Biosuntec HVAC systems (fan coils, floor heating, recuperation, DHW)",
    is_readonly_fn=_biosuntec_is_readonly,
    wid_min=4000,
    wid_max=6000,
)

GENERIC = TargetProfile(
    key="generic",
    name="Generic AMiT PLC",
    description="Generic AMiT DB-Net/IP device — no product-specific variable filtering",
    is_readonly_fn=None,
    wid_min=None,
    wid_max=None,
)

#: Ordered list of all registered target profiles.
#: This list drives the dropdown shown in the HA config flow.
ALL_TARGETS: list[TargetProfile] = [BIOSUNTEC, GENERIC]

_BY_KEY: dict[str, TargetProfile] = {t.key: t for t in ALL_TARGETS}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_target(key: str) -> TargetProfile:
    """Return the TargetProfile for *key*, falling back to BIOSUNTEC if unknown.

    The fallback ensures that existing config entries created before the
    ``target`` field was introduced continue to work without migration.
    """
    return _BY_KEY.get(key, BIOSUNTEC)
