"""Number platform: installer values with a documented command and limits."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfPower, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import (
    IZonePlusCoordinator,
    async_bridge_command,
    bridge_device_info,
)


@dataclass(frozen=True, slots=True)
class _Setting:
    key: str
    name: str
    state_key: str
    command_key: str
    icon: str
    native_min: float
    native_max: float
    native_step: float
    # Wire value = displayed value * scale. 100 for centi-degree fields.
    scale: int = 1
    unit: str | None = None
    device_class: NumberDeviceClass | None = None


# Limits are the ones in iZone_JSON_datastrings.h. Fan capacity and damper
# time have no published max; the ranges below cover this bridge's live values.
SETTINGS: tuple[_Setting, ...] = (
    _Setting(
        "economy_max", "Economy maximum", "EcoMax", "EconomyMax", "mdi:thermometer-high",
        15, 30, 0.5, 100, UnitOfTemperature.CELSIUS, NumberDeviceClass.TEMPERATURE,
    ),
    _Setting(
        "economy_min", "Economy minimum", "EcoMin", "EconomyMin", "mdi:thermometer-low",
        15, 30, 0.5, 100, UnitOfTemperature.CELSIUS, NumberDeviceClass.TEMPERATURE,
    ),
    _Setting(
        "auto_deadband", "Auto mode deadband", "AutoModeDeadB", "AutoModeDeadB",
        "mdi:arrow-expand-vertical", 0.75, 5, 0.25, 100, UnitOfTemperature.CELSIUS,
    ),
    _Setting(
        "damper_time", "Damper time", "DamperTime", "DamperTime", "mdi:timer",
        0, 240, 1, 1, UnitOfTime.SECONDS,
    ),
    _Setting(
        "fan_capacity", "Fan auto capacity", "FanCapacity", "FanCapacity", "mdi:fan",
        0, 4000, 50,
    ),
    _Setting(
        "fan_unit_capacity", "Fan auto unit capacity", "FanUnitCapacity",
        "FanUnitCapacity", "mdi:air-conditioner", 1, 40, 1, 1, UnitOfPower.KILO_WATT,
        NumberDeviceClass.POWER,
    ),
    _Setting(
        "rf_channel", "RF channel", "RfCh", "ChangeRfCh", "mdi:access-point",
        1, 8, 1,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up installer number entities."""
    coordinator: IZonePlusCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    info = bridge_device_info(coordinator)
    async_add_entities(
        [IZoneSettingNumber(coordinator, info, setting) for setting in SETTINGS]
    )


class IZoneSettingNumber(CoordinatorEntity[IZonePlusCoordinator], NumberEntity):
    """Write one numeric installer command. 0 damper time means automatic."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.BOX

    def __init__(
        self,
        coordinator: IZonePlusCoordinator,
        device_info: DeviceInfo,
        setting: _Setting,
    ) -> None:
        super().__init__(coordinator)
        self._setting = setting
        self._attr_name = setting.name
        self._attr_icon = setting.icon
        self._attr_unique_id = f"izone_plus_{coordinator.client.host}_{setting.key}"
        self._attr_device_info = device_info
        self._attr_native_min_value = setting.native_min
        self._attr_native_max_value = setting.native_max
        self._attr_native_step = setting.native_step
        self._attr_native_unit_of_measurement = setting.unit
        if setting.device_class is not None:
            self._attr_device_class = setting.device_class

    @property
    def native_value(self) -> float | None:
        raw = self.coordinator.data["system"].get(self._setting.state_key)
        if raw is None:
            return None
        try:
            value = int(raw) / self._setting.scale
        except (TypeError, ValueError):
            return None
        return round(value, 2)

    async def async_set_native_value(self, value: float) -> None:
        wire = int(round(value * self._setting.scale))
        low = int(round(self._setting.native_min * self._setting.scale))
        high = int(round(self._setting.native_max * self._setting.scale))
        if wire < low or wire > high:
            raise HomeAssistantError(
                f"{self._setting.name} {value} is outside {self._setting.native_min}"
                f"–{self._setting.native_max}"
            )
        await async_bridge_command(self.coordinator, {self._setting.command_key: wire})
