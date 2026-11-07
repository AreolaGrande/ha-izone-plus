"""Data coordinator for iZone Plus — polls V2 endpoints."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
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
SLOW_REFRESH = timedelta(minutes=15)


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
        self._faults: list[dict[str, Any]] = []
        self._firmware = ""
        self._slow_at: datetime | None = None

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            system = await self.client.request_v2(1)
        except (TimeoutError, OSError) as err:
            return self._keep_last(err)
        if not system["ok"] or not system["parsed"]:
            return self._keep_last(system.get("raw") or "SystemV2 request failed")
        sysdata = dict(system["parsed"].get("SystemV2", {}))
        sysdata.pop("Pass", None)
        sysdata.pop("LockCode", None)

        now = datetime.now()
        if self._slow_at is None or now - self._slow_at >= SLOW_REFRESH:
            await self._refresh_slow()
            self._slow_at = now

        no_zones = int(sysdata.get("NoOfZones", 8) or 8)
        previous = (self.data or {}).get("zones") or []
        zones: list[dict[str, Any]] = []
        for i in range(min(no_zones, SCAN_ZONES)):
            try:
                zres: dict[str, Any] = await self.client.request_v2(2, i)
            except (TimeoutError, OSError):
                zres = {"ok": False, "parsed": None}
            if zres["ok"] and zres["parsed"]:
                zones.append(zres["parsed"].get("ZonesV2", {}))
            elif i < len(previous):
                zones.append(previous[i])
            else:
                zones.append({})

        return {
            "system": sysdata,
            "faults": self._faults,
            "firmware": self._firmware,
            "zones": zones,
        }

    def _keep_last(self, err: object) -> dict[str, Any]:
        """A failed poll must not mark every entity unavailable."""
        if self.data:
            _LOGGER.warning("iZone Plus poll failed, keeping last data: %s", err)
            return self.data
        raise UpdateFailed(f"SystemV2 request failed: {err}")

    async def _refresh_slow(self) -> None:
        """Fault history and firmware barely change. Do not fetch them every minute."""
        try:
            faults_res = await self.client.request_v2(4)
        except (TimeoutError, OSError):
            faults_res = {"ok": False, "parsed": None}
        if faults_res["ok"] and faults_res["parsed"]:
            self._faults = [
                f
                for f in faults_res["parsed"].get("AcUnitFaultHistV2", [])
                if f.get("Code", "").strip()
            ]
        try:
            fmw_res = await self.client.request_v2(6)
        except (TimeoutError, OSError):
            fmw_res = {"ok": False, "parsed": None}
        if fmw_res["ok"] and fmw_res["parsed"]:
            self._firmware = fmw_res["parsed"].get("Fmw", "") or self._firmware


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
