"""IHC sensors: temperature and the other measured values."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util.enum import try_parse_enum

from . import IHCConfigEntry
from .catalog import ResourceRole
from .entity import IHCEntity

_UNITS = {SensorDeviceClass.TEMPERATURE: UnitOfTemperature.CELSIUS}


async def async_setup_entry(
    hass: HomeAssistant, entry: IHCConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    """Add a sensor for every measured value in the installation."""
    data = entry.runtime_data
    async_add_entities(
        IHCSensor(
            data.connection,
            product,
            resource,
            primary=resource.index == 1,
            controller_device_id=data.controller_device_id,
        )
        for product, resource in data.project.resources
        if resource.role is ResourceRole.SENSOR
    )


class IHCSensor(IHCEntity, SensorEntity):
    """A measured value from an IHC product."""

    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Take the device class and its unit from the catalogue."""
        super().__init__(*args, **kwargs)
        self._attr_device_class = try_parse_enum(SensorDeviceClass, self._resource.device_class)
        self._attr_native_unit_of_measurement = _UNITS.get(self._attr_device_class)

    @callback
    def _apply_value(self, value: Any) -> None:
        """Handle a measured value, ignoring anything that is not a number."""
        self._attr_native_value = value if isinstance(value, (int, float)) and not isinstance(value, bool) else None
