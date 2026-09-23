"""Read an IHC project file into the products and resources Home Assistant can use.

The controller stores the whole installation as one XML document: groups (rooms), the products
placed in them, and for each product the resources that carry its values. A resource id is what
the controller notifies on and what a command is sent to, so everything here exists to answer two
questions: which resources are worth an entity, and what should that entity be called.

The file also holds the installation's own logic: function blocks (a wall switch toggling a relay,
a PIR lighting a lamp) and the links that wire them to products. Home Assistant never runs that
logic - the controller does - but knowing it answers the question a project file otherwise leaves
open: when this relay changes and Home Assistant did not ask for it, what did? So the links are
followed once at setup and each product is told which products can drive it, and through which
block.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from defusedxml import ElementTree

from .catalog import ResourceRole, icon_for, model_name, role_for

# Nodes that hold a value we can read or write. Everything else in a product is structure.
_INPUT_TAGS = ("dataline_input", "airlink_input", "rf_input", "rs485_input")
_OUTPUT_TAGS = ("dataline_output", "airlink_relay", "airlink_dimming", "rf_output", "rs485_output")
_VALUE_TAGS = (*_INPUT_TAGS, *_OUTPUT_TAGS, "resource_temperature", "resource_float", "resource_integer")

_PRODUCT_TAGS = ("product_dataline", "product_airlink", "product_rf", "product_rs485")

# A link is two halves: the source carries a "link" attribute naming the id of the matching
# half inside whatever it feeds. Both halves sit inside the product or function block they
# belong to, so the wiring is read by looking at who owns each half.
_LINK_FROM_TAG = "link_from_resource"
_LINK_TO_TAG = "link_to_resource"


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
    icon: str | None = None
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
class FunctionBlock:
    """One piece of logic the controller runs by itself, such as "toggle with timer"."""

    block_id: int
    name: str
    group: str

    @property
    def short_name(self) -> str:
        """Return the name without the catalogue number IHC prefixes it with ("1.1.01. ")."""
        _number, _, rest = self.name.partition(". ")
        return (rest or self.name).strip()


@dataclass(frozen=True, slots=True)
class Product:
    """One physical product, which becomes one device in Home Assistant."""

    product_id: int
    identifier: str
    name: str
    note: str
    position: str
    group: str
    # What the product is, in words, and the identifier the project file uses for it.
    model: str
    model_id: str
    resources: tuple[Resource, ...] = ()
    # Products whose links reach this one, and the function blocks the signal passes through.
    # Both are names, not ids: this exists to be read by a person looking at an entity.
    controlled_by: tuple[str, ...] = ()
    function_blocks: tuple[str, ...] = ()

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
    function_blocks: list[FunctionBlock] = field(default_factory=list)

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
    # Who owns each element id, so a link half can be traced back to its product or block.
    owner_of: dict[str, Any] = {}
    for group in root.iter("group"):
        group_name = _text(group.get("name"))
        project.groups.append(group_name)
        for element in group.iter():
            if element.tag in _PRODUCT_TAGS:
                product = _parse_product(element, group_name)
                if product is not None:
                    project.products.append(product)
                _claim(element, element, owner_of)
            elif element.tag == "functionblock":
                block_id = _int_id(element.get("id"))
                if block_id is not None:
                    project.function_blocks.append(
                        FunctionBlock(block_id=block_id, name=_text(element.get("name")), group=group_name)
                    )
                _claim(element, element, owner_of)
    _apply_wiring(root, project, owner_of)
    return project


def _claim(owner: Any, element: Any, owner_of: dict[str, Any]) -> None:
    """Record that every id below this product or block belongs to it."""
    for node in element.iter():
        node_id = node.get("id")
        if node_id:
            owner_of[node_id] = owner


def _describe(element: Any) -> str:
    """Return a readable name for a product or function block, as a person would say it."""
    name = _text(element.get("name"))
    position = _text(element.get("position"))
    if element.tag == "functionblock":
        _number, _, rest = name.partition(". ")
        return (rest or name).strip()
    return f"{name} ({position})" if position else name


def _apply_wiring(root: Any, project: Project, owner_of: dict[str, Any]) -> None:
    """Follow the project's links and tell each product what can drive it.

    A link's source half names the id of its other half, which sits inside the thing it feeds.
    Most chains run switch -> function block -> relay, so a block in the middle is stepped over
    and reported separately: what a person wants to know is which switch works this lamp, with
    the block as the reason it does.
    """
    edges: dict[int, list[Any]] = {}
    blocks: dict[int, Any] = {}
    for link in root.iter(_LINK_FROM_TAG):
        source = owner_of.get(link.get("id"))
        target = owner_of.get(_text(link.get("link")))
        if source is None or target is None or source is target:
            continue
        target_id = _int_id(target.get("id"))
        if target_id is None:
            continue
        edges.setdefault(target_id, []).append(source)
        if target.tag == "functionblock":
            blocks[target_id] = target

    for index, product in enumerate(project.products):
        sources: list[str] = []
        via: list[str] = []
        for source in edges.get(product.product_id, ()):
            source_id = _int_id(source.get("id"))
            if source.tag == "functionblock":
                # The block is the reason, not the origin: keep walking to what feeds it.
                via.append(_describe(source))
                for upstream in edges.get(source_id, ()) if source_id is not None else ():
                    if upstream.tag != "functionblock":
                        sources.append(_describe(upstream))
            else:
                sources.append(_describe(source))
        if sources or via:
            project.products[index] = replace(
                product,
                controlled_by=tuple(dict.fromkeys(s for s in sources if s)),
                function_blocks=tuple(dict.fromkeys(v for v in via if v)),
            )


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
                icon=icon_for(identifier, spec.role),
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
        model=model_name(identifier, _text(element.get("name")) or element.tag.removeprefix("product_")),
        model_id=identifier.lstrip("_"),
        resources=tuple(resources),
    )
