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
from .logicentity import IHCLogicEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: IHCConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    """Add a binary sensor for every sensor input in the installation."""
    data = entry.runtime_data
    async_add_entities(IHCFlagSensor(data.connection, resource) for resource in data.logic.flags)
    async_add_entities(IHCBlockOutputSensor(data.connection, resource) for resource in data.logic.outputs)
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


class IHCFlagSensor(IHCLogicEntity, BinarySensorEntity):
    """A flag in the controller's logic, read as on or off.

    Disabled by default: an installation has many internal flags, and most are plumbing only. They
    are here for when a flag turns out to explain something, without cluttering the entity list for
    everyone who does not need them.
    """

    _attr_is_on = False
    _attr_entity_registry_enabled_default = False

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Give the flag an icon; it has no device class."""
        super().__init__(*args, **kwargs)
        self._attr_icon = "mdi:flag"

    @callback
    def _apply_value(self, value: Any) -> None:
        """Store the flag's on/off state."""
        self._attr_is_on = bool(value)


class IHCBlockOutputSensor(IHCFlagSensor):
    """An output of a function block in the controller's logic, read as on or off.

    Disabled by default, like the flags: most outputs are pulses that feed a product. The few that
    say what no product shows - the alarm is armed, a contact loop is open - are worth switching on.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Mark it as something a block puts out."""
        super().__init__(*args, **kwargs)
        self._attr_icon = "mdi:export"
