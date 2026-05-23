"""Config flow for the Robot Mower Yard prototype."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.helpers import selector

from .auth import NavimowOAuth2Implementation
from .const import (
    CONF_APP_KEY,
    CONF_APP_SECRET,
    CONF_BASE_STATION_LATITUDE,
    CONF_BASE_STATION_LONGITUDE,
    CONF_BATTERY_ENTITY,
    CONF_ENTRY_KIND,
    CONF_MOWER_NAME,
    CONF_POSITION_OFFSET_EAST_M,
    CONF_POSITION_OFFSET_NORTH_M,
    CONF_PROBLEM_ENTITY,
    CONF_PROVIDER_TYPE,
    CONF_STATUS_ENTITY,
    CONF_TRACKER_ENTITY,
    CONF_YARD_ENTRY_ID,
    CONF_YARD_NAME,
    CONF_ZONES,
    DEFAULT_ZONES,
    DOMAIN,
    ENTRY_KIND_PROVIDER,
    ENTRY_KIND_YARD,
    NAVIMOW_AUTHORIZE_URL,
    NAVIMOW_CLIENT_ID,
    NAVIMOW_CLIENT_SECRET,
    NAVIMOW_TOKEN_URL,
    PROVIDER_ENTITY,
    PROVIDER_HUSQVARNA,
    PROVIDER_MOCK,
    PROVIDER_NAVIMOW,
)


class RobotMowerYardConfigFlow(
    config_entry_oauth2_flow.AbstractOAuth2FlowHandler,
    domain=DOMAIN,
):
    """Handle a config flow."""

    DOMAIN = DOMAIN
    VERSION = 1

    _provider_data: dict[str, Any]

    def __init__(self) -> None:
        """Initialize the flow."""
        super().__init__()
        self._provider_data = {}

    @property
    def logger(self):
        """Return logger."""
        import logging

        return logging.getLogger(__name__)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Choose what to add."""
        if user_input is not None:
            if user_input[CONF_ENTRY_KIND] == ENTRY_KIND_PROVIDER:
                return await self.async_step_provider()
            return await self.async_step_yard()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_ENTRY_KIND,
                        default=ENTRY_KIND_YARD,
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                {"value": ENTRY_KIND_YARD, "label": "Yard/location"},
                                {"value": ENTRY_KIND_PROVIDER, "label": "Mower provider"},
                            ],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
        )

    async def async_step_yard(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Create a yard entry."""
        if user_input is not None:
            yard_name = user_input[CONF_YARD_NAME]
            await self.async_set_unique_id(f"yard_{yard_name.lower()}")
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=yard_name,
                data={
                    CONF_ENTRY_KIND: ENTRY_KIND_YARD,
                    CONF_YARD_NAME: yard_name,
                },
                options={CONF_ZONES: user_input[CONF_ZONES]},
            )

        return self.async_show_form(
            step_id="yard",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_YARD_NAME, default="Home"): str,
                    vol.Optional(CONF_ZONES, default=DEFAULT_ZONES): selector.TextSelector(
                        selector.TextSelectorConfig(multiline=True)
                    ),
                }
            ),
        )

    async def async_step_provider(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Select a provider type and yard."""
        yards = _yard_entries(self)
        if not yards:
            return self.async_abort(reason="no_yards")

        if user_input is not None:
            self._provider_data = dict(user_input)
            if user_input[CONF_PROVIDER_TYPE] == PROVIDER_ENTITY:
                return await self.async_step_entity_provider()
            if user_input[CONF_PROVIDER_TYPE] == PROVIDER_HUSQVARNA:
                return await self.async_step_husqvarna_provider()
            if user_input[CONF_PROVIDER_TYPE] == PROVIDER_NAVIMOW:
                return await self.async_step_navimow_provider()
            return await self.async_step_mock_provider()

        return self.async_show_form(
            step_id="provider",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_YARD_ENTRY_ID): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                {"value": entry_id, "label": title}
                                for entry_id, title in yards.items()
                            ],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Required(
                        CONF_PROVIDER_TYPE,
                        default=PROVIDER_MOCK,
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                {
                                    "value": PROVIDER_HUSQVARNA,
                                    "label": "Husqvarna Automower",
                                },
                                {"value": PROVIDER_NAVIMOW, "label": "Navimow"},
                                {
                                    "value": PROVIDER_ENTITY,
                                    "label": "Existing HA entities",
                                },
                                {"value": PROVIDER_MOCK, "label": "Mock provider"},
                            ],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
        )

    async def async_step_husqvarna_provider(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Create a Husqvarna provider entry."""
        if user_input is not None:
            yard_entry_id = self._provider_data[CONF_YARD_ENTRY_ID]
            await self.async_set_unique_id(f"{yard_entry_id}_{PROVIDER_HUSQVARNA}")
            self._abort_if_unique_id_configured()
            yard_title = _yard_entries(self)[yard_entry_id]
            return self.async_create_entry(
                title=f"{yard_title} Husqvarna",
                data={
                    CONF_ENTRY_KIND: ENTRY_KIND_PROVIDER,
                    CONF_PROVIDER_TYPE: PROVIDER_HUSQVARNA,
                    CONF_YARD_ENTRY_ID: yard_entry_id,
                    **user_input,
                },
            )

        return self.async_show_form(
            step_id="husqvarna_provider",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_APP_KEY): str,
                    vol.Required(CONF_APP_SECRET): str,
                }
            ),
        )

    async def async_step_navimow_provider(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Create a Navimow provider entry."""
        self.flow_impl = NavimowOAuth2Implementation(
            self.hass,
            DOMAIN,
            NAVIMOW_CLIENT_ID,
            NAVIMOW_CLIENT_SECRET,
            NAVIMOW_AUTHORIZE_URL,
            NAVIMOW_TOKEN_URL,
        )
        return await self.async_step_auth(user_input)

    async def async_oauth_create_entry(
        self, data: dict[str, Any]
    ) -> config_entries.ConfigFlowResult:
        """Create a provider entry from OAuth data."""
        yard_entry_id = self._provider_data[CONF_YARD_ENTRY_ID]
        await self.async_set_unique_id(f"{yard_entry_id}_{PROVIDER_NAVIMOW}")
        self._abort_if_unique_id_configured()
        yard_title = _yard_entries(self)[yard_entry_id]
        return self.async_create_entry(
            title=f"{yard_title} Navimow",
            data={
                CONF_ENTRY_KIND: ENTRY_KIND_PROVIDER,
                CONF_PROVIDER_TYPE: PROVIDER_NAVIMOW,
                CONF_YARD_ENTRY_ID: yard_entry_id,
                **data,
            },
        )

    async def async_step_mock_provider(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Create a mock provider entry."""
        yard_entry_id = self._provider_data[CONF_YARD_ENTRY_ID]
        await self.async_set_unique_id(f"{yard_entry_id}_{PROVIDER_MOCK}")
        self._abort_if_unique_id_configured()
        yard_title = _yard_entries(self)[yard_entry_id]
        return self.async_create_entry(
            title=f"{yard_title} Mock Provider",
            data={
                CONF_ENTRY_KIND: ENTRY_KIND_PROVIDER,
                CONF_PROVIDER_TYPE: PROVIDER_MOCK,
                CONF_YARD_ENTRY_ID: yard_entry_id,
            },
        )

    async def async_step_entity_provider(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Create an existing-entities provider entry."""
        if user_input is not None:
            yard_entry_id = self._provider_data[CONF_YARD_ENTRY_ID]
            mower_name = user_input[CONF_MOWER_NAME]
            await self.async_set_unique_id(
                f"{yard_entry_id}_{PROVIDER_ENTITY}_{mower_name.lower()}"
            )
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=mower_name,
                data={
                    CONF_ENTRY_KIND: ENTRY_KIND_PROVIDER,
                    CONF_PROVIDER_TYPE: PROVIDER_ENTITY,
                    CONF_YARD_ENTRY_ID: yard_entry_id,
                    **user_input,
                },
            )

        return self.async_show_form(
            step_id="entity_provider",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_MOWER_NAME, default="Existing Mower"): str,
                    vol.Optional(CONF_TRACKER_ENTITY): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="device_tracker")
                    ),
                    vol.Optional(CONF_STATUS_ENTITY): selector.EntitySelector(),
                    vol.Optional(CONF_BATTERY_ENTITY): selector.EntitySelector(),
                    vol.Optional(CONF_PROBLEM_ENTITY): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="binary_sensor")
                    ),
                }
            ),
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return RobotMowerYardOptionsFlow(config_entry)


