"""Diagnostic sensors for the controller itself, so its own state can be looked at.

The rest of the integration exposes the installation: lamps, relays, the keys on the wall. These
describe the box that runs it - how many wireless devices it hears, whether its clock is right,
what address it answers on - and they are read-only by nature. None of it can be set from Home
Assistant, and none of it should be: changing a controller's address or its clock belongs in IHC
Administrator, where an installer can see what they are doing.

They are read once, when the entry is set up, because nothing here changes unless someone visits
the controller. Reload the entry to read them again.

The clock is the exception worth watching. A controller runs its own time-based logic, so a clock
that has drifted quietly moves when the house does things, and `clock_offset` says by how much.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN
from .services import ControllerStatus


def _clock_offset(status: ControllerStatus) -> int | None:
    """Return how far the controller's clock is from ours, in seconds.

    Negative means the controller is behind. The controller reports local time with its own
    offset and DST applied, so that is undone before comparing: what matters is the instant, not
    how the controller chooses to write it down.
    """
    if status.controller_time is None or status.gmt_offset_hours is None:
        return None
    try:
        naive = dt.datetime.fromisoformat(status.controller_time)
    except ValueError:
        return None
    offset = status.gmt_offset_hours + (1 if status.uses_dst else 0)
    controller = naive.replace(tzinfo=dt.timezone(dt.timedelta(hours=offset)))
    return round((controller - dt.datetime.now(dt.UTC)).total_seconds())


def _count(status: ControllerStatus, of: Callable[[ControllerStatus], int]) -> int | None:
    """Return a count of wireless devices, or None when the controller has no wireless service.

    Reporting 0 would read as "it heard none", when the truth is that it was never able to ask:
    a controller without AirlinkManagementService answers nothing at all.
    """
    return of(status) if status.rf_devices else None


def _signal(status: ControllerStatus, pick: Callable[[list[int]], int]) -> int | None:
    """Return a signal strength across the wireless devices, or None when there are none."""
    strengths = [device.signal_strength for device in status.rf_devices]
    return pick(strengths) if strengths else None


@dataclass(frozen=True, kw_only=True)
class ControllerSensorDescription(SensorEntityDescription):
    """A sensor whose value is read straight off the controller's status."""

    value: Callable[[ControllerStatus], Any]


SENSORS: tuple[ControllerSensorDescription, ...] = (
    ControllerSensorDescription(
        key="rf_devices",
        translation_key="rf_devices",
        icon="mdi:access-point",
        value=lambda status: _count(status, lambda s: len(s.rf_devices)),
    ),
    ControllerSensorDescription(
        key="rf_devices_low_battery",
        translation_key="rf_devices_low_battery",
        icon="mdi:battery-alert",
        value=lambda status: _count(status, lambda s: s.rf_devices_low_battery),
    ),
    ControllerSensorDescription(
        key="rf_devices_unheard",
        translation_key="rf_devices_unheard",
        icon="mdi:access-point-off",
        value=lambda status: _count(status, lambda s: s.rf_devices_unheard),
    ),
    ControllerSensorDescription(
        key="rf_signal_weakest",
        translation_key="rf_signal_weakest",
        icon="mdi:signal-cellular-1",
        value=lambda status: _signal(status, min),
    ),
    ControllerSensorDescription(
        key="rf_signal_strongest",
        translation_key="rf_signal_strongest",
        icon="mdi:signal-cellular-3",
        value=lambda status: _signal(status, max),
    ),
    ControllerSensorDescription(
        key="clock_offset",
        translation_key="clock_offset",
        icon="mdi:clock-alert-outline",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        device_class=SensorDeviceClass.DURATION,
        value=_clock_offset,
    ),
    ControllerSensorDescription(
        key="time_server",
        translation_key="time_server",
        icon="mdi:clock-check-outline",
        value=lambda status: status.time_server,
    ),
    ControllerSensorDescription(
        key="project_revision",
        translation_key="project_revision",
        icon="mdi:file-tree",
        value=lambda status: status.project_major_revision,
    ),
    ControllerSensorDescription(
        key="ip_address",
        translation_key="ip_address",
        icon="mdi:ip-network",
        value=lambda status: status.ip_address,
    ),
    ControllerSensorDescription(
        key="gateway",
        translation_key="gateway",
        icon="mdi:router-network",
        value=lambda status: status.gateway,
    ),
    ControllerSensorDescription(
        key="dns_servers",
        translation_key="dns_servers",
        icon="mdi:dns",
        value=lambda status: ", ".join(status.dns_servers) or None,
    ),
)


class IHCControllerSensor(SensorEntity):
    """One read-only fact about the controller, on the controller's own device."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    entity_description: ControllerSensorDescription

    def __init__(self, serial: str, status: ControllerStatus, description: ControllerSensorDescription) -> None:
        """Take the value once: nothing here changes without someone visiting the controller."""
        self.entity_description = description
        self._attr_unique_id = f"{serial}-controller-{description.key}"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, serial)})
        self._attr_native_value = description.value(status)
