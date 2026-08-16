"""The vtherm_auto_fan_extended integration."""

from __future__ import annotations

import asyncio
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import CoreState, HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import helper_integration

from vtherm_api.log_collector import get_vtherm_logger
from vtherm_api.vtherm_api import VThermAPI

from .const import (
    CONF_TARGET_VTHERM,
    CONF_THERMOSTAT_CLIMATE,
    CONF_THERMOSTAT_TYPE,
    DATA_ADD_ENTITIES,
    DATA_ENTITIES,
    DATA_FACTORY_REGISTERED,
    DATA_MANAGERS,
    DOMAIN,
    FEATURE_MANAGER_AUTO_FAN,
)
from .factory import AutoFanManagerFactory

VT_DOMAIN = "versatile_thermostat"

PLATFORMS = [Platform.NUMBER, Platform.SELECT, Platform.SWITCH, Platform.SENSOR]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

_LOGGER = get_vtherm_logger(__name__)


def _ensure_domain_data(hass: HomeAssistant) -> dict[str, Any]:
    """Return the plugin data storage in hass."""
    return hass.data.setdefault(DOMAIN, {})


def _register_factory(hass: HomeAssistant) -> bool:
    """Register the AutoFan factory in the shared VT API."""
    data = _ensure_domain_data(hass)
    if data.get(DATA_FACTORY_REGISTERED) is True:
        return True

    api = VThermAPI.get_vtherm_api(hass)
    if api is None:
        _LOGGER.warning(
            "Unable to register AutoFan factory because VThermAPI is unavailable"
        )
        return False

    factory = AutoFanManagerFactory()
    if api.get_feature_manager(factory.name) is None:
        api.register_feature_manager(factory)

    data[DATA_FACTORY_REGISTERED] = True
    return True


def _unregister_factory(hass: HomeAssistant) -> None:
    """Unregister the AutoFan factory from the shared VT API."""
    api = VThermAPI.get_vtherm_api(hass)
    if api is not None:
        api.unregister_feature_manager(FEATURE_MANAGER_AUTO_FAN)
    _ensure_domain_data(hass)[DATA_FACTORY_REGISTERED] = False


async def _reload_auto_fan_vtherms(
    hass: HomeAssistant,
    source_entry: ConfigEntry | None = None,
) -> None:
    """Reload over_climate VTherm entries so they pick up the auto fan config."""
    target_unique_id: str | None = None
    if source_entry is not None:
        target_unique_id = source_entry.data.get(CONF_TARGET_VTHERM)

    reload_tasks = []
    for entry in hass.config_entries.async_entries(VT_DOMAIN):
        if entry.data.get(CONF_THERMOSTAT_TYPE) != CONF_THERMOSTAT_CLIMATE:
            continue
        if target_unique_id is not None and entry.unique_id != target_unique_id:
            continue
        reload_tasks.append(hass.config_entries.async_reload(entry.entry_id))

    if reload_tasks:
        await asyncio.gather(*reload_tasks)


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up vtherm_auto_fan_extended from YAML."""
    del config
    _register_factory(hass)
    return True


async def _cleanup_legacy_helper_devices(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Detach any historical device this helper wrongly co-owned or forked.

    Older releases attached this plugin's config entry to the VTherm device by
    copying its identifiers into ``device_info``. Core 2026.8 restricts a device
    to a single config entry, so relink the plugin entities to the VTherm source
    device and drop the residual split/fork(s) owned by this entry.
    """

    target_uid = entry.data.get(CONF_TARGET_VTHERM)
    if target_uid is None:
        return

    ent_reg = er.async_get(hass)
    source_device_id: str | None = None
    source_entity_id = ent_reg.async_get_entity_id(
        Platform.CLIMATE, VT_DOMAIN, target_uid
    )
    if source_entity_id is not None:
        source_reg_entry = ent_reg.async_get(source_entity_id)
        if source_reg_entry is not None:
            source_device_id = source_reg_entry.device_id

    remove_helper_devices = getattr(
        helper_integration, "async_remove_helper_devices", None
    )
    if remove_helper_devices is not None:
        if source_device_id is not None:
            remove_helper_devices(
                hass,
                helper_config_entry_id=entry.entry_id,
                source_device_id=source_device_id,
            )
        remove_helper_devices(
            hass,
            helper_config_entry_id=entry.entry_id,
            source_device_id=None,
            remove_all_devices=True,
            keep_device_ids=(
                {source_device_id} if source_device_id is not None else set()
            ),
        )
        return

    # Core 2025.8 to 2026.7: only the per-source helper API is available.
    dev_reg = dr.async_get(hass)
    legacy_device_ids = {
        device.id
        for device in dr.async_entries_for_config_entry(dev_reg, entry.entry_id)
    }
    if source_device_id is not None:
        legacy_device_ids.add(source_device_id)
    for device_id in legacy_device_ids:
        helper_integration.async_remove_helper_config_entry_from_source_device(
            hass,
            helper_config_entry_id=entry.entry_id,
            source_device_id=device_id,
        )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up vtherm_auto_fan_extended from a config entry."""
    _ensure_domain_data(hass)[entry.entry_id] = entry.entry_id
    _register_factory(hass)

    await _cleanup_legacy_helper_devices(hass, entry)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_update_options))

    # During initial HA startup, VTherm restores its own entries independently.
    if hass.state == CoreState.running:
        await _reload_auto_fan_vtherms(hass, entry)

    return True


async def _async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the config entry when options change so new params are picked up."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a vtherm_auto_fan_extended config entry."""
    await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    data = _ensure_domain_data(hass)
    data.pop(entry.entry_id, None)

    remaining = [
        key
        for key in data
        if key
        not in (
            DATA_FACTORY_REGISTERED,
            DATA_MANAGERS,
            DATA_ADD_ENTITIES,
            DATA_ENTITIES,
        )
    ]
    if not remaining:
        _unregister_factory(hass)
        await _reload_auto_fan_vtherms(hass)

    return True
