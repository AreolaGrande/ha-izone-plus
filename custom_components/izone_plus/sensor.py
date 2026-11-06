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

SENSOR_DESCRIPTIONS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(key="filter_warn", name="Filter warning"),
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
    async_add_entities(entities)

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
            if not d["faults"]:
                return None
            latest = d["faults"][0]
            return f'{latest["Code"].strip()} @ {latest["Time"]}'
        if self._key == "firmware":
            return d["firmware"]
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self._key == "latest_fault":
            return {"history": self.coordinator.data["faults"]}
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
