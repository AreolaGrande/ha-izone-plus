"""Config flow for iZone Plus."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .bridge import IZoneBridgeClient
from .const import CONF_HOST, DOMAIN

_LOGGER = logging.getLogger(__name__)


class IZonePlusConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for iZone Plus."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step: bridge host."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            client = IZoneBridgeClient(async_get_clientsession(self.hass), host)
            probe = await client.request_v2(1, 0, 0)
            if probe["ok"]:
                await self.async_set_unique_id("izone_plus_" + host)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=f"iZone Plus {host}", data={CONF_HOST: host})
            errors["base"] = "cannot_connect"
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_HOST): str}),
            errors=errors,
        )
