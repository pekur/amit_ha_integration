"""Shared, read-only live values. No history or persistent storage."""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import contextmanager
from datetime import datetime, timezone
import logging
import math
from time import monotonic
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from homeassistant.const import UnitOfTemperature

from .protocol import AMiTClient, Variable

if TYPE_CHECKING:
    from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

    from .targets import EntityRules

_LOGGER = logging.getLogger(__name__)
MIN_READ_DELAY = 0.2


def _signature(variable: Variable) -> tuple:
    return variable.wid, variable.name, variable.var_type


class AMiTMonitor:
    """Share ordinary reads and fill active viewers' read requirements."""

    def __init__(self, hass, client: AMiTClient, variables: list[Variable],
                 monitored: list[Variable], scan_interval: float,
                 rules: EntityRules | None = None,
                 *, coordinator: DataUpdateCoordinator | None = None) -> None:
        self._hass = hass
        self._client = client
        self._interval = max(MIN_READ_DELAY, scan_interval)
        self._rules = rules
        self._coordinator = coordinator
        self._unsub_coordinator: Callable[[], None] | None = None
        self._normal = {_signature(v) for v in monitored if v.is_readable()}
        self._listeners: dict[object, Callable[[dict], None]] = {}
        self._requests: dict[object, tuple[float | None, frozenset[int] | None]] = {}
        self._intervals: dict[int, float] = {}
        self._last_read: dict[int, float] = {}
        self._samples: dict[int, dict] = {}
        self._variables: dict[int, Variable] = {}
        self._revisions: dict[int, int] = {}
        self._revision = 0
        self._sequence = 0
        self._epoch = 0
        self._closed = False
        self._normal_busy = 0
        self._wake = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._due: dict[int, float] = {}
        self._next_read = 0.0
        self._retry_after = 0.0
        self._cursor = 0
        self.runtime_id = uuid4().hex
        self.update_catalog(variables)

    @property
    def closed(self) -> bool:
        """Return whether this runtime has been unloaded."""
        return self._closed

    def snapshot(self) -> dict:
        """Return metadata and latest values, never historical samples."""
        return {
            "kind": "snapshot", "runtime_id": self.runtime_id,
            "sequence": self._sequence,
            "scan_interval": self._interval,
            "intervals": dict(self._intervals),
            "variables": [
                {"wid": v.wid, "name": v.name, "type": v.type_name,
                 "readable": v.is_readable(), "revision": self._revisions[v.wid],
                 "unit": self._unit(v)}
                for v in self._variables.values()
            ],
            "samples": [dict(sample) for sample in self._samples.values()],
        }

    def _unit(self, variable: Variable) -> str | None:
        """Use only units established by the selected profile's rules."""
        if self._rules and variable.is_readable() and (
            self._rules.is_temperature(variable.name, variable.var_type)
            or self._rules.is_temperature_setpoint(variable.name)
            or self._rules.is_offset_value(variable.name)
        ):
            return UnitOfTemperature.CELSIUS
        return None

    def subscribe(self, listener: Callable[[dict], None], *,
                  interval: float | None = None,
                  wids: list[int] | None = None) -> Callable[[], None]:
        """Attach a listener; the caller sends the initial snapshot this turn."""
        if self._closed:
            raise ValueError("PLC monitor is closed")
        if interval is not None and (type(interval) not in (int, float)
                                     or not 1 <= interval <= 120 or not math.isfinite(interval)):
            raise ValueError("Interval must be a finite number from 1 to 120 seconds")
        if wids is not None and (type(wids) is not list or any(
            type(wid) is not int or wid not in self._variables
            or not self._variables[wid].is_readable() for wid in wids
        )):
            raise ValueError("Selected WIDs must identify readable catalog variables")
        if not self._listeners and self._coordinator is not None:
            # Keep ordinary polling alive even when all PLC entities are disabled.
            self._unsub_coordinator = self._coordinator.async_add_listener(self._wake.set)
        token = object()
        self._listeners[token] = listener
        self._requests[token] = (interval, None if wids is None else frozenset(wids))
        self._refresh_schedule()
        self._start_worker()
        self._wake.set()

        def unsubscribe() -> None:
            self._listeners.pop(token, None)
            self._requests.pop(token, None)
            self._refresh_schedule()
            if not self._listeners:
                self._release_coordinator()
                self._samples.clear()
                self._last_read.clear()
                self._due.clear()
                self._epoch += 1
                self._wake.set()

        return unsubscribe

    def _refresh_schedule(self, *, notify: bool = True) -> None:
        """Combine viewer requests without changing ordinary entity polling."""
        intervals = {}
        for wid, variable in self._variables.items():
            if variable.is_readable():
                intervals[wid] = min((
                    interval if interval is not None and (wids is None or wid in wids)
                    else self._interval for interval, wids in self._requests.values()
                ), default=self._interval)
        changed = intervals != self._intervals
        self._intervals = intervals
        self._extras = [v for v in self._variables.values() if v.is_readable() and (
            _signature(v) not in self._normal or intervals[v.wid] < self._interval)]
        self._due = {v.wid: self._last_read[v.wid] + intervals[v.wid]
                     for v in self._extras if v.wid in self._last_read}
        self._cursor = 0
        if changed and notify:
            self._emit({"kind": "intervals", "runtime_id": self.runtime_id,
                        "intervals": dict(intervals)})
        self._start_worker()
        self._wake.set()

    def _release_coordinator(self) -> None:
        """Release only the monitor's listener; entity listeners stay intact."""
        if self._unsub_coordinator is not None:
            unsubscribe = self._unsub_coordinator
            self._unsub_coordinator = None
            unsubscribe()

    def update_catalog(self, variables: list[Variable]) -> None:
        """Replace discovery metadata and invalidate changed definitions."""
        if self._closed:
            return
        updated = {v.wid: v for v in variables}
        for wid, variable in updated.items():
            previous = self._variables.get(wid)
            if previous is None or _signature(previous) != _signature(variable):
                self._revision += 1
                self._revisions[wid] = self._revision
                self._samples.pop(wid, None)
                self._due.pop(wid, None)
                self._last_read.pop(wid, None)
        self._samples = {wid: s for wid, s in self._samples.items() if wid in updated}
        self._due = {wid: due for wid, due in self._due.items() if wid in updated}
        self._revisions = {wid: rev for wid, rev in self._revisions.items() if wid in updated}
        self._variables = updated
        self._last_read = {wid: stamp for wid, stamp in self._last_read.items() if wid in updated}
        self._refresh_schedule(notify=False)
        self._emit(dict(self.snapshot(), kind="catalog"))
        self._start_worker()
        self._wake.set()

    @contextmanager
    def normal_reads(self):
        """Yield to ordinary polling and discovery between extra requests."""
        self._normal_busy += 1
        try:
            yield
        finally:
            self._normal_busy -= 1
            self._wake.set()

    def record(self, variable: Variable, value: Any = None,
               *, failed: bool = False, connection_failed: bool = False) -> None:
        """Publish one actual read, including unchanged values and failures."""
        current = self._variables.get(variable.wid)
        if (not self._listeners or self._closed or current is None
                or not current.is_readable()
                or _signature(current) != _signature(variable)):
            return
        status = "read_error" if failed else "ok"
        if not failed and (type(value) not in (int, float)
                           or not math.isfinite(value)):
            status = "invalid"
        timestamp = datetime.now(timezone.utc).isoformat()
        self._last_read[variable.wid] = monotonic()
        self._due[variable.wid] = self._last_read[variable.wid] + self._intervals[variable.wid]
        previous = self._samples.get(variable.wid, {})
        self._sequence += 1
        sample = {
            "wid": variable.wid, "revision": self._revisions[variable.wid],
            "sequence": self._sequence, "timestamp": timestamp,
            "status": status, "value": value if status == "ok" else None,
            "last_value": value if status == "ok" else previous.get("last_value"),
            "last_success": timestamp if status == "ok" else previous.get("last_success"),
        }
        self._samples[variable.wid] = sample
        if connection_failed:
            # A faster viewer must not shorten the transport recovery delay.
            self._retry_after = monotonic() + self._interval
        self._emit({"kind": "sample", "runtime_id": self.runtime_id,
                    "sample": dict(sample)})

    def _emit(self, event: dict) -> None:
        for listener in list(self._listeners.values()):
            try:
                listener(event)
            except Exception:
                # A disconnected viewer must not break PLC polling.
                _LOGGER.debug("Monitor listener failed", exc_info=True)

    def _start_worker(self) -> None:
        if (self._listeners and self._extras and not self._closed
                and (self._task is None or self._task.done())):
            self._task = self._hass.async_create_background_task(
                self._poll(), "AMiT live monitor"
            )

    async def _wait(self, delay: float) -> None:
        self._wake.clear()
        try:
            await asyncio.wait_for(self._wake.wait(), timeout=delay)
        except asyncio.TimeoutError:
            pass

    async def _poll(self) -> None:
        try:
            # Recent HA versions start background tasks eagerly. Let the API
            # register and acknowledge the subscription before publishing reads.
            await asyncio.sleep(0)
            while self._listeners and not self._closed and self._extras:
                now = monotonic()
                delay = max(self._next_read, self._retry_after) - now
                if self._normal_busy or delay > 0:
                    await self._wait(max(MIN_READ_DELAY, delay))
                    continue
                variable = None
                for _ in self._extras:
                    candidate = self._extras[self._cursor % len(self._extras)]
                    self._cursor += 1
                    if self._due.get(candidate.wid, 0) <= now:
                        variable = candidate
                        break
                if variable is None:
                    await self._wait(max(MIN_READ_DELAY, min(
                        self._due[v.wid] for v in self._extras) - now))
                    continue
                epoch = self._epoch
                revision = self._revisions[variable.wid]
                failed = False
                connection_failed = False
                value = None
                try:
                    value = await self._client.read_variable(variable)
                except Exception as err:
                    failed = True
                    # TimeoutError and ConnectionError are OSError subclasses.
                    # A PLC rejection or invalid value affects only this WID.
                    connection_failed = isinstance(err, OSError)
                finally:
                    self._next_read = monotonic() + MIN_READ_DELAY
                # Ignore an old session or a catalog replaced during the read.
                if (epoch == self._epoch
                        and self._revisions.get(variable.wid) == revision):
                    self.record(variable, value, failed=failed,
                                connection_failed=connection_failed)
        finally:
            self._task = None

    async def async_close(self) -> None:
        """Notify viewers and stop before the UDP client is disconnected."""
        self._closed = True
        self._release_coordinator()
        self._emit({"kind": "unavailable", "runtime_id": self.runtime_id})
        self._listeners.clear()
        self._requests.clear()
        self._last_read.clear()
        self._refresh_schedule()
        self._samples.clear()
        self._wake.set()
        if self._task is not None:
            task = self._task
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
