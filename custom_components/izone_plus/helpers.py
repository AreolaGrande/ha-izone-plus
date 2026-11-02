"""Helpers for iZone Plus."""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from .const import DOMAIN


def get_client(hass: HomeAssistant):
    """Return the first configured bridge client."""
    entries = hass.data.get(DOMAIN, {})
    if not entries:
        raise ValueError("No iZone Plus bridge configured")
    return next(iter(entries.values()))
