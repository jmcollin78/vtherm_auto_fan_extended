"""Unit tests for the AutoFan feature manager wiring and evaluation.

These tests exercise the manager against a lightweight fake runtime thermostat
and fake config entities, without spinning up a full Home Assistant instance.
"""

from __future__ import annotations

import pytest

from custom_components.vtherm_auto_fan_extended.manager import AutoFanFeatureManager
from custom_components.vtherm_auto_fan_extended.registry import entity_bucket


class FakeUnits:
    """Minimal unit system stub."""

    def __init__(self, temperature_unit: str = "°C") -> None:
        """Store the temperature unit."""
        self.temperature_unit = temperature_unit


class FakeConfig:
    """Minimal hass.config stub."""

    def __init__(self, temperature_unit: str = "°C") -> None:
        """Store the unit system."""
        self.units = FakeUnits(temperature_unit)


class FakeHass:
    """Minimal hass stub used for data storage and config."""

    def __init__(self, temperature_unit: str = "°C") -> None:
        """Initialize an empty data mapping and a config."""
        self.data: dict = {}
        self.config = FakeConfig(temperature_unit)


class FakeNumber:
    """Fake threshold number entity."""

    def __init__(self, native_value: float) -> None:
        """Store the threshold value."""
        self.native_value = native_value


class FakeSelect:
    """Fake rest-mode select entity."""

    def __init__(self, current_option: str) -> None:
        """Store the current option."""
        self.current_option = current_option


class FakeSwitch:
    """Fake enable switch entity."""

    def __init__(self, is_on: bool = True) -> None:
        """Store the on/off state."""
        self.is_on = is_on


class FakeRuntime:
    """Fake InterfaceThermostatRuntime for the auto fan tests."""

    def __init__(
        self,
        hass: FakeHass,
        fan_modes: list[str],
        target: float | None = None,
        current: float | None = None,
        hvac_mode: str | None = "heat",
    ) -> None:
        """Store the runtime values exposed to the manager."""
        self.hass = hass
        self.name = "fake"
        self.unique_id = "uid-1"
        self.entity_id = "climate.fake"
        self.underlying_fan_modes = fan_modes
        self.regulated_target_temperature = target
        self.target_temperature = target
        self.current_temperature = current
        self.vtherm_hvac_mode = hvac_mode
        self.sent_fan_modes: list[str] = []

    async def async_set_underlying_fan_mode(self, fan_mode: str) -> None:
        """Record the fan mode sent to the underlying."""
        self.sent_fan_modes.append(fan_mode)

    def update_custom_attributes(self) -> None:
        """No-op stub."""

    def async_write_ha_state(self) -> None:
        """No-op stub."""


def _setup(
    fan_modes: list[str],
    thresholds: dict[str, float],
    rest_mode: str,
    target: float | None = None,
    current: float | None = None,
    hvac_mode: str = "heat",
    enabled: bool = True,
) -> tuple[AutoFanFeatureManager, FakeRuntime]:
    """Build a manager with a populated entity bucket."""
    hass = FakeHass()
    runtime = FakeRuntime(hass, fan_modes, target, current, hvac_mode)
    manager = AutoFanFeatureManager(runtime, hass)
    bucket = entity_bucket(hass, runtime.unique_id)
    bucket["numbers"] = {fm: FakeNumber(val) for fm, val in thresholds.items()}
    bucket["select"] = FakeSelect(rest_mode)
    bucket["switch"] = FakeSwitch(enabled)
    return manager, runtime


ON_OFF_MODES = ["on_low", "on_high", "auto_low", "auto_high", "off"]
ON_OFF_THRESHOLDS = {
    "on_low": 1.0,
    "on_high": 2.5,
    "auto_low": 0.0,
    "auto_high": 0.0,
    "off": 0.0,
}


