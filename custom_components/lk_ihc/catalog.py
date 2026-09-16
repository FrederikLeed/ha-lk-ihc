"""What each IHC product is, and what its resources should become in Home Assistant.

The project file names a product only by an identifier such as `_0x2101`. This module turns that
into a decision: this resource is a light, that one is a relay, this one is a key on a wall switch.

Two sources feed it. The product identifiers and their roles come from Home Assistant's own IHC
auto setup list, which is the accumulated knowledge of that integration. The wall switch products
are added here, because the built-in integration leaves them out: they are inputs, and it only
looks for outputs and sensors. Those keys are the most useful thing an IHC installation can give
an automation, so this integration exposes each one as an event entity.

Anything unknown still gets a home: outputs become switches, inputs become binary sensors that are
disabled until someone enables them, so a house is never silently half missing.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ResourceRole(StrEnum):
    """What a resource becomes in Home Assistant."""

    LIGHT = "light"
    SWITCH = "switch"
    BINARY_SENSOR = "binary_sensor"
    BUTTON = "button"
    SENSOR = "sensor"


@dataclass(frozen=True, slots=True)
class RoleSpec:
    """The role of one resource, with what the platform needs to know about it."""

    role: ResourceRole
    dimmable: bool = False
    device_class: str | None = None
    inverting: bool = False
    # Entities that are only interesting once someone goes looking are created disabled.
    enabled_default: bool = True


# Product identifier -> what its resources are. Names are the LK product names, kept in English.
@dataclass(frozen=True, slots=True)
class ProductSpec:
    """A known product: its model name and what each kind of resource on it means."""

    model: str
    outputs: RoleSpec | None = None
    inputs: RoleSpec | None = None


_LIGHT = RoleSpec(ResourceRole.LIGHT)
_DIMMER = RoleSpec(ResourceRole.LIGHT, dimmable=True)
_RELAY = RoleSpec(ResourceRole.SWITCH)
_KEY = RoleSpec(ResourceRole.BUTTON)
_TEMPERATURE = RoleSpec(ResourceRole.SENSOR, device_class="temperature")


def _sensor(device_class: str, *, inverting: bool = False) -> RoleSpec:
    return RoleSpec(ResourceRole.BINARY_SENSOR, device_class=device_class, inverting=inverting)


PRODUCTS: dict[str, ProductSpec] = {
    # Wall switches. Their keys are inputs, and every one can drive an automation.
    "_0x2101": ProductSpec("Dataline wall switch, 2 keys", inputs=_KEY),
    "_0x2102": ProductSpec("Dataline wall switch, 4 keys", inputs=_KEY),
    "_0x2103": ProductSpec("Dataline wall switch, 1 key", inputs=_KEY),
    "_0x4101": ProductSpec("Wireless wall switch, 2 keys", inputs=_KEY),
    "_0x4102": ProductSpec("Wireless wall switch, 4 keys", inputs=_KEY),
    "_0x4103": ProductSpec("Wireless mobile switch", inputs=_KEY),
    # Relays and outlets.
    "_0x2201": ProductSpec("Dataline plug outlet", outputs=_RELAY),
    "_0x2202": ProductSpec("Dataline lamp outlet", outputs=_LIGHT),
    "_0x4201": ProductSpec("Wireless plug outlet", outputs=_RELAY),
    "_0x4202": ProductSpec("Wireless lamp outlet", outputs=_LIGHT),
    "_0x4203": ProductSpec("Universal relay", outputs=_RELAY),
    "_0x4204": ProductSpec("Wireless mobile relay", outputs=_RELAY),
    # Dimmers.
    "_0x4301": ProductSpec("Wireless dimmer, mobile", outputs=_DIMMER),
    "_0x4302": ProductSpec("Wireless lamp outlet dimmer", outputs=_DIMMER),
    "_0x4303": ProductSpec("Wireless dimmer, mobile", outputs=_DIMMER),
    "_0x4304": ProductSpec("Wireless lamp outlet dimmer", outputs=_DIMMER),
    "_0x4305": ProductSpec("Wireless blind dimmer", outputs=_DIMMER),
    "_0x4306": ProductSpec("Wireless universal dimmer", outputs=_DIMMER),
    "_0x4307": ProductSpec("Wireless puck dimmer, 1 key", outputs=_DIMMER),
    "_0x4308": ProductSpec("Wireless puck dimmer, 2 keys", outputs=_DIMMER),
    "_0x4410": ProductSpec("RS485 LED dimmer channel", outputs=_DIMMER),
    # Combi products: an output plus keys on the same plate.
    "_0x4401": ProductSpec("Wireless combi dimmer, 2 keys", outputs=_DIMMER, inputs=_KEY),
    "_0x4402": ProductSpec("Wireless combi dimmer, 4 keys touch", outputs=_DIMMER, inputs=_KEY),
    "_0x4403": ProductSpec("Wireless combi relay, 2 keys", outputs=_RELAY, inputs=_KEY),
    "_0x4404": ProductSpec("Wireless combi relay, 4 keys", outputs=_RELAY, inputs=_KEY),
    "_0x4406": ProductSpec("Wireless combi dimmer, 4 keys", outputs=_DIMMER, inputs=_KEY),
    # Sensors.
    "_0x2109": ProductSpec("Magnet contact", inputs=_sensor("opening", inverting=True)),
    "_0x210a": ProductSpec("Smoke detector", inputs=_sensor("smoke")),
    "_0x210c": ProductSpec("Leak detector", inputs=_sensor("moisture")),
    "_0x210e": ProductSpec("PIR sensor", inputs=_sensor("motion")),
    "_0x210f": ProductSpec("PIR sensor, alarm", inputs=_sensor("motion")),
    "_0x2110": ProductSpec("Twilight sensor", inputs=_sensor("light")),
    "_0x2124": ProductSpec("Temperature sensor", inputs=_TEMPERATURE),
    "_0x2135": ProductSpec("Humidity and temperature sensor", inputs=_TEMPERATURE),
    "_0x2136": ProductSpec("Lux and temperature sensor", inputs=_TEMPERATURE),
}

# What a resource becomes when its product is not in the catalogue. An output can be switched, so
# it is a switch; an input can only be read, so it is a sensor, and it starts disabled because an
# unknown installation can hold hundreds of them.
_FALLBACK_BY_TAG: dict[str, RoleSpec] = {
    "dataline_output": _RELAY,
    "airlink_relay": _RELAY,
    "rf_output": _RELAY,
    "rs485_output": _RELAY,
    "airlink_dimming": _DIMMER,
    "dataline_input": RoleSpec(ResourceRole.BINARY_SENSOR, enabled_default=False),
    "airlink_input": RoleSpec(ResourceRole.BINARY_SENSOR, enabled_default=False),
    "rf_input": RoleSpec(ResourceRole.BINARY_SENSOR, enabled_default=False),
    "rs485_input": RoleSpec(ResourceRole.BINARY_SENSOR, enabled_default=False),
    "resource_temperature": _TEMPERATURE,
    "resource_float": RoleSpec(ResourceRole.SENSOR),
    "resource_integer": RoleSpec(ResourceRole.SENSOR),
}

_INPUT_TAGS = ("dataline_input", "airlink_input", "rf_input", "rs485_input")


def model_name(identifier: str, fallback: str) -> str:
    """Return the readable model name for a product identifier."""
    spec = PRODUCTS.get(identifier)
    return spec.model if spec else fallback


def is_known(identifier: str) -> bool:
    """Return whether the catalogue knows this product."""
    return identifier in PRODUCTS


def role_for(identifier: str, tag: str, index: int) -> RoleSpec:
    """Return what one resource becomes, given its product and the node it sits in.

    A PIR carries more than one input: the first is the movement, the others are its settings and
    secondary contacts, which mean little on their own, so only the first is enabled.
    """
    spec = PRODUCTS.get(identifier)
    if spec is not None:
        wanted = spec.inputs if tag in _INPUT_TAGS else spec.outputs
        if wanted is not None:
            if wanted.device_class == "motion" and index > 1:
                return RoleSpec(ResourceRole.BINARY_SENSOR, device_class="motion", enabled_default=False)
            return wanted
    return _FALLBACK_BY_TAG.get(tag, RoleSpec(ResourceRole.BINARY_SENSOR, enabled_default=False))
