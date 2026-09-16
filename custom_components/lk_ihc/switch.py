"""IHC switches: relays and plug outlets."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import IHCConfigEntry
from .catalog import ResourceRole
from .entity import IHCEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: IHCConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    """Add a switch for every relay in the installation."""
    data = entry.runtime_data
    async_add_entities(
        IHCSwitch(data.connection, product, resource, primary=True, controller_device_id=data.controller_device_id)
        for product, resource in data.project.resources
        if resource.role is ResourceRole.SWITCH
    )


class IHCSwitch(IHCEntity, SwitchEntity):
    """A relay output on an IHC product."""

    _attr_is_on = False

    @callback
    def _apply_value(self, value: Any) -> None:
        """Handle an on/off value from the controller."""
        self._attr_is_on = bool(value)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Close the relay."""
        await self._connection.async_set_bool(self._resource.ihc_id, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Open the relay."""
        await self._connection.async_set_bool(self._resource.ihc_id, False)
