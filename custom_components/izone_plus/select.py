"""Select platform: filter reminder interval."""

from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import IZonePlusCoordinator, async_bridge_command

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
    async_add_entities(
        [
            IZoneFilterIntervalSelect(coordinator, device_info),
            IZoneReturnAirSelect(coordinator, device_info),
            IZoneFanAutoTypeSelect(coordinator, device_info),
            IZoneControlZoneSelect(coordinator, device_info),
        ]
    )


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


# ReturnAirSensor_e: Ras = 1, Master = 2, Zones = 3. Command is RASSet, not RAS.
_RAS: dict[str, int] = {"Return air": 1, "Master": 2, "Zones": 3}
_RAS_BY_VALUE = {value: label for label, value in _RAS.items()}

# FanAutoType_e starts at 0. Command key matches the status field.
_FAN_AUTO: dict[str, int] = {
    "2-speed": 0,
    "3-speed": 1,
    "Variable": 2,
    "4-speed": 3,
}
_FAN_AUTO_BY_VALUE = {value: label for label, value in _FAN_AUTO.items()}


class _MappedSelect(CoordinatorEntity[IZonePlusCoordinator], SelectEntity):
    """Select whose options are a fixed label-to-int map."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: IZonePlusCoordinator,
        device_info: DeviceInfo,
        *,
        key: str,
        name: str,
        icon: str,
        state_key: str,
        command_key: str,
        options: dict[str, int],
        by_value: dict[int, str],
    ) -> None:
        super().__init__(coordinator)
        self._state_key = state_key
        self._command_key = command_key
        self._by_value = by_value
        self._options = options
        self._attr_name = name
        self._attr_icon = icon
        self._attr_options = list(options)
        self._attr_unique_id = f"izone_plus_{coordinator.client.host}_{key}"
        self._attr_device_info = device_info

    @property
    def current_option(self) -> str | None:
        raw = self.coordinator.data["system"].get(self._state_key)
        try:
            return self._by_value.get(int(raw))
        except (TypeError, ValueError):
            return None

    async def async_select_option(self, option: str) -> None:
        await async_bridge_command(
            self.coordinator, {self._command_key: self._options[option]}
        )


class IZoneReturnAirSelect(_MappedSelect):
    """Set which sensor controls the unit."""

    def __init__(
        self, coordinator: IZonePlusCoordinator, device_info: DeviceInfo
    ) -> None:
        super().__init__(
            coordinator,
            device_info,
            key="return_air_sensor",
            name="Return air sensor",
            icon="mdi:thermometer",
            state_key="RAS",
            command_key="RASSet",
            options=_RAS,
            by_value=_RAS_BY_VALUE,
        )


class IZoneFanAutoTypeSelect(_MappedSelect):
    """Set the fan type used by fan-auto."""

    def __init__(
        self, coordinator: IZonePlusCoordinator, device_info: DeviceInfo
    ) -> None:
        super().__init__(
            coordinator,
            device_info,
            key="fan_auto_type",
            name="Fan auto type",
            icon="mdi:fan",
            state_key="FanAutoType",
            command_key="FanAutoType",
            options=_FAN_AUTO,
            by_value=_FAN_AUTO_BY_VALUE,
        )


def _zone_labels(coordinator: IZonePlusCoordinator) -> list[str]:
    """One unique label per installed zone, in bridge index order."""
    labels: list[str] = []
    seen: set[str] = set()
    for index, zone in enumerate(coordinator.data.get("zones") or []):
        name = str(zone.get("Name") or "").strip() or f"Zone {index + 1}"
        if name in seen:
            name = f"{name} ({index + 1})"
        seen.add(name)
        labels.append(name)
    return labels


class IZoneControlZoneSelect(CoordinatorEntity[IZonePlusCoordinator], SelectEntity):
    """Set CtrlZone via MasterZone. Index 0 is zone 1."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_name = "Control zone"
    _attr_icon = "mdi:map-marker"

    def __init__(
        self, coordinator: IZonePlusCoordinator, device_info: DeviceInfo
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"izone_plus_{coordinator.client.host}_control_zone"
        self._attr_device_info = device_info

    @property
    def options(self) -> list[str]:
        return _zone_labels(self.coordinator)

    @property
    def current_option(self) -> str | None:
        labels = self.options
        raw = self.coordinator.data["system"].get("CtrlZone")
        try:
            index = int(raw)
        except (TypeError, ValueError):
            return None
        if 0 <= index < len(labels):
            return labels[index]
        return None

    async def async_select_option(self, option: str) -> None:
        labels = self.options
        if option not in labels:
            raise HomeAssistantError(f"Unknown control zone {option}")
        await async_bridge_command(
            self.coordinator, {"MasterZone": labels.index(option)}
        )
