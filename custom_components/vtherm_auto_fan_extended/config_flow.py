"""Config flow for vtherm_auto_fan_extended."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components.climate import DOMAIN as CLIMATE_DOMAIN
from homeassistant.config_entries import ConfigFlow
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import selector

from .const import CONF_TARGET_VTHERM, DOMAIN

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_TARGET_VTHERM): selector.EntitySelector(
            selector.EntitySelectorConfig(domain=CLIMATE_DOMAIN)
        )
    }
)


class AutoFanConfigFlow(ConfigFlow, domain=DOMAIN):
    """Manage Auto Fan plugin config entries."""

    VERSION = 1

    def is_matching(self, other_flow: "AutoFanConfigFlow") -> bool:
        """Return True if the other flow targets the same entry."""
        return other_flow.unique_id == self.unique_id

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Pick the target over_climate VTherm to attach the auto fan to."""
        if user_input is not None:
            entity_id = user_input[CONF_TARGET_VTHERM]
            registry = er.async_get(self.hass)
            reg_entry = registry.async_get(entity_id)
            if reg_entry is None or reg_entry.unique_id is None:
                return self.async_show_form(
                    step_id="user",
                    data_schema=USER_SCHEMA,
                    errors={CONF_TARGET_VTHERM: "invalid_entity"},
                )

            target_unique_id = reg_entry.unique_id
            await self.async_set_unique_id(f"{DOMAIN}-{target_unique_id}")
            self._abort_if_unique_id_configured()

            state = self.hass.states.get(entity_id)
            title = state.name if state is not None else entity_id
            return self.async_create_entry(
                title=title,
                data={CONF_TARGET_VTHERM: target_unique_id},
            )

        return self.async_show_form(step_id="user", data_schema=USER_SCHEMA)

