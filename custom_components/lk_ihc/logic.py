"""Read the installation's logic resources - the flags and enums the controller works with.

A product carries physical inputs and outputs. Beside them the project holds resources that exist
only inside the controller's own logic: flags it sets and tests, and enumerations that pick between
named states. They are not wired to anything you can touch, so Home Assistant never showed them,
and until now the only way to know a flag's state was to infer it from what the lights did.

A function block's outputs belong here too. Many are pulses that feed a product, but some say what
the controller's logic has concluded and no product shows: whether the alarm is armed, whether a
contact loop is open, whether a dimmer is on.

These are read-only here on purpose. A flag or an enum is an input to logic the controller runs;
writing one from Home Assistant would reach into that logic blind, and ihcsdk has no setter for an
enum in any case. So they are exposed to be seen, not driven, and they live on the controller
device as diagnostics rather than pretending to be hardware in a room.

Timers and scenes are deliberately left out: a timer reads as a bare countdown that is almost
always zero, and a scene has no readable value at all (activation is a separate mechanism). Neither
tells you anything worth an entity.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from defusedxml import ElementTree


def _int_id(value: str | None) -> int | None:
    """Return an IHC id as a number, written _0x1a2b3c in the project file."""
    if not value:
        return None
    try:
        return int(value.strip("_"), 0)
    except ValueError:
        return None


def _text(value: str | None) -> str:
    """Return an attribute stripped, empty when missing."""
    return (value or "").strip()


@dataclass(frozen=True, slots=True)
class LogicResource:
    """One logic resource: a flag or a block output (on/off), or an enum (one of several named states)."""

    ihc_id: int
    name: str
    kind: str  # "flag", "enum" or "output"
    group: str = ""
    # For an enum, the names it can take, in project order. Empty for a flag.
    options: tuple[str, ...] = ()
    # For a block output, the block it belongs to, without its catalogue number.
    block: str = ""


@dataclass(slots=True)
class Logic:
    """The installation's flags, enums and function block outputs."""

    flags: list[LogicResource] = field(default_factory=list)
    enums: list[LogicResource] = field(default_factory=list)
    outputs: list[LogicResource] = field(default_factory=list)

    @property
    def resources(self) -> list[LogicResource]:
        """Every logic resource together."""
        return [*self.flags, *self.enums, *self.outputs]


def _outside_programs(element: Any) -> Iterator[Any]:
    """Every element below this one, leaving out the function blocks' programs.

    A program writes the values it tests and sets as resources of their own: "if the mode is Last
    level" holds a resource_enum with the value Last level. Those are constants in the program,
    not resources with a state, and IHC Visual names them "Enumerator" or nothing at all.
    """
    for child in element:
        if child.tag == "programs":
            continue
        yield child
        yield from _outside_programs(child)


def parse_logic(xml: str | bytes) -> Logic:
    """Read the flags, enums and function block outputs from the project.

    Enum options come from a shared definition the resource points at by `typedef`, so the
    definitions are collected first and then looked up. A resource whose definition is missing
    still becomes an entity - it just cannot list its options.
    """
    root = ElementTree.fromstring(xml)

    enum_options: dict[str, tuple[str, ...]] = {}
    for definition in root.iter("enum_definition"):
        definition_id = definition.get("id")
        if not definition_id:
            continue
        values = tuple(_text(value.get("name")) for value in definition if value.tag == "enum_value")
        enum_options[definition_id] = values

    logic = Logic()
    for group in root.iter("group"):
        group_name = _text(group.get("name"))
        for element in _outside_programs(group):
            ihc_id = _int_id(element.get("id"))
            if ihc_id is None:
                continue
            if element.tag == "resource_flag":
                logic.flags.append(
                    LogicResource(ihc_id=ihc_id, name=_text(element.get("name")), kind="flag", group=group_name)
                )
            elif element.tag == "resource_enum":
                logic.enums.append(
                    LogicResource(
                        ihc_id=ihc_id,
                        name=_text(element.get("name")),
                        kind="enum",
                        group=group_name,
                        options=enum_options.get(element.get("typedef", ""), ()),
                    )
                )
        for block in group.iter("functionblock"):
            # Without its catalogue number ("6.2.01.b. "), as FunctionBlock.short_name has it.
            number, _, rest = _text(block.get("name")).partition(". ")
            block_name = (rest or number).strip()
            for element in block.findall("outputs/resource_output"):
                ihc_id = _int_id(element.get("id"))
                if ihc_id is not None:
                    logic.outputs.append(
                        LogicResource(
                            ihc_id=ihc_id,
                            name=_text(element.get("name")),
                            kind="output",
                            group=group_name,
                            block=block_name,
                        )
                    )
    return logic


# Every tag whose element is a resource the controller can be asked to set. Products carry the
# first group; the controller's own logic carries the rest (timers, flags, enums, scenes).
_ADDRESSABLE_TAGS = frozenset(
    {
        "dataline_input",
        "dataline_output",
        "airlink_input",
        "airlink_relay",
        "airlink_dimming",
        "rf_input",
        "rf_output",
        "rs485_input",
        "rs485_output",
    }
)


def parse_resource_ids(xml: str | bytes) -> set[int]:
    """Return the id of every resource in the project that a command could be sent to.

    This is wider than the set that becomes entities: a timer inside a function block has no entity,
    but an action may still want to set it. It is still bounded by the project - an id that is not
    in the installation is not in this set, and a command to it is refused.
    """
    root = ElementTree.fromstring(xml)
    ids: set[int] = set()
    for element in root.iter():
        if element.tag in _ADDRESSABLE_TAGS or element.tag.startswith("resource_"):
            ihc_id = _int_id(element.get("id"))
            if ihc_id is not None:
                ids.add(ihc_id)
    return ids