class RobotMowerYardOptionsFlow(config_entries.OptionsFlow):
    """Handle options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Manage options."""
        entry_kind = self._config_entry.data.get(CONF_ENTRY_KIND)
        provider_type = self._config_entry.data.get(CONF_PROVIDER_TYPE)
        if entry_kind == ENTRY_KIND_PROVIDER and provider_type == PROVIDER_NAVIMOW:
            return await self.async_step_navimow(user_input)
        if entry_kind != ENTRY_KIND_YARD:
            return self.async_abort(reason="provider_options_not_supported")

        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

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

    async def async_step_navimow(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Manage Navimow provider options."""
        if user_input is not None:
            options = dict(self._config_entry.options)
            options.update(user_input)
            return self.async_create_entry(title="", data=options)

        return self.async_show_form(
            step_id="navimow",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_BASE_STATION_LATITUDE,
                        default=self._config_entry.options.get(
                            CONF_BASE_STATION_LATITUDE,
                        ),
                    ): vol.Coerce(float),
                    vol.Optional(
                        CONF_BASE_STATION_LONGITUDE,
                        default=self._config_entry.options.get(
                            CONF_BASE_STATION_LONGITUDE,
                        ),
                    ): vol.Coerce(float),
                    vol.Optional(
                        CONF_POSITION_OFFSET_NORTH_M,
                        default=self._config_entry.options.get(
                            CONF_POSITION_OFFSET_NORTH_M,
                        ),
                    ): vol.Coerce(float),
                    vol.Optional(
                        CONF_POSITION_OFFSET_EAST_M,
                        default=self._config_entry.options.get(
                            CONF_POSITION_OFFSET_EAST_M,
                        ),
                    ): vol.Coerce(float),
                }
            ),
        )


def _yard_entries(flow: RobotMowerYardConfigFlow) -> dict[str, str]:
    return {
        entry.entry_id: entry.title
        for entry in flow._async_current_entries()
        if entry.data.get(CONF_ENTRY_KIND) == ENTRY_KIND_YARD
    }
