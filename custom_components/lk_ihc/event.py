"""IHC wall switch keys, as events an automation can trigger on.

The built-in IHC integration only looks for outputs and sensors, so the keys people actually press
are invisible to Home Assistant. Every key is an input resource that goes true while it is held, so
each one becomes an event entity that fires on press. The key keeps doing whatever the installation
already uses it for; this only listens.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.event import EventDeviceClass, EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import IHCConfigEntry
from .catalog import ResourceRole
from .const import CONF_EXPOSE_BUTTONS, DEFAULT_EXPOSE_BUTTONS, EVENT_PRESS
from .entity import IHCEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: IHCConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    """Add an event entity for every key on every wall switch."""
    if not entry.options.get(CONF_EXPOSE_BUTTONS, DEFAULT_EXPOSE_BUTTONS):
        return
    data = entry.runtime_data
    async_add_entities(
        IHCButtonEvent(data.connection, product, resource, controller_device_id=data.controller_device_id)
        for product, resource in data.project.resources
        if resource.role is ResourceRole.BUTTON
    )


class IHCButtonEvent(IHCEntity, EventEntity):
    """One key on an IHC wall switch."""

    _attr_device_class = EventDeviceClass.BUTTON
    _attr_event_types = [EVENT_PRESS]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Name the entity after the key, falling back to its position on the product."""
        super().__init__(*args, **kwargs)
        if not self._resource.name:
            self._attr_name = f"Key {self._resource.index}"
        self._first_value_seen = False

    @callback
    def _handle_value(self, value: Any) -> None:
        """Fire on a press, and ignore the release and the value the subscription starts with."""
        if not self._first_value_seen:
            # The controller reports the current state when the subscription starts. A key that
            # happens to be held at that moment must not look like a press.
            self._first_value_seen = True
            return
        if not value:
            return
        self._trigger_event(EVENT_PRESS)
        if self.hass is not None:
            self.async_write_ha_state()

    @callback
    def _apply_value(self, value: Any) -> None:
        """Not used: an event entity has no state of its own to keep."""
