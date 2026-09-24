"""The base for a logic-resource entity: a flag or enum shown on the controller device.

Unlike a product entity, a logic resource has no product and belongs to no room - it is part of the
controller's own logic. So it hangs on the controller device, in the diagnostic category, and takes
its value the same way every other entity does: by subscribing to the controller's notifications.
"""

from __future__ import annotations

from typing import Any

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity, EntityCategory

from .const import DOMAIN
from .controller import IHCConnection
from .logic import LogicResource


class IHCLogicEntity(Entity):
    """One logic resource on the controller device, read live and never written."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, connection: IHCConnection, resource: LogicResource) -> None:
        """Attach to the controller device and name the entity after the resource."""
        self._connection = connection
        self._resource = resource
        serial = connection.serial_number
        self._attr_unique_id = f"{serial}-logic-{resource.ihc_id}"
        self._attr_name = resource.name or f"IHC {resource.kind} {resource.ihc_id}"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, serial)})

    async def async_added_to_hass(self) -> None:
        """Start listening for this resource's value."""
        await self._connection.async_subscribe(self._resource.ihc_id, self._handle_value)

    @callback
    def _handle_value(self, value: Any) -> None:
        """Store the value and update, once the entity is on the bus."""
        self._apply_value(value)
        if self.hass is not None:
            self.async_write_ha_state()

    @callback
    def _apply_value(self, value: Any) -> None:
        """Each platform decides what its value means."""
        raise NotImplementedError

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Say where the resource sits in the project and what it is."""
        attributes = {"ihc_id": self._resource.ihc_id, "ihc_kind": self._resource.kind}
        if self._resource.group:
            attributes["ihc_group"] = self._resource.group
        if self._resource.block:
            attributes["ihc_function_block"] = self._resource.block
        return attributes
