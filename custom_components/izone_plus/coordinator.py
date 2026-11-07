"""Data coordinator for iZone Plus — polls V2 endpoints."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .bridge import IZoneBridgeClient
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

REDACT = {"Pass", "LockCode"}
SCAN_ZONES = 14  # bridge reports NoOfZones, but pad to catch zone-count drift


class IZonePlusCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Poll SystemV2 / faults / firmware / zones from the bridge."""

    def __init__(self, hass: HomeAssistant, client: IZoneBridgeClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"izone_plus {client.host}",
            update_interval=timedelta(seconds=60),
        )
        self.client = client

    async def _async_update_data(self) -> dict[str, Any]:
        system = await self.client.request_v2(1)
        if not system["ok"] or not system["parsed"]:
            raise UpdateFailed("SystemV2 request failed")
        sysdata = dict(system["parsed"].get("SystemV2", {}))
        sysdata.pop("Pass", None)
        sysdata.pop("LockCode", None)

        faults_res = await self.client.request_v2(4)
        faults: list[dict[str, Any]] = []
        if faults_res["ok"] and faults_res["parsed"]:
            faults = [
                f for f in faults_res["parsed"].get("AcUnitFaultHistV2", [])
                if f.get("Code", "").strip()
            ]

        fmw_res = await self.client.request_v2(6)
        fmw = ""
        if fmw_res["ok"] and fmw_res["parsed"]:
            fmw = fmw_res["parsed"].get("Fmw", "")

        no_zones = int(sysdata.get("NoOfZones", 8) or 8)
        zones: list[dict[str, Any]] = []
        for i in range(min(no_zones, SCAN_ZONES)):
            zres = await self.client.request_v2(2, i)
            if zres["ok"] and zres["parsed"]:
                zones.append(zres["parsed"].get("ZonesV2", {}))
            else:
                zones.append({})

        return {"system": sysdata, "faults": faults, "firmware": fmw, "zones": zones}


def bridge_device_info(coordinator: IZonePlusCoordinator) -> DeviceInfo:
    """Device shared by every platform. Identifier is the bridge host."""
    host = coordinator.client.host
    return DeviceInfo(
        identifiers={(DOMAIN, host)},
        name=f"iZone Plus {host}",
        manufacturer="iZone / Airstream",
        model="ASH bridge",
    )


async def async_bridge_command(
    coordinator: IZonePlusCoordinator, payload: dict[str, Any]
) -> None:
    """POST one bare iZoneCommandV2 object and refresh. No password is sent."""
    result = await coordinator.client.command_v2(payload)
    if not result.get("ok"):
        raise HomeAssistantError(f"Bridge rejected {payload}: {result.get('raw')}")
    await coordinator.async_request_refresh()
