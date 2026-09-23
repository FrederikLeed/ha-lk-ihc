"""The base every LK IHC entity is built on."""

from __future__ import annotations

from typing import Any

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .controller import IHCConnection
from .project import Product, Resource


class IHCEntity(Entity):
    """An entity for one IHC resource, belonging to the device of its product."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        connection: IHCConnection,
        product: Product,
        resource: Resource,
        *,
        primary: bool = False,
        controller_device_id: str = "",
    ) -> None:
        """Set up naming, identity and the device this entity belongs to.

        A product's main resource carries the device's name (the light is "Lamp outlet (in the
        ceiling)"), while further resources name themselves (a key is "Left key" on that device).
        """
        self._connection = connection
        self._product = product
        self._resource = resource
        serial = connection.serial_number
        self._attr_unique_id = f"{serial}-{resource.ihc_id}"
        self._attr_entity_registry_enabled_default = resource.enabled_default
        if resource.icon:
            self._attr_icon = resource.icon
        if primary or not resource.name:
            self._attr_name = None
        else:
            self._attr_name = resource.name
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{serial}-{product.product_id}")},
            name=product.device_name,
            manufacturer="LK",
            model=product.model,
            model_id=product.model_id or None,
            suggested_area=product.group or None,
            via_device_id=controller_device_id,
        )

    async def async_added_to_hass(self) -> None:
        """Start listening for values from the controller."""
        await self._connection.async_subscribe(self._resource.ihc_id, self._handle_value)

    @callback
    def _handle_value(self, value: Any) -> None:
        """Handle a new value for this resource."""
        self._apply_value(value)
        if self.hass is not None:
            self.async_write_ha_state()

    @callback
    def _apply_value(self, value: Any) -> None:
        """Store the value. Each platform decides what its state means."""
        raise NotImplementedError

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose where this entity comes from, which is what you need when reading a project."""
        attributes = {"ihc_id": self._resource.ihc_id, "ihc_product": self._product.name}
        if self._product.note:
            attributes["ihc_note"] = self._product.note
        if self._product.position:
            attributes["ihc_position"] = self._product.position
        # What else can change this entity behind our back. The controller runs its own logic,
        # so a relay moving without a Home Assistant call is normal, not a fault - this says why.
        if self._product.controlled_by:
            attributes["ihc_controlled_by"] = list(self._product.controlled_by)
        if self._product.function_blocks:
            attributes["ihc_function_block"] = list(self._product.function_blocks)
        return attributes
