"""Sensor + binary_sensor platform for iZone Plus."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import IZonePlusCoordinator

# Only codes with a published meaning. Others stay "undescribed" — do not guess.
# E4: Mitsubishi Electric chart, "Controller communication error"
# (acgairconditioningcanberra.com.au). 683 and the garbled "t 68" on this
# bridge have no published descriptor.
_FAULT_DESCRIPTORS = {
    "E4": "Controller communication error",
    "OK": "No fault",
}


def fault_code(raw: str) -> str:
    """Normalise a bridge fault code (' 683', ' E4 ', 't 68')."""
    return " ".join(str(raw or "").split())


def fault_descriptor(code: str) -> str:
    """Return a published descriptor, or say there isn't one."""
    return _FAULT_DESCRIPTORS.get(code.upper(), "No published descriptor")


def fault_record(entry: dict[str, Any]) -> dict[str, str]:
    """One history row: code, time, descriptor."""
    code = fault_code(entry.get("Code", ""))
    return {
        "code": code,
        "time": str(entry.get("Time") or "").strip(),
        "descriptor": fault_descriptor(code),
    }

SENSOR_DESCRIPTIONS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="filter_warn",
        name="Filter reminder interval",
        native_unit_of_measurement="months",
        icon="mdi:air-filter",
    ),
    SensorEntityDescription(key="ac_error", name="AC unit status"),
    SensorEntityDescription(key="latest_fault", name="Latest AC fault"),
    SensorEntityDescription(key="firmware", name="Firmware"),
    # SystemV2 duct temps, centi-degrees on the wire. "Induct" is iZone/ASH
    # jargon for the in-duct supply sensor (pizone: temp_supply).
    SensorEntityDescription(
        key="induct_temp", name="Induct temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="°C",
    ),
    SensorEntityDescription(
        key="return_temp", name="Return air temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="°C",
    ),
    SensorEntityDescription(
        key="system_setpoint", name="System setpoint",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="°C",
    ),
)

# SystemV2 keys for the centi-degree temperature sensors.
_CENTI_FIELDS = {"induct_temp": "Supply", "return_temp": "Temp",
                 "system_setpoint": "Setpoint"}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up sensors from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    uid = coordinator.client.host
    device_info = DeviceInfo(
        identifiers={(DOMAIN, uid)},
        name=f"iZone Plus {uid}",
        manufacturer="iZone / Airstream",
        model="ASH bridge",
    )

    entities: list[SensorEntity] = []
    for desc in SENSOR_DESCRIPTIONS:
        entities.append(IZonePlusSensor(coordinator, desc, device_info, desc.key))

    no_zones = min(int(coordinator.data.get("system", {}).get("NoOfZones", 8) or 8), 14)
    for idx in range(no_zones):
        zname = coordinator.data["zones"][idx].get("Name") or f"Zone {idx + 1}"
        entities.append(
            IZonePlusZoneSensor(
                coordinator,
                device_info,
                idx,
                "DmpPos",
                f"{zname} damper position",
                "%",
            )
        )
    async_add_entities(entities + [IZoneFilterCleanSensor(coordinator, device_info)])

    bins: list[BinarySensorEntity] = []
    for idx in range(no_zones):
        zname = coordinator.data["zones"][idx].get("Name") or f"Zone {idx + 1}"
        bins.append(
            IZonePlusZoneBinarySensor(
                coordinator,
                device_info,
                idx,
                "SensorFault",
                f"{zname} zone sensor fault",
            )
        )
    async_add_entities(bins)


class _Base(CoordinatorEntity[IZonePlusCoordinator]):
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: IZonePlusCoordinator,
        device_info: DeviceInfo,
        key: str,
    ) -> None:
        super().__init__(coordinator)
        self._key = key
        self._attr_unique_id = f"izone_plus_{coordinator.client.host}_{key}"
        self._device_info = device_info


class IZonePlusSensor(_Base, SensorEntity):
    """Top-level system sensors."""

    def __init__(
        self,
        coordinator: IZonePlusCoordinator,
        description: SensorEntityDescription,
        device_info: DeviceInfo,
        key: str,
    ) -> None:
        super().__init__(coordinator, device_info, key)
        self.entity_description = description
        self._attr_device_info = device_info

    @property
    def native_value(self) -> Any:
        d = self.coordinator.data
        if self._key in _CENTI_FIELDS:
            raw = d["system"].get(_CENTI_FIELDS[self._key])
            if not isinstance(raw, (int, float)) or raw in (0, 32128):
                return None
            return round(raw / 100, 1)
        if self._key == "filter_warn":
            return d["system"].get("FilterWarn")
        if self._key == "ac_error":
            return str(d["system"].get("ACError", "")).strip() or "ok"
        if self._key == "latest_fault":
            faults = d.get("faults") or []
            if not faults:
                return None
            row = fault_record(faults[0])
            if not row["code"]:
                return None
            return f'{row["code"]} — {row["descriptor"]} @ {row["time"]}'
        if self._key == "firmware":
            return d["firmware"]
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self._key == "latest_fault":
            rows = [
                fault_record(entry)
                for entry in self.coordinator.data.get("faults") or []
                if fault_code(entry.get("Code", ""))
            ]
            return {"history": rows}
        return None


class IZonePlusZoneSensor(_Base, SensorEntity):
    """Per-zone numeric attribute (damper position)."""

    def __init__(
        self,
        coordinator: IZonePlusCoordinator,
        device_info: DeviceInfo,
        zone_idx: int,
        field: str,
        name: str,
        unit: str,
    ) -> None:
        super().__init__(coordinator, device_info, f"z{zone_idx}_{field}")
        self._zone_idx = zone_idx
        self._field = field
        self._attr_name = name
        self._attr_native_unit_of_measurement = unit
        self._attr_device_info = device_info

    @property
    def native_value(self) -> Any:
        zones = self.coordinator.data.get("zones", [])
        if self._zone_idx >= len(zones):
            return None
        return zones[self._zone_idx].get(self._field)


class IZonePlusZoneBinarySensor(_Base, BinarySensorEntity):
    """Per-zone boolean (sensor fault)."""

    def __init__(
        self,
        coordinator: IZonePlusCoordinator,
        device_info: DeviceInfo,
        zone_idx: int,
        field: str,
        name: str,
    ) -> None:
        super().__init__(coordinator, device_info, f"z{zone_idx}_{field}")
        self._zone_idx = zone_idx
        self._field = field
        self._attr_name = name
        self._attr_device_info = device_info

    @property
    def is_on(self) -> bool | None:
        zones = self.coordinator.data.get("zones", [])
        if self._zone_idx >= len(zones):
            return None
        v = zones[self._zone_idx].get(self._field)
        return bool(v) if v is not None else None


class IZoneFilterCleanSensor(_Base, SensorEntity):
    """yes when SystemV2.Warnings is \"filter\". Not the reminder interval."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["yes", "no"]
    _attr_name = "Filter cleaning required"
    _attr_icon = "mdi:air-filter"

    def __init__(
        self, coordinator: IZonePlusCoordinator, device_info: DeviceInfo
    ) -> None:
        super().__init__(coordinator, device_info, "filter_clean")
        self._attr_device_info = device_info

    @property
    def native_value(self) -> str:
        warnings = str(self.coordinator.data["system"].get("Warnings") or "")
        return "yes" if warnings.strip().lower() == "filter" else "no"
