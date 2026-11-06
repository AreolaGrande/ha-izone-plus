"""Select platform: filter reminder interval."""

from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import IZonePlusCoordinator

_LOGGER = logging.getLogger(__name__)

# Spec: FilterWarn months. Valid values 0 (disabled), 3, 6, 12.
INTERVALS: dict[str, int] = {
    "Off": 0,
    "3 months": 3,
    "6 months": 6,
    "12 months": 12,
}
_BY_MONTHS = {months: label for label, months in INTERVALS.items()}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the filter-interval select."""
    coordinator: IZonePlusCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    device_info = DeviceInfo(
        identifiers={(DOMAIN, coordinator.client.host)},
        name=f"iZone Plus {coordinator.client.host}",
        manufacturer="iZone / Airstream",
        model="ASH bridge",
    )
    async_add_entities([IZoneFilterIntervalSelect(coordinator, device_info)])


class IZoneFilterIntervalSelect(CoordinatorEntity[IZonePlusCoordinator], SelectEntity):
    """Set SystemV2.FilterWarn (reminder period, not the clean-now flag)."""

    _attr_has_entity_name = True
    _attr_name = "Filter reminder interval"
    _attr_options = list(INTERVALS)
    _attr_icon = "mdi:air-filter"

    def __init__(
        self, coordinator: IZonePlusCoordinator, device_info: DeviceInfo
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"izone_plus_{coordinator.client.host}_filter_interval"
        self._attr_device_info = device_info

    @property
    def current_option(self) -> str | None:
        raw = self.coordinator.data["system"].get("FilterWarn")
        try:
            return _BY_MONTHS.get(int(raw))
        except (TypeError, ValueError):
            return None

    async def async_select_option(self, option: str) -> None:
        """Write FilterWarn. Body is the command object, not a Cmd wrapper."""
        months = INTERVALS[option]
        result = await self.coordinator.client.command_v2({"FilterWarn": months})
        if not result.get("ok"):
            raise HomeAssistantError(
                f"Bridge rejected FilterWarn={months}: {result.get('raw')}"
            )
        await self.coordinator.async_request_refresh()
        _LOGGER.info("Filter reminder interval set to %s", option)
