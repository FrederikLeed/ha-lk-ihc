"""Set up an IHC controller from the user interface."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_PASSWORD, CONF_URL, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    BooleanSelector,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from . import IHCConfigEntry
from .const import (
    CONF_EXPOSE_BUTTONS,
    CONF_READ_ONLY,
    DEFAULT_EXPOSE_BUTTONS,
    DEFAULT_READ_ONLY,
    DOMAIN,
)
from .controller import IHCAuthError, IHCConnectError, IHCConnection
from .project import parse_project

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_URL, default="http://192.168.1.3"): TextSelector(
            TextSelectorConfig(type=TextSelectorType.URL)
        ),
        vol.Required(CONF_USERNAME): TextSelector(),
        vol.Required(CONF_PASSWORD): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
    }
)


class LKIHCConfigFlow(ConfigFlow, domain=DOMAIN):
    """Ask for the controller's address and sign in to it."""

    VERSION = 1

    def __init__(self) -> None:
        """Start with no controller."""
        self._reauth_entry: IHCConfigEntry | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Connect to a controller and create the entry."""
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {}
        if user_input is not None:
            connection = IHCConnection(
                self.hass, user_input[CONF_URL], user_input[CONF_USERNAME], user_input[CONF_PASSWORD]
            )
            try:
                info = await connection.async_connect()
                project = parse_project(await connection.async_project())
            except IHCAuthError:
                errors["base"] = "invalid_auth"
            except IHCConnectError:
                errors["base"] = "cannot_connect"
            else:
                await connection.async_close()
                serial = str(info.get("serial_number") or "").strip()
                await self.async_set_unique_id(serial or user_input[CONF_URL])
                self._abort_if_unique_id_configured(updates=dict(user_input))
                counts = project.counts()
                title = f"IHC controller {serial}" if serial else "IHC controller"
                placeholders = {
                    "products": str(len(project.products)),
                    "lights": str(counts.get("light", 0)),
                    "switches": str(counts.get("switch", 0)),
                    "buttons": str(counts.get("button", 0)),
                }
                return self.async_create_entry(
                    title=title,
                    data=user_input,
                    options={CONF_READ_ONLY: DEFAULT_READ_ONLY, CONF_EXPOSE_BUTTONS: DEFAULT_EXPOSE_BUTTONS},
                    description_placeholders=placeholders,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(STEP_USER_SCHEMA, user_input or {}),
            errors=errors,
            description_placeholders=placeholders,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """Start again when the controller stops accepting the password."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for the password again and check it."""
        entry = self._reauth_entry
        assert entry is not None
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {**entry.data, **user_input}
            connection = IHCConnection(self.hass, data[CONF_URL], data[CONF_USERNAME], data[CONF_PASSWORD])
            try:
                await connection.async_connect()
            except IHCAuthError:
                errors["base"] = "invalid_auth"
            except IHCConnectError:
                errors["base"] = "cannot_connect"
            else:
                await connection.async_close()
                return self.async_update_reload_and_abort(entry, data=data)

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME, default=entry.data[CONF_USERNAME]): TextSelector(),
                    vol.Required(CONF_PASSWORD): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
                }
            ),
            errors=errors,
            description_placeholders={"url": entry.data[CONF_URL]},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: IHCConfigEntry) -> LKIHCOptionsFlow:
        """Return the options flow."""
        return LKIHCOptionsFlow()


class LKIHCOptionsFlow(OptionsFlow):
    """Read-only mode, and whether the wall switch keys are exposed."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Show and save the options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        options = self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_READ_ONLY,
                        default=options.get(CONF_READ_ONLY, DEFAULT_READ_ONLY),
                    ): BooleanSelector(),
                    vol.Required(
                        CONF_EXPOSE_BUTTONS,
                        default=options.get(CONF_EXPOSE_BUTTONS, DEFAULT_EXPOSE_BUTTONS),
                    ): BooleanSelector(),
                }
            ),
        )
