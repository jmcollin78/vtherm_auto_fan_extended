"""Tests for the historical single-config-entry device cleanup."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, call

import pytest

import custom_components.vtherm_auto_fan_extended as init_module
from custom_components.vtherm_auto_fan_extended import (
    _cleanup_legacy_helper_devices,
)
from custom_components.vtherm_auto_fan_extended.const import CONF_TARGET_VTHERM

VT_DOMAIN = "versatile_thermostat"


def _entry(entry_id: str = "auto-fan-entry", target: str | None = "vt-salon"):
    """Build a fake config entry with the plugin data."""
    return SimpleNamespace(entry_id=entry_id, data={CONF_TARGET_VTHERM: target})


@pytest.mark.asyncio
async def test_cleanup_targets_source_then_sweeps(monkeypatch) -> None:
    """Modern cleanup relinks/removes the fork then sweeps orphan devices."""
    hass = MagicMock()
    registry = MagicMock()
    registry.async_get_entity_id.return_value = "climate.salon"
    registry.async_get.return_value = SimpleNamespace(device_id="device-salon")
    remove_helper_devices = MagicMock()
    monkeypatch.setattr(init_module.er, "async_get", lambda _hass: registry)
    monkeypatch.setattr(
        init_module.helper_integration,
        "async_remove_helper_devices",
        remove_helper_devices,
        raising=False,
    )

    await _cleanup_legacy_helper_devices(hass, _entry())

    assert remove_helper_devices.call_args_list == [
        call(
            hass,
            helper_config_entry_id="auto-fan-entry",
            source_device_id="device-salon",
        ),
        call(
            hass,
            helper_config_entry_id="auto-fan-entry",
            source_device_id=None,
            remove_all_devices=True,
            keep_device_ids={"device-salon"},
        ),
    ]


@pytest.mark.asyncio
async def test_cleanup_sweeps_without_current_target(monkeypatch) -> None:
    """Cleanup sweeps helper devices when the VTherm device is gone."""
    hass = MagicMock()
    registry = MagicMock()
    registry.async_get_entity_id.return_value = None
    remove_helper_devices = MagicMock()
    monkeypatch.setattr(init_module.er, "async_get", lambda _hass: registry)
    monkeypatch.setattr(
        init_module.helper_integration,
        "async_remove_helper_devices",
        remove_helper_devices,
        raising=False,
    )

    await _cleanup_legacy_helper_devices(hass, _entry())

    remove_helper_devices.assert_called_once_with(
        hass,
        helper_config_entry_id="auto-fan-entry",
        source_device_id=None,
        remove_all_devices=True,
        keep_device_ids=set(),
    )


@pytest.mark.asyncio
async def test_cleanup_uses_legacy_helper(monkeypatch) -> None:
    """Legacy cleanup unlinks current and stale helper-owned devices."""
    hass = MagicMock()
    registry = MagicMock()
    registry.async_get_entity_id.return_value = "climate.salon"
    registry.async_get.return_value = SimpleNamespace(device_id="device-salon")
    device_registry = MagicMock()
    legacy_cleanup = MagicMock()
    monkeypatch.setattr(init_module.er, "async_get", lambda _hass: registry)
    monkeypatch.setattr(init_module.dr, "async_get", lambda _hass: device_registry)
    monkeypatch.setattr(
        init_module.dr,
        "async_entries_for_config_entry",
        lambda _registry, _entry_id: [SimpleNamespace(id="stale-device")],
    )
    monkeypatch.delattr(
        init_module.helper_integration,
        "async_remove_helper_devices",
        raising=False,
    )
    monkeypatch.setattr(
        init_module.helper_integration,
        "async_remove_helper_config_entry_from_source_device",
        legacy_cleanup,
    )

    await _cleanup_legacy_helper_devices(hass, _entry())

    assert sorted(
        c.kwargs["source_device_id"] for c in legacy_cleanup.call_args_list
    ) == ["device-salon", "stale-device"]
    for c in legacy_cleanup.call_args_list:
        assert c.kwargs["helper_config_entry_id"] == "auto-fan-entry"


@pytest.mark.asyncio
async def test_cleanup_noop_without_target(monkeypatch) -> None:
    """Cleanup does nothing when the entry has no target VTherm."""
    hass = MagicMock()
    remove_helper_devices = MagicMock()
    monkeypatch.setattr(
        init_module.helper_integration,
        "async_remove_helper_devices",
        remove_helper_devices,
        raising=False,
    )

    await _cleanup_legacy_helper_devices(hass, _entry(target=None))

    remove_helper_devices.assert_not_called()
