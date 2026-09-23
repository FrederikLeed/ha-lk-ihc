"""Read the installation's logic resources - the flags and enums the controller works with.

A product carries physical inputs and outputs. Beside them the project holds resources that exist
only inside the controller's own logic: flags it sets and tests, and enumerations that pick between
named states. They are not wired to anything you can touch, so Home Assistant never showed them,
and until now the only way to know a flag's state was to infer it from what the lights did.

These are read-only here on purpose. A flag or an enum is an input to logic the controller runs;
writing one from Home Assistant would reach into that logic blind, and ihcsdk has no setter for an
enum in any case. So they are exposed to be seen, not driven, and they live on the controller
device as diagnostics rather than pretending to be hardware in a room.

Timers and scenes are deliberately left out: a timer reads as a bare countdown that is almost
always zero, and a scene has no readable value at all (activation is a separate mechanism). Neither
tells you anything worth an entity.
"""

from __future__ import annotations

from dataclasses import dataclass, field

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
    """One logic resource: a flag (on/off) or an enum (one of several named states)."""

    ihc_id: int
    name: str
    kind: str  # "flag" or "enum"
    group: str = ""
    # For an enum, the names it can take, in project order. Empty for a flag.
    options: tuple[str, ...] = ()


@dataclass(slots=True)
class Logic:
    """The installation's flags and enums."""

    flags: list[LogicResource] = field(default_factory=list)
    enums: list[LogicResource] = field(default_factory=list)

    @property
    def resources(self) -> list[LogicResource]:
        """Every logic resource, flags and enums together."""
        return [*self.flags, *self.enums]


def parse_logic(xml: str | bytes) -> Logic:
    """Read the flags and enums from the project.

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
        for element in group.iter():
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
    return logic
