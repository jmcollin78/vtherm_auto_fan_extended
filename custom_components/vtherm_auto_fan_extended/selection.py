"""Pure business logic for the threshold-based auto fan.

This module contains framework-agnostic helpers that classify fan modes,
compute best-effort default thresholds and select the fan mode to apply from a
temperature gap. It is deliberately free of any Home Assistant dependency so it
can be unit tested in isolation.
"""

from __future__ import annotations

from .const import (
    DEFAULT_THRESHOLD_END_CELSIUS,
    DEFAULT_THRESHOLD_END_FAHRENHEIT,
    DEFAULT_THRESHOLD_START_CELSIUS,
    DEFAULT_THRESHOLD_START_FAHRENHEIT,
    FAN_MODE_EXCLUSION,
    REST_MODE_PRIORITY,
    THRESHOLD_DISABLED,
    VTHERM_HVAC_MODE_COOL,
    VTHERM_HVAC_MODE_HEAT,
    VTHERM_HVAC_MODE_OFF,
)


def is_participant(fan_mode: str) -> bool:
    """Return True when the fan_mode is a candidate activation speed.

    A fan_mode is excluded when it contains the ``auto`` keyword or when it
    matches one of the special/rest modes exactly (case-insensitive).
    """
    normalized = fan_mode.strip().lower()
    if "auto" in normalized:
        return False
    return normalized not in FAN_MODE_EXCLUSION


def compute_default_thresholds(
    fan_modes: list[str], is_fahrenheit: bool = False
) -> dict[str, float]:
    """Compute best-effort default thresholds for the given fan modes.

    Participant fan modes (in list order) receive linearly increasing
    thresholds between ``START`` and ``END`` (depending on the unit); every
    non-participant receives ``0`` (does not participate).
    """
    if is_fahrenheit:
        start = DEFAULT_THRESHOLD_START_FAHRENHEIT
        end = DEFAULT_THRESHOLD_END_FAHRENHEIT
    else:
        start = DEFAULT_THRESHOLD_START_CELSIUS
        end = DEFAULT_THRESHOLD_END_CELSIUS

    participants = [mode for mode in fan_modes if is_participant(mode)]
    count = len(participants)

    thresholds: dict[str, float] = {
        mode: THRESHOLD_DISABLED for mode in fan_modes
    }

    for index, mode in enumerate(participants):
        if count == 1:
            value = start
        else:
            value = start + (end - start) * index / (count - 1)
        thresholds[mode] = round(value, 1)

    return thresholds


def compute_default_rest_mode(fan_modes: list[str]) -> str | None:
    """Return the default rest fan_mode for the given fan modes.

    Picks the first fan_mode found following the rest priority order, falling
    back to the first available fan_mode.
    """
    if not fan_modes:
        return None

    lowered = {mode.lower(): mode for mode in fan_modes}
    for candidate in REST_MODE_PRIORITY:
        if candidate in lowered:
            return lowered[candidate]

    return fan_modes[0]


def select_fan_mode(
    dtemp: float,
    thresholds: dict[str, float],
    rest_mode: str | None,
    hvac_mode: str | None,
) -> str | None:
    """Select the fan_mode to apply from the temperature gap.

    - Applies the heating/cooling coherence guard (never push the fan against
      the current need), returning the rest mode in that case.
    - Otherwise selects, among the modes whose threshold is strictly positive,
      the one with the greatest threshold lower than or equal to ``|dtemp|``.
    - Falls back to the rest mode when no active threshold qualifies.
    """
    if (
        (hvac_mode == VTHERM_HVAC_MODE_HEAT and dtemp < 0)
        or (hvac_mode == VTHERM_HVAC_MODE_COOL and dtemp > 0)
        or hvac_mode == VTHERM_HVAC_MODE_OFF
    ):
        return rest_mode

    abs_dtemp = abs(dtemp)
    best_mode: str | None = None
    best_threshold = THRESHOLD_DISABLED

    for mode, threshold in thresholds.items():
        if threshold > THRESHOLD_DISABLED and threshold <= abs_dtemp:
            if best_mode is None or threshold > best_threshold:
                best_mode = mode
                best_threshold = threshold

    return best_mode if best_mode is not None else rest_mode
