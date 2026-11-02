"""iZone Plus — raw API access to the iZone ASH bridge."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .bridge import IZoneBridgeClient
from .const import CONF_HOST, DOMAIN
from .services import async_setup_services

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = []


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up iZone Plus from a config entry."""
    host = entry.data[CONF_HOST]
    session = async_get_clientsession(hass)
    client = IZoneBridgeClient(session, host)

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = client

    await async_setup_services(hass)
    _LOGGER.warning("iZone Plus set up for bridge %s (entry %s)", host, entry.entry_id)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return True


def get_client(hass: HomeAssistant) -> IZoneBridgeClient:
    """Return the first configured bridge client."""
    entries = hass.data.get(DOMAIN, {})
    if not entries:
        raise ValueError("No iZone Plus bridge configured")
    return next(iter(entries.values()))
