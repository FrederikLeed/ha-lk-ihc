"""Read an IHC project file into the products and resources Home Assistant can use.

The controller stores the whole installation as one XML document: groups (rooms), the products
placed in them, and for each product the resources that carry its values. A resource id is what
the controller notifies on and what a command is sent to, so everything here exists to answer two
questions: which resources are worth an entity, and what should that entity be called.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from defusedxml import ElementTree

from .catalog import ResourceRole, role_for

# Nodes that hold a value we can read or write. Everything else in a product is structure.
_INPUT_TAGS = ("dataline_input", "airlink_input", "rf_input", "rs485_input")
_OUTPUT_TAGS = ("dataline_output", "airlink_relay", "airlink_dimming", "rf_output", "rs485_output")
_VALUE_TAGS = (*_INPUT_TAGS, *_OUTPUT_TAGS, "resource_temperature", "resource_float", "resource_integer")

_PRODUCT_TAGS = ("product_dataline", "product_airlink", "product_rf", "product_rs485")


def _int_id(value: str | None) -> int | None:
    """Return an IHC id as a number. They are written as _0x1a2b3c in the project file."""
    if not value:
        return None
    try:
        return int(value.strip("_"), 0)
    except ValueError:
        return None


def _text(value: str | None) -> str:
    """Return an attribute stripped, empty when it is missing. IHC text often has stray spaces."""
    return (value or "").strip()


@dataclass(frozen=True, slots=True)
class Resource:
    """One value inside a product: an input, an output or a measurement."""

    ihc_id: int
    name: str
    tag: str
    role: ResourceRole
    # Position of this resource among the product's resources of the same tag, from 1.
    index: int = 1
    dimmable: bool = False
    device_class: str | None = None
    inverting: bool = False
    enabled_default: bool = True

    @property
    def is_input(self) -> bool:
        """Return whether the resource is something the installation writes to, not us."""
        return self.tag in _INPUT_TAGS


@dataclass(frozen=True, slots=True)
class Product:
    """One physical product, which becomes one device in Home Assistant."""

    product_id: int
    identifier: str
    name: str
    note: str
    position: str
    group: str
    model: str
    resources: tuple[Resource, ...] = ()

    @property
    def device_name(self) -> str:
        """Return the name to show for the device: what it is, and where it sits."""
        if self.position:
            return f"{self.name} ({self.position})"
        return self.name or f"IHC product {self.product_id}"


@dataclass(slots=True)
class Project:
    """A parsed IHC project."""

    products: list[Product] = field(default_factory=list)
    groups: list[str] = field(default_factory=list)

    @property
    def resources(self) -> list[tuple[Product, Resource]]:
        """Return every resource with the product it belongs to."""
        return [(product, resource) for product in self.products for resource in product.resources]

    def counts(self) -> dict[str, int]:
        """Return how many resources fall into each role, for diagnostics and the setup summary."""
        counts: dict[str, int] = {}
        for _product, resource in self.resources:
            counts[resource.role.value] = counts.get(resource.role.value, 0) + 1
        return counts


def parse_project(xml: str | bytes) -> Project:
    """Parse the project XML the controller serves into products and resources.

    Unknown products are kept: their outputs still become switches and their inputs still become
    (disabled) sensors, because a house rarely holds only the products a catalogue knows about.
    """
    root = ElementTree.fromstring(xml)
    project = Project()
    for group in root.iter("group"):
        group_name = _text(group.get("name"))
        project.groups.append(group_name)
        for element in group.iter():
            if element.tag not in _PRODUCT_TAGS:
                continue
            product = _parse_product(element, group_name)
            if product is not None:
                project.products.append(product)
    return project


def _parse_product(element: Any, group_name: str) -> Product | None:
    """Return one product with its resources, or None when it carries no id."""
    product_id = _int_id(element.get("id"))
    if product_id is None:
        return None
    identifier = _text(element.get("product_identifier"))
    resources: list[Resource] = []
    seen_per_tag: dict[str, int] = {}
    for node in element.iter():
        if node.tag not in _VALUE_TAGS:
            continue
        # A "setting" node configures the product; it is not a value to expose.
        if node.get("setting") == "yes":
            continue
        ihc_id = _int_id(node.get("id"))
        if ihc_id is None:
            continue
        index = seen_per_tag.get(node.tag, 0) + 1
        seen_per_tag[node.tag] = index
        spec = role_for(identifier, node.tag, index)
        resources.append(
            Resource(
                ihc_id=ihc_id,
                name=_text(node.get("name")),
                tag=node.tag,
                role=spec.role,
                index=index,
                dimmable=spec.dimmable,
                device_class=spec.device_class,
                inverting=spec.inverting,
                enabled_default=spec.enabled_default,
            )
        )
    if not resources:
        return None
    return Product(
        product_id=product_id,
        identifier=identifier,
        name=_text(element.get("name")),
        note=_text(element.get("note")),
        position=_text(element.get("position")),
        group=group_name,
        model=identifier.lstrip("_") or element.tag.removeprefix("product_"),
        resources=tuple(resources),
    )
