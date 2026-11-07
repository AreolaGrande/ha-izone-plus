"""Switch platform: installer flags with a documented 0/1 command."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import IZonePlusCoordinator, async_bridge_command, bridge_device_info


@dataclass(frozen=True, slots=True)
class _Flag:
    """One installer flag. state_key is the Type-1 field; command_key is the write."""

    key: str
    name: str
    state_key: str
    command_key: str
    icon: str


# Command names that differ from the status field are called out. The local
# API does not check the config password; these writes are the command itself.
FLAGS: tuple[_Flag, ...] = (
    _Flag("economy_lock", "Economy lock", "EcoLock", "EconomyLock", "mdi:lock"),
    _Flag("fan_auto", "Fan auto", "FanAutoEn", "FanAutoEn", "mdi:fan-auto"),
    _Flag("izone_on_off", "iZone controls on/off", "iZoneOnOff", "iZoneOnOff", "mdi:power"),
    _Flag("izone_mode", "iZone controls mode", "iZoneMode", "iZoneMode", "mdi:thermostat"),
    _Flag("izone_fan", "iZone controls fan", "iZoneFan", "iZoneFan", "mdi:fan"),
    _Flag("izone_setpoint", "iZone controls setpoint", "iZoneSetpoint", "iZoneSetpoint", "mdi:thermometer"),
    _Flag("ac_on_off", "AC unit controls on/off", "ExtOnOff", "ExtOnOff", "mdi:power"),
    _Flag("ac_mode", "AC unit controls mode", "ExtMode", "ExtMode", "mdi:thermostat"),
    _Flag("ac_fan", "AC unit controls fan", "ExtFan", "ExtFan", "mdi:fan"),
    _Flag("ac_setpoint", "AC unit controls setpoint", "ExtSetpoint", "ExtSetpoint", "mdi:thermometer"),
    _Flag("airflow_lock", "Airflow lock", "AirflowLock", "AirflowLock", "mdi:lock"),
    _Flag("airflow_min_lock", "Airflow minimum lock", "AirflowMinLock", "AirflowMinLock", "mdi:lock-outline"),
    _Flag("reverse_dampers", "Reverse dampers", "ReverseDampers", "ReverseDampers", "mdi:swap-horizontal"),
    _Flag("scrooge", "Scrooge mode", "Scrooge", "ScroogeMode", "mdi:leaf"),
    _Flag("hide_induct", "Hide induct temperature", "HideInduct", "HideInduct", "mdi:eye-off"),
    _Flag("auto_off", "Auto off", "AutoOff", "AutoOff", "mdi:timer-off"),
    _Flag("room_temp_display", "Room temperature display", "RoomTempDisp", "RoomTempDisp", "mdi:thermometer"),
    _Flag("wired_leds", "Wired sensor LEDs", "WiredLeds", "SetWiredLeds", "mdi:led-on"),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up installer switches."""
    coordinator: IZonePlusCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    info = bridge_device_info(coordinator)
    async_add_entities([IZoneFlagSwitch(coordinator, info, flag) for flag in FLAGS])


class IZoneFlagSwitch(CoordinatorEntity[IZonePlusCoordinator], SwitchEntity):
    """Write a 0/1 installer command."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: IZonePlusCoordinator,
        device_info: DeviceInfo,
        flag: _Flag,
    ) -> None:
        super().__init__(coordinator)
        self._flag = flag
        self._attr_name = flag.name
        self._attr_icon = flag.icon
        self._attr_unique_id = f"izone_plus_{coordinator.client.host}_{flag.key}"
        self._attr_device_info = device_info

    @property
    def is_on(self) -> bool | None:
        raw = self.coordinator.data["system"].get(self._flag.state_key)
        if raw is None:
            return None
        try:
            return bool(int(raw))
        except (TypeError, ValueError):
            return None

    async def async_turn_on(self, **kwargs) -> None:
        await async_bridge_command(self.coordinator, {self._flag.command_key: 1})

    async def async_turn_off(self, **kwargs) -> None:
        await async_bridge_command(self.coordinator, {self._flag.command_key: 0})