@pytest.mark.parametrize(
    "target, current, expected",
    [
        (20.5, 20.0, "off"),
        (21.8, 20.0, "on_low"),
        (23.0, 20.0, "on_high"),
    ],
)
async def test_evaluate_spec_example(target, current, expected) -> None:
    """The concrete spec example is applied to the underlying."""
    manager, runtime = _setup(
        ON_OFF_MODES, ON_OFF_THRESHOLDS, "off", target=target, current=current
    )
    changed = await manager._evaluate()  # noqa: SLF001
    assert changed is True
    assert runtime.sent_fan_modes == [expected]


async def test_evaluate_not_resent_when_unchanged() -> None:
    """The fan mode is only sent when it differs from the last sent one."""
    manager, runtime = _setup(
        ON_OFF_MODES, ON_OFF_THRESHOLDS, "off", target=23.0, current=20.0
    )
    assert await manager._evaluate() is True  # noqa: SLF001
    assert await manager._evaluate() is False  # noqa: SLF001
    assert runtime.sent_fan_modes == ["on_high"]


async def test_evaluate_disabled_switch_does_nothing() -> None:
    """When the switch is off the manager never drives the underlying."""
    manager, runtime = _setup(
        ON_OFF_MODES,
        ON_OFF_THRESHOLDS,
        "off",
        target=23.0,
        current=20.0,
        enabled=False,
    )
    assert await manager._evaluate() is False  # noqa: SLF001
    assert runtime.sent_fan_modes == []


async def test_evaluate_off_hvac_applies_rest() -> None:
    """When HVAC is off the rest mode is applied."""
    manager, runtime = _setup(
        ON_OFF_MODES,
        ON_OFF_THRESHOLDS,
        "off",
        target=25.0,
        current=20.0,
        hvac_mode="off",
    )
    assert await manager._evaluate() is True  # noqa: SLF001
    assert runtime.sent_fan_modes == ["off"]


async def test_evaluate_missing_temperature_returns_false() -> None:
    """Missing temperatures prevent any action."""
    manager, runtime = _setup(
        ON_OFF_MODES, ON_OFF_THRESHOLDS, "off", target=None, current=20.0
    )
    assert await manager._evaluate() is False  # noqa: SLF001
    assert runtime.sent_fan_modes == []


async def test_evaluate_rest_mode_disappeared_falls_back() -> None:
    """A rest mode that is not available anymore falls back to a valid mode."""
    manager, runtime = _setup(
        ON_OFF_MODES,
        ON_OFF_THRESHOLDS,
        "ghost",  # not part of the fan modes
        target=20.2,
        current=20.0,
    )
    # Gap 0.2 is below every threshold -> rest, but "ghost" is invalid so the
    # manager falls back to the computed default rest mode ("off").
    assert await manager._evaluate() is True  # noqa: SLF001
    assert runtime.sent_fan_modes == ["off"]


def test_is_configured_and_detected() -> None:
    """The manager reports its configured/detected state from the entities."""
    manager, _ = _setup(
        ON_OFF_MODES, ON_OFF_THRESHOLDS, "off", target=23.0, current=20.0
    )
    assert manager.is_configured is True
    assert manager.is_detected is False


async def test_is_detected_true_when_driving() -> None:
    """is_detected becomes True once a non-rest mode is driven."""
    manager, _ = _setup(
        ON_OFF_MODES, ON_OFF_THRESHOLDS, "off", target=23.0, current=20.0
    )
    await manager._evaluate()  # noqa: SLF001
    assert manager.is_detected is True


def test_add_custom_attributes_section() -> None:
    """Custom attributes are exposed under the dedicated section."""
    manager, _ = _setup(
        ON_OFF_MODES, ON_OFF_THRESHOLDS, "off", target=23.0, current=20.0
    )
    attrs: dict = {}
    manager.add_custom_attributes(attrs)
    assert "auto_fan" in attrs
    section = attrs["auto_fan"]
    assert section["enabled"] is True
    assert section["rest_mode"] == "off"
    assert section["thresholds"] == ON_OFF_THRESHOLDS
