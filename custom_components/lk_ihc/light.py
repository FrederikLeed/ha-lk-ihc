"""IHC lights: lamp outlets and dimmers."""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import ATTR_BRIGHTNESS, ColorMode, LightEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import IHCConfigEntry
from .catalog import ResourceRole
from .entity import IHCEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: IHCConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    """Add a light for every lamp outlet and dimmer in the installation."""
    data = entry.runtime_data
    async_add_entities(
        IHCLight(data.connection, product, resource, primary=True, controller_device_id=data.controller_device_id)
        for product, resource in data.project.resources
        if resource.role is ResourceRole.LIGHT
    )


class IHCLight(IHCEntity, LightEntity):
    """A light on an IHC output.

    A dimmer's resource holds a level from 0 to 100, a plain outlet holds on or off. The project
    file says which it is, and the first value from the controller confirms it.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Set the color mode from what the product can do."""
        super().__init__(*args, **kwargs)
        self._dimmable = self._resource.dimmable
        self._attr_color_mode = ColorMode.BRIGHTNESS if self._dimmable else ColorMode.ONOFF
        self._attr_supported_color_modes = {self._attr_color_mode}
        self._attr_is_on = False
        self._attr_brightness = None

    @callback
    def _apply_value(self, value: Any) -> None:
        """Handle a level or an on/off value from the controller."""
        if isinstance(value, bool):
            self._attr_is_on = value
            return
        level = int(value)
        self._attr_is_on = level > 0
        if self._dimmable:
            self._attr_brightness = round(level * 255 / 100) if level else None

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on, at a brightness when it can dim."""
        if not self._dimmable:
            await self._connection.async_set_bool(self._resource.ihc_id, True)
            return
        brightness = kwargs.get(ATTR_BRIGHTNESS, self._attr_brightness or 255)
        await self._connection.async_set_int(self._resource.ihc_id, round(brightness * 100 / 255))

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""
        if self._dimmable:
            await self._connection.async_set_int(self._resource.ihc_id, 0)
        else:
            await self._connection.async_set_bool(self._resource.ihc_id, False)
