"""IHC wall switch keys, as events an automation can trigger on.

The built-in IHC integration only looks for outputs and sensors, so the keys people actually press
are invisible to Home Assistant. Every key is an input resource that goes true while it is held, so
each one becomes an event entity. It fires on press, and on the gestures gestures.py works out from
the key going down and up - a single, double or long press - so an automation can pick the one it
wants. The key keeps doing whatever the installation already uses it for; this only listens.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from homeassistant.components.event import EventDeviceClass, EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_call_later

from . import IHCConfigEntry
from .catalog import ResourceRole
from .const import BUTTON_EVENT_TYPES, CONF_EXPOSE_BUTTONS, DEFAULT_EXPOSE_BUTTONS
from .entity import IHCEntity
from .gestures import KeyGestures


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
    _attr_event_types = BUTTON_EVENT_TYPES
    # Names the event types in the user's language in the automation editor's list.
    _attr_translation_key = "key"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Name the entity after the key, falling back to its position on the product."""
        super().__init__(*args, **kwargs)
        if not self._resource.name:
            self._attr_name = f"Key {self._resource.index}"
        self._first_value_seen = False
        self._gestures = KeyGestures(self._fire, self._schedule)

    async def async_will_remove_from_hass(self) -> None:
        """Stop the gesture timers, so none fires on an entity that is gone."""
        self._gestures.cancel()
        await super().async_will_remove_from_hass()

    @callback
    def _handle_value(self, value: Any) -> None:
        """Pass the key going down and up on, and ignore the value the subscription starts with."""
        if not self._first_value_seen:
            # The controller reports the current state when the subscription starts. A key that
            # happens to be held at that moment must not look like a press.
            self._first_value_seen = True
            return
        if value:
            self._gestures.down()
        else:
            self._gestures.up()

    @callback
    def _fire(self, event_type: str) -> None:
        """Fire one event."""
        self._trigger_event(event_type)
        if self.hass is not None:
            self.async_write_ha_state()

    @callback
    def _schedule(self, seconds: float, action: Callable[[], None]) -> Callable[[], None]:
        """Call action in some seconds, and return what cancels it."""
        # Marked as a callback, or Home Assistant runs it in a worker thread, where the entity may
        # not write its state.
        return async_call_later(self.hass, seconds, callback(lambda _now: action()))

    @callback
    def _apply_value(self, value: Any) -> None:
        """Not used: an event entity has no state of its own to keep."""
