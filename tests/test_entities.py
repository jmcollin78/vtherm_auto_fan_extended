"""Tests for the dynamic creation and wiring of the auto fan entities."""

from __future__ import annotations

from custom_components.vtherm_auto_fan_extended.const import (
    PLATFORM_NUMBER,
    PLATFORM_SELECT,
    PLATFORM_SENSOR,
    PLATFORM_SWITCH,
)
from custom_components.vtherm_auto_fan_extended.manager import AutoFanFeatureManager
from custom_components.vtherm_auto_fan_extended.registry import add_entities_registry


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


class FakeRuntime:
    """Fake InterfaceThermostatRuntime exposing a device_info."""

    def __init__(self, hass: FakeHass, fan_modes: list[str]) -> None:
        """Store the runtime values exposed to the manager."""
        self.hass = hass
        self.name = "fake"
        self.unique_id = "uid-1"
        self.entity_id = "climate.fake"
        self.underlying_fan_modes = fan_modes
        self.device_info = {"identifiers": {("vtherm", "uid-1")}}


class FakeAdder:
    """Collects entities passed to async_add_entities."""

    def __init__(self) -> None:
        """Initialize an empty entity list."""
        self.entities: list = []

    def __call__(self, entities) -> None:
        """Record the added entities."""
        self.entities.extend(entities)


def _register(
    hass: FakeHass, uid: str
) -> tuple[FakeAdder, FakeAdder, FakeAdder, FakeAdder]:
    """Register fake add-entities callbacks for the four platforms."""
    registry = add_entities_registry(hass).setdefault(uid, {})
    number_adder = FakeAdder()
    select_adder = FakeAdder()
    switch_adder = FakeAdder()
    sensor_adder = FakeAdder()
    registry[PLATFORM_NUMBER] = number_adder
    registry[PLATFORM_SELECT] = select_adder
    registry[PLATFORM_SWITCH] = switch_adder
    registry[PLATFORM_SENSOR] = sensor_adder
    return number_adder, select_adder, switch_adder, sensor_adder


def test_ensure_entities_creates_all() -> None:
    """Only participant fan_modes get a threshold number; excluded ones do not."""
    hass = FakeHass()
    fan_modes = ["on_low", "on_high", "auto_low", "auto_high", "off"]
    runtime = FakeRuntime(hass, fan_modes)
    manager = AutoFanFeatureManager(runtime, hass)
    number_adder, select_adder, switch_adder, sensor_adder = _register(
        hass, runtime.unique_id
    )

    manager.ensure_entities()

    assert len(switch_adder.entities) == 1
    assert len(select_adder.entities) == 1
    assert len(sensor_adder.entities) == 1
    # auto_low, auto_high and off are excluded by the default patterns.
    assert len(number_adder.entities) == 2

    values = {e._fan_mode: e.native_value for e in number_adder.entities}  # noqa: SLF001
    assert values == {"on_low": 1.0, "on_high": 3.0}


def test_ensure_entities_is_idempotent() -> None:
    """Calling ensure_entities twice does not duplicate entities."""
    hass = FakeHass()
    runtime = FakeRuntime(hass, ["low", "high", "off"])
    manager = AutoFanFeatureManager(runtime, hass)
    number_adder, select_adder, switch_adder, _ = _register(hass, runtime.unique_id)

    manager.ensure_entities()
    manager.ensure_entities()

    assert len(switch_adder.entities) == 1
    assert len(select_adder.entities) == 1
    # off is excluded -> only low and high.
    assert len(number_adder.entities) == 2


def test_ensure_entities_creates_number_for_new_fan_mode() -> None:
    """A fan_mode appearing later gets its own threshold number."""
    hass = FakeHass()
    runtime = FakeRuntime(hass, ["low", "high"])
    manager = AutoFanFeatureManager(runtime, hass)
    number_adder, _, _, _ = _register(hass, runtime.unique_id)

    manager.ensure_entities()
    assert len(number_adder.entities) == 2

    runtime.underlying_fan_modes = ["low", "high", "turbo"]
    manager.ensure_entities()

    assert len(number_adder.entities) == 3
    fan_modes = {e._fan_mode for e in number_adder.entities}  # noqa: SLF001
    assert "turbo" in fan_modes


def test_ensure_entities_waits_for_fan_modes() -> None:
    """Numbers and select are deferred until fan_modes are available."""
    hass = FakeHass()
    runtime = FakeRuntime(hass, [])
    manager = AutoFanFeatureManager(runtime, hass)
    number_adder, select_adder, switch_adder, sensor_adder = _register(
        hass, runtime.unique_id
    )

    manager.ensure_entities()
    # The switch and sensor do not depend on the fan modes.
    assert len(switch_adder.entities) == 1
    assert len(sensor_adder.entities) == 1
    assert len(number_adder.entities) == 0
    assert len(select_adder.entities) == 0

    runtime.underlying_fan_modes = ["low", "high", "off"]
    manager.ensure_entities()
    # off is excluded -> only low and high.
    assert len(number_adder.entities) == 2
    assert len(select_adder.entities) == 1
    # The switch and sensor are not recreated.
    assert len(switch_adder.entities) == 1
    assert len(sensor_adder.entities) == 1


def test_select_options_follow_fan_modes() -> None:
    """The rest select exposes the underlying fan modes as options."""
    hass = FakeHass()
    runtime = FakeRuntime(hass, ["low", "high", "off"])
    manager = AutoFanFeatureManager(runtime, hass)
    _, select_adder, _, _ = _register(hass, runtime.unique_id)

    manager.ensure_entities()
    select = select_adder.entities[0]
    assert select.options == ["low", "high", "off"]
    assert select.current_option == "off"


def test_reconcile_removes_number_for_disappeared_fan_mode() -> None:
    """A fan_mode that disappears from the underlying loses its number."""
    hass = FakeHass()
    runtime = FakeRuntime(hass, ["low", "high"])
    manager = AutoFanFeatureManager(runtime, hass)
    _register(hass, runtime.unique_id)

    manager.ensure_entities()
    assert manager._created_number_fan_modes == {"low", "high"}  # noqa: SLF001

    runtime.underlying_fan_modes = ["low"]
    manager.ensure_entities()

    assert manager._created_number_fan_modes == {"low"}  # noqa: SLF001
