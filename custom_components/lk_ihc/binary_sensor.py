"""IHC binary sensors: movement, door contacts, smoke, water and the like."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util.enum import try_parse_enum

from . import IHCConfigEntry
from .catalog import ResourceRole
from .entity import IHCEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: IHCConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    """Add a binary sensor for every sensor input in the installation."""
    data = entry.runtime_data
    async_add_entities(
        IHCBinarySensor(
            data.connection,
            product,
            resource,
            primary=resource.index == 1,
            controller_device_id=data.controller_device_id,
        )
        for product, resource in data.project.resources
        if resource.role is ResourceRole.BINARY_SENSOR
    )


class IHCBinarySensor(IHCEntity, BinarySensorEntity):
    """An input on an IHC product, read as on or off."""

    _attr_is_on = False

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Take the device class from the catalogue."""
        super().__init__(*args, **kwargs)
        self._attr_device_class = try_parse_enum(BinarySensorDeviceClass, self._resource.device_class)

    @callback
    def _apply_value(self, value: Any) -> None:
        """Handle an on/off value, inverted for the products that report the opposite."""
        self._attr_is_on = not bool(value) if self._resource.inverting else bool(value)
