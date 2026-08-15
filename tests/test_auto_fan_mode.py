"""Unit tests for the AutoFan feature manager business logic.

These tests exercise the pure mapping and activation logic without spinning up a
full Home Assistant instance, using a lightweight fake runtime thermostat.
"""

from __future__ import annotations

import pytest

from custom_components.vtherm_auto_fan_extended.const import (
    CONF_AUTO_FAN_HIGH,
    CONF_AUTO_FAN_LOW,
    CONF_AUTO_FAN_MEDIUM,
    CONF_AUTO_FAN_NONE,
    CONF_AUTO_FAN_TURBO,
)
from custom_components.vtherm_auto_fan_extended.manager import AutoFanFeatureManager


class FakeHass:
    """Minimal hass stub used only for attribute storage."""

    def __init__(self) -> None:
        """Initialize an empty data mapping."""
        self.data: dict = {}


class FakeRuntime:
    """Fake InterfaceThermostatRuntime for the auto fan tests."""

    def __init__(
        self,
        fan_modes: list[str],
        target: float | None = None,
        current: float | None = None,
        hvac_mode: str | None = "heat",
    ) -> None:
        """Store the runtime values exposed to the manager."""
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


def _make_manager(runtime: FakeRuntime) -> AutoFanFeatureManager:
    """Create a manager bound to the given fake runtime."""
    return AutoFanFeatureManager(runtime, FakeHass())


@pytest.mark.parametrize(
    "fan_modes, level, expected",
    [
        (["low", "medium", "high"], CONF_AUTO_FAN_LOW, "low"),
        (["low", "medium", "high"], CONF_AUTO_FAN_MEDIUM, "medium"),
        (["low", "medium", "high"], CONF_AUTO_FAN_HIGH, "high"),
        (["low", "medium", "high"], CONF_AUTO_FAN_TURBO, "high"),
        (["low", "medium", "high", "turbo"], CONF_AUTO_FAN_TURBO, "turbo"),
        (["low", "medium", "high", "turbo"], CONF_AUTO_FAN_LOW, "low"),
    ],
)
def test_choose_auto_fan_mode_mapping(fan_modes, level, expected) -> None:
    """The logical level should map onto the expected underlying speed."""
    runtime = FakeRuntime(fan_modes)
    manager = _make_manager(runtime)
    manager.choose_auto_fan_mode(level)
    assert manager._auto_activated_fan_mode == expected  # noqa: SLF001


def test_choose_auto_fan_mode_none_disables() -> None:
    """The ``none`` level disables activation."""
    runtime = FakeRuntime(["low", "medium", "high"])
    manager = _make_manager(runtime)
    manager.choose_auto_fan_mode(CONF_AUTO_FAN_NONE)
    assert manager._auto_activated_fan_mode is None  # noqa: SLF001


def test_choose_auto_fan_mode_no_speed_modes_warns() -> None:
    """Fan modes without speed values cannot be mapped."""
    runtime = FakeRuntime(["auto", "mute"])
    manager = _make_manager(runtime)
    manager.choose_auto_fan_mode(CONF_AUTO_FAN_HIGH)
    assert manager._auto_activated_fan_mode is None  # noqa: SLF001


async def test_send_activates_when_gap_exceeds_threshold() -> None:
    """A large positive gap in heating mode activates the fan."""
    runtime = FakeRuntime(
        ["low", "medium", "high"], target=22.0, current=19.0, hvac_mode="heat"
    )
    manager = _make_manager(runtime)
    manager._auto_fan_mode = CONF_AUTO_FAN_HIGH  # noqa: SLF001
    manager.choose_auto_fan_mode(CONF_AUTO_FAN_HIGH)

    sent = await manager._send_auto_fan_mode()  # noqa: SLF001
    assert sent is True
    assert runtime.sent_fan_modes == ["high"]


async def test_send_deactivates_when_gap_small() -> None:
    """A small gap deactivates the fan (silent mode)."""
    runtime = FakeRuntime(
        ["low", "medium", "high"], target=20.5, current=20.0, hvac_mode="heat"
    )
    manager = _make_manager(runtime)
    manager._auto_fan_mode = CONF_AUTO_FAN_HIGH  # noqa: SLF001
    manager.choose_auto_fan_mode(CONF_AUTO_FAN_HIGH)

    sent = await manager._send_auto_fan_mode()  # noqa: SLF001
    assert sent is True
    assert runtime.sent_fan_modes == ["low"]


async def test_send_off_mode_never_activates() -> None:
    """When HVAC is off the fan is never activated."""
    runtime = FakeRuntime(
        ["low", "medium", "high"], target=25.0, current=19.0, hvac_mode="off"
    )
    manager = _make_manager(runtime)
    manager._auto_fan_mode = CONF_AUTO_FAN_HIGH  # noqa: SLF001
    manager.choose_auto_fan_mode(CONF_AUTO_FAN_HIGH)

    await manager._send_auto_fan_mode()  # noqa: SLF001
    assert "high" not in runtime.sent_fan_modes


async def test_send_none_level_does_nothing() -> None:
    """With the ``none`` level nothing is sent."""
    runtime = FakeRuntime(
        ["low", "medium", "high"], target=25.0, current=19.0, hvac_mode="heat"
    )
    manager = _make_manager(runtime)
    manager._auto_fan_mode = CONF_AUTO_FAN_NONE  # noqa: SLF001
    manager.choose_auto_fan_mode(CONF_AUTO_FAN_NONE)

    sent = await manager._send_auto_fan_mode()  # noqa: SLF001
    assert sent is False
    assert runtime.sent_fan_modes == []
