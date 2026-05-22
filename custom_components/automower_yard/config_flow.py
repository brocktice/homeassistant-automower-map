"""Config flow for Automower Yard."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector

from .api import AutomowerApiClient, AutomowerApiError
from .const import CONF_APP_KEY, CONF_APP_SECRET, CONF_ZONES, DEFAULT_ZONES, DOMAIN


class AutomowerYardConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle initial setup."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await _validate_credentials(self.hass, user_input)
            except AutomowerApiError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(user_input[CONF_APP_KEY])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="Automower Yard",
                    data=user_input,
                    options={CONF_ZONES: DEFAULT_ZONES},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_APP_KEY): str,
                    vol.Required(CONF_APP_SECRET): str,
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return AutomowerYardOptionsFlow(config_entry)


class AutomowerYardOptionsFlow(config_entries.OptionsFlow):
    """Handle integration options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Manage options."""
        if user_input is not None:
            return self.async_create_entry(
                title="",
                data={**self._config_entry.options, **user_input},
            )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_ZONES,
                        default=self._config_entry.options.get(
                            CONF_ZONES, DEFAULT_ZONES
                        ),
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(multiline=True)
                    )
                }
            ),
        )


async def _validate_credentials(hass: HomeAssistant, data: dict[str, Any]) -> None:
    client = AutomowerApiClient(hass, data[CONF_APP_KEY], data[CONF_APP_SECRET])
    await client.async_validate()
