"""Raw probe services for the iZone bridge API."""

from __future__ import annotations

import json
import logging
from typing import Any

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN
from .helpers import get_client

_LOGGER = logging.getLogger(__name__)

SERVICE_V2_REQUEST = "v2_request"
SERVICE_V2_COMMAND = "v2_command"
SERVICE_V1_COMMAND = "v1_command"
SERVICE_RAW_POST = "raw_post"
SERVICE_RAW_GET = "raw_get"

SCHEMA_V2_REQUEST = vol.Schema(
    {
        vol.Required("type"): cv.positive_int,
        vol.Optional("no", default=0): cv.positive_int,
        vol.Optional("no1", default=0): cv.positive_int,
    }
)
SCHEMA_V2_COMMAND = vol.Schema({vol.Required("payload"): dict})
SCHEMA_V1_COMMAND = vol.Schema(
    {
        vol.Required("command"): cv.string,
        vol.Optional("data", default=dict): dict,
    }
)
SCHEMA_RAW_POST = vol.Schema(
    {
        vol.Required("path"): cv.string,
        vol.Optional("body", default="{}"): cv.string,
    }
)
SCHEMA_RAW_GET = vol.Schema({vol.Required("path"): cv.string})

_loaded = False


async def async_setup_services(hass: HomeAssistant) -> None:
    """Register raw probe services (once)."""
    global _loaded  # noqa: PLW0603
    if _loaded:
        return
    _loaded = True

    async def v2_request(call: ServiceCall) -> ServiceResponse:
        client = get_client(hass)
        return await client.request_v2(
            call.data["type"], call.data.get("no", 0), call.data.get("no1", 0)
        )

    async def v2_command(call: ServiceCall) -> ServiceResponse:
        client = get_client(hass)
        return await client.command_v2(call.data["payload"])

    async def v1_command(call: ServiceCall) -> ServiceResponse:
        client = get_client(hass)
        return await client.command_v1(call.data["command"], call.data.get("data", {}))

    async def raw_post(call: ServiceCall) -> ServiceResponse:
        client = get_client(hass)
        raw = await client.post_raw(call.data["path"], call.data.get("body", "{}"))
        return {"ok": not raw.strip().startswith("{ERROR"), "raw": raw[:48000]}

    async def raw_get(call: ServiceCall) -> ServiceResponse:
        client = get_client(hass)
        raw = await client.get_raw(call.data["path"])
        return {"ok": not raw.strip().startswith("{ERROR"), "raw": raw[:48000]}

    hass.services.async_register(
        DOMAIN, SERVICE_V2_REQUEST, v2_request,
        schema=SCHEMA_V2_REQUEST, supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_V2_COMMAND, v2_command,
        schema=SCHEMA_V2_COMMAND, supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_V1_COMMAND, v1_command,
        schema=SCHEMA_V1_COMMAND, supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_RAW_POST, raw_post,
        schema=SCHEMA_RAW_POST, supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_RAW_GET, raw_get,
        schema=SCHEMA_RAW_GET, supports_response=SupportsResponse.ONLY,
    )
    _LOGGER.warning("iZone Plus raw probe services registered")
