"""Button platform: reset the filter-cleaning warning after a confirmed press."""

from __future__ import annotations

from datetime import datetime, timedelta
import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import IZonePlusCoordinator

_LOGGER = logging.getLogger(__name__)

# Home Assistant has no confirm dialog on a button press. First press arms.
# Second press inside this window sends the reset.
CONFIRM_WINDOW = timedelta(seconds=30)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the filter-reset button."""
    coordinator: IZonePlusCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    device_info = DeviceInfo(
        identifiers={(DOMAIN, coordinator.client.host)},
        name=f"iZone Plus {coordinator.client.host}",
        manufacturer="iZone / Airstream",
        model="ASH bridge",
    )
    async_add_entities([IZoneFilterResetButton(coordinator, device_info)])


class IZoneFilterResetButton(CoordinatorEntity[IZonePlusCoordinator], ButtonEntity):
    """Send ResetWarning=filter only after a second press."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:air-filter"

    def __init__(
        self, coordinator: IZonePlusCoordinator, device_info: DeviceInfo
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"izone_plus_{coordinator.client.host}_filter_reset"
        self._attr_device_info = device_info
        self._armed_until: datetime | None = None
        self._cancel_arm = None

    @property
    def name(self) -> str:
        if self._armed_until and dt_util.utcnow() < self._armed_until:
            return "Confirm filter reset"
        return "Reset filter warning"

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        if self._armed_until and dt_util.utcnow() < self._armed_until:
            return {
                "confirmation": "Press again within 30 seconds to reset the filter warning",
            }
        return {
            "confirmation": "Press once to arm. Nothing is sent until the second press.",
        }

    def _expire(self, _now: datetime) -> None:
        self._armed_until = None
        self._cancel_arm = None
        self.async_write_ha_state()

    async def async_press(self) -> None:
        """Arm on the first press. Reset only on the confirming press."""
        now = dt_util.utcnow()
        if self._armed_until is None or now >= self._armed_until:
            self._armed_until = now + CONFIRM_WINDOW
            if self._cancel_arm:
                self._cancel_arm()
            self._cancel_arm = async_call_later(
                self.hass, CONFIRM_WINDOW.total_seconds(), self._expire
            )
            self.async_write_ha_state()
            _LOGGER.info("Filter reset armed; waiting for confirmation")
            return

        if self._cancel_arm:
            self._cancel_arm()
            self._cancel_arm = None
        self._armed_until = None
        result = await self.coordinator.client.command_v2({"ResetWarning": "filter"})
        self.async_write_ha_state()
        if not result.get("ok"):
            raise HomeAssistantError(
                f"Bridge rejected filter reset: {result.get('raw')}"
            )
        await self.coordinator.async_request_refresh()
        _LOGGER.info("Filter warning reset sent")
