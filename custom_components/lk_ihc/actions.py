"""Actions that set a resource by its id: the escape hatch the entities do not cover.

An entity is the right way to switch a lamp. But an installation holds resources no entity
represents - a function block's timer, a flag its logic tests, an input that only exists to be
pulsed - and an automation sometimes needs exactly one of those. These actions reach them by
resource id, the same way the built-in `ihc` integration's services do and with the same field
names, so an automation written for `ihc.set_runtime_value_bool` works here by changing the domain.

Two things do not change because a resource is addressed by number instead of by entity:

- **Read-only mode still holds.** While the entry is read-only, every action is refused with the
  same explanation an entity gives.
- **The project still bounds what can be written.** A command only goes to an id that exists in the
  controller's own project. That set is wider than the entities (timers and flags are in it), but
  an id that is not in the installation is refused, so a typo cannot write into the house blind.

With more than one controller set up, the `controller` field names one by serial number. With one,
it can be left out.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN
from .controller import IHCConnection

ATTR_IHC_ID = "ihc_id"
ATTR_CONTROLLER = "controller"
ATTR_VALUE = "value"
ATTR_VALUE_HOUR = "value_hour"
ATTR_VALUE_MINUTE = "value_minute"
ATTR_VALUE_SECOND = "value_second"

ACTION_SET_BOOL = "set_runtime_value_bool"
ACTION_SET_INT = "set_runtime_value_int"
ACTION_SET_FLOAT = "set_runtime_value_float"
ACTION_SET_TIMER = "set_runtime_value_timer"
ACTION_SET_TIME = "set_runtime_value_time"
ACTION_PULSE = "pulse"

_BASE = {
    vol.Required(ATTR_IHC_ID): cv.positive_int,
    vol.Optional(ATTR_CONTROLLER): cv.string,
}
SCHEMA_BOOL = vol.Schema({**_BASE, vol.Required(ATTR_VALUE): cv.boolean})
SCHEMA_INT = vol.Schema({**_BASE, vol.Required(ATTR_VALUE): vol.Coerce(int)})
SCHEMA_FLOAT = vol.Schema({**_BASE, vol.Required(ATTR_VALUE): vol.Coerce(float)})
SCHEMA_TIMER = vol.Schema({**_BASE, vol.Required(ATTR_VALUE): vol.All(vol.Coerce(int), vol.Range(min=0))})
SCHEMA_TIME = vol.Schema(
    {
        **_BASE,
        vol.Required(ATTR_VALUE_HOUR): vol.All(vol.Coerce(int), vol.Range(min=0, max=23)),
        vol.Required(ATTR_VALUE_MINUTE): vol.All(vol.Coerce(int), vol.Range(min=0, max=59)),
        vol.Required(ATTR_VALUE_SECOND): vol.All(vol.Coerce(int), vol.Range(min=0, max=59)),
    }
)
SCHEMA_PULSE = vol.Schema(_BASE)


def _connection(hass: HomeAssistant, call: ServiceCall) -> IHCConnection:
    """Return the controller the call is for, or say why that cannot be decided."""
    entries = hass.config_entries.async_loaded_entries(DOMAIN)
    wanted = call.data.get(ATTR_CONTROLLER)
    if wanted is not None:
        for entry in entries:
            if entry.runtime_data.connection.serial_number == wanted:
                return entry.runtime_data.connection
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="unknown_controller",
            translation_placeholders={"controller": wanted},
        )
    if not entries:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="no_controller")
    if len(entries) > 1:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="which_controller")
    return entries[0].runtime_data.connection


def _handler(
    hass: HomeAssistant, send: Callable[[IHCConnection, ServiceCall], Awaitable[None]]
) -> Callable[[ServiceCall], Awaitable[None]]:
    """Wrap a send function so it receives the resolved connection."""

    async def handle(call: ServiceCall) -> None:
        await send(_connection(hass, call), call)

    return handle


async def _set_bool(connection: IHCConnection, call: ServiceCall) -> None:
    await connection.async_set_bool(call.data[ATTR_IHC_ID], call.data[ATTR_VALUE])


async def _set_int(connection: IHCConnection, call: ServiceCall) -> None:
    await connection.async_set_int(call.data[ATTR_IHC_ID], call.data[ATTR_VALUE])


async def _set_float(connection: IHCConnection, call: ServiceCall) -> None:
    await connection.async_set_float(call.data[ATTR_IHC_ID], call.data[ATTR_VALUE])


async def _set_timer(connection: IHCConnection, call: ServiceCall) -> None:
    await connection.async_set_timer(call.data[ATTR_IHC_ID], call.data[ATTR_VALUE])


async def _set_time(connection: IHCConnection, call: ServiceCall) -> None:
    await connection.async_set_time(
        call.data[ATTR_IHC_ID],
        call.data[ATTR_VALUE_HOUR],
        call.data[ATTR_VALUE_MINUTE],
        call.data[ATTR_VALUE_SECOND],
    )


async def _pulse(connection: IHCConnection, call: ServiceCall) -> None:
    await connection.async_pulse(call.data[ATTR_IHC_ID])


ACTIONS: tuple[tuple[str, vol.Schema, Callable[[IHCConnection, ServiceCall], Awaitable[None]]], ...] = (
    (ACTION_SET_BOOL, SCHEMA_BOOL, _set_bool),
    (ACTION_SET_INT, SCHEMA_INT, _set_int),
    (ACTION_SET_FLOAT, SCHEMA_FLOAT, _set_float),
    (ACTION_SET_TIMER, SCHEMA_TIMER, _set_timer),
    (ACTION_SET_TIME, SCHEMA_TIME, _set_time),
    (ACTION_PULSE, SCHEMA_PULSE, _pulse),
)


@callback
def async_register_actions(hass: HomeAssistant) -> None:
    """Register the actions once for the domain. They resolve the controller per call."""
    for name, schema, send in ACTIONS:
        if not hass.services.has_service(DOMAIN, name):
            hass.services.async_register(DOMAIN, name, _handler(hass, send), schema=schema)
