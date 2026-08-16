"""Unit tests for the pure threshold-based auto fan selection logic."""

from __future__ import annotations

import pytest

from custom_components.vtherm_auto_fan_extended.const import (
    DEFAULT_EXCLUSION_PATTERNS,
    VTHERM_HVAC_MODE_COOL,
    VTHERM_HVAC_MODE_HEAT,
    VTHERM_HVAC_MODE_OFF,
)
from custom_components.vtherm_auto_fan_extended.selection import (
    compile_exclusion_patterns,
    compute_default_rest_mode,
    compute_default_thresholds,
    is_participant,
    select_fan_mode,
)

PATTERNS = compile_exclusion_patterns(DEFAULT_EXCLUSION_PATTERNS)


# ---------------------------------------------------------------------------
# is_participant
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "fan_mode, expected",
    [
        ("on_low", True),
        ("on_high", True),
        ("auto_low", False),
        ("auto_high", False),
        ("auto", False),
        ("off", False),
        ("quiet", True),
        ("low", True),
        ("turbo", True),
        ("on", False),
        ("sleep", False),
        ("circulate", False),
        ("HIGH", True),
        ("Off", False),
    ],
)
def test_is_participant(fan_mode, expected) -> None:
    """Fan modes are classified as participants or not."""
    assert is_participant(fan_mode, PATTERNS) is expected


# ---------------------------------------------------------------------------
# compute_default_thresholds
# ---------------------------------------------------------------------------
def test_default_thresholds_on_off_example() -> None:
    """The on_low/on_high example from the spec (2 participants, °C)."""
    fan_modes = ["on_low", "on_high", "auto_low", "auto_high", "off"]
    thresholds = compute_default_thresholds(fan_modes, PATTERNS, is_fahrenheit=False)
    assert thresholds == {
        "on_low": 1.0,
        "on_high": 3.0,
    }


def test_default_thresholds_seven_participants_example() -> None:
    """The 7-participant example from the spec (°C)."""
    fan_modes = [
        "auto",
        "quiet",
        "low",
        "medlow",
        "medium",
        "medhigh",
        "high",
        "turbo",
    ]
    thresholds = compute_default_thresholds(fan_modes, PATTERNS, is_fahrenheit=False)
    assert "auto" not in thresholds
    assert thresholds["quiet"] == 1.0
    assert thresholds["low"] == 1.3
    assert thresholds["medlow"] == 1.7
    assert thresholds["medium"] == 2.0
    assert thresholds["medhigh"] == 2.3
    assert thresholds["high"] == 2.7
    assert thresholds["turbo"] == 3.0


def test_default_thresholds_single_participant() -> None:
    """A single participant gets the START bound."""
    thresholds = compute_default_thresholds(["off", "low", "auto"], PATTERNS)
    assert thresholds == {"low": 1.0}


def test_default_thresholds_fahrenheit_bounds() -> None:
    """Fahrenheit bounds are used when requested."""
    thresholds = compute_default_thresholds(
        ["low", "high"], PATTERNS, is_fahrenheit=True
    )
    assert thresholds == {"low": 2.0, "high": 6.0}


def test_default_thresholds_empty() -> None:
    """An empty fan_modes list yields an empty mapping."""
    assert compute_default_thresholds([], PATTERNS) == {}


# ---------------------------------------------------------------------------
# compute_default_rest_mode
# ---------------------------------------------------------------------------
def test_default_rest_mode_prefers_quiet() -> None:
    """quiet is chosen when sleep is absent."""
    fan_modes = ["auto", "quiet", "low", "medium", "high", "turbo"]
    assert compute_default_rest_mode(fan_modes) == "quiet"


def test_default_rest_mode_falls_back_to_off() -> None:
    """off is chosen for the on_low/on_high example."""
    fan_modes = ["on_low", "on_high", "auto_low", "auto_high", "off"]
    assert compute_default_rest_mode(fan_modes) == "off"


def test_default_rest_mode_falls_back_to_first() -> None:
    """The first fan_mode is used when no priority mode is present."""
    fan_modes = ["on_low", "on_high"]
    assert compute_default_rest_mode(fan_modes) == "on_low"


def test_default_rest_mode_empty() -> None:
    """An empty list has no rest mode."""
    assert compute_default_rest_mode([]) is None


# ---------------------------------------------------------------------------
# select_fan_mode
# ---------------------------------------------------------------------------
@pytest.fixture
def on_off_thresholds() -> dict[str, float]:
    """Thresholds from the concrete spec example."""
    return {
        "on_low": 1.0,
        "on_high": 2.5,
        "auto_low": 0.0,
        "auto_high": 0.0,
        "off": 0.0,
    }


@pytest.mark.parametrize(
    "dtemp, expected",
    [
        (0.5, "off"),
        (1.8, "on_low"),
        (3.0, "on_high"),
    ],
)
def test_select_fan_mode_spec_example(on_off_thresholds, dtemp, expected) -> None:
    """The concrete spec example selection table (heating)."""
    result = select_fan_mode(
        dtemp, on_off_thresholds, "off", VTHERM_HVAC_MODE_HEAT
    )
    assert result == expected


def test_select_fan_mode_exact_threshold_is_included(on_off_thresholds) -> None:
    """A gap exactly equal to a threshold activates that mode."""
    result = select_fan_mode(
        1.0, on_off_thresholds, "off", VTHERM_HVAC_MODE_HEAT
    )
    assert result == "on_low"


def test_select_fan_mode_heat_negative_gap_returns_rest(on_off_thresholds) -> None:
    """In heating a negative gap (room warmer) returns the rest mode."""
    result = select_fan_mode(
        -3.0, on_off_thresholds, "off", VTHERM_HVAC_MODE_HEAT
    )
    assert result == "off"


def test_select_fan_mode_cool_positive_gap_returns_rest(on_off_thresholds) -> None:
    """In cooling a positive gap (room cooler) returns the rest mode."""
    result = select_fan_mode(
        3.0, on_off_thresholds, "off", VTHERM_HVAC_MODE_COOL
    )
    assert result == "off"


def test_select_fan_mode_cool_negative_gap_activates(on_off_thresholds) -> None:
    """In cooling a negative gap (room warmer) activates the fan."""
    result = select_fan_mode(
        -3.0, on_off_thresholds, "off", VTHERM_HVAC_MODE_COOL
    )
    assert result == "on_high"


def test_select_fan_mode_off_returns_rest(on_off_thresholds) -> None:
    """When HVAC is off the rest mode is always returned."""
    result = select_fan_mode(
        5.0, on_off_thresholds, "off", VTHERM_HVAC_MODE_OFF
    )
    assert result == "off"


def test_select_fan_mode_all_disabled_returns_rest() -> None:
    """When every threshold is 0 the rest mode is always applied."""
    thresholds = {"off": 0.0, "low": 0.0}
    result = select_fan_mode(5.0, thresholds, "off", VTHERM_HVAC_MODE_HEAT)
    assert result == "off"
