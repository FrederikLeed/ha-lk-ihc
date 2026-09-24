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
from .controller_sensor import SENSORS, IHCControllerSensor
from .entity import IHCEntity
from .logicentity import IHCLogicEntity

_UNITS = {SensorDeviceClass.TEMPERATURE: UnitOfTemperature.CELSIUS}


async def async_setup_entry(
    hass: HomeAssistant, entry: IHCConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    """Add a sensor for every measured value, and the controller's own diagnostics."""
    data = entry.runtime_data
    async_add_entities(
        IHCControllerSensor(data.connection.serial_number, data.status, description)
        for description in SENSORS
        # A controller that does not implement a service reports nothing for it, and an entity
        # that would only ever say "unknown" is worse than no entity at all.
        if description.value(data.status) is not None
    )
    async_add_entities(IHCEnumSensor(data.connection, resource) for resource in data.logic.enums)
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


class IHCEnumSensor(IHCLogicEntity, SensorEntity):
    """An enumeration in the controller's logic, showing its current named state.

    One in a function block's settings is how the block was set up ("PIR function: step high/off")
    and changes only when the project is reprogrammed, so it starts disabled, like the flags. One in
    the block's outputs says how things stand now ("Dimmer status: off"), and stays enabled.
    """

    _ICONS = {"settings": "mdi:cog", "outputs": "mdi:export"}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Offer the enum's names as options, so the value reads as a known state."""
        super().__init__(*args, **kwargs)
        self._attr_icon = self._ICONS.get(self._resource.section, "mdi:format-list-bulleted")
        self._attr_entity_registry_enabled_default = self._resource.section != "settings"
        if self._resource.options:
            self._attr_options = list(self._resource.options)
            self._attr_device_class = SensorDeviceClass.ENUM

    @callback
    def _apply_value(self, value: Any) -> None:
        """Store the enum's current name; ihcsdk reports it as the option string."""
        # Stripped like the options are when the project is read, or a name with a trailing space
        # is not among them and the state cannot be written.
        name = value.strip() if isinstance(value, str) else ""
        self._attr_native_value = name or None
