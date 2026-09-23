"""The actions that set a resource by id, and the two rules they keep."""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.lk_ihc.const import DOMAIN

from .conftest import SERIAL, controller_of

pytestmark = pytest.mark.usefixtures("auto_enable_custom_integrations")

# From the invented project: a relay output that has an entity, a function block's timer that has
# none, and a flag that has a disabled one. All three are in the project, so all three may be set.
RELAY = 0x3007
TIMER = 0x300F
FLAG = 0xF001
NOT_IN_PROJECT = 999_999


async def call(hass: HomeAssistant, action: str, **data: object) -> None:
    """Call one of the domain's actions and wait for it."""
    await hass.services.async_call(DOMAIN, action, data, blocking=True)


async def test_every_action_is_registered(hass: HomeAssistant, setup_entry: MockConfigEntry) -> None:
    """Six actions, the same names as the built-in integration's services."""
    for name in (
        "set_runtime_value_bool",
        "set_runtime_value_int",
        "set_runtime_value_float",
        "set_runtime_value_timer",
        "set_runtime_value_time",
        "pulse",
    ):
        assert hass.services.has_service(DOMAIN, name), name


async def test_actions_reach_the_controller(hass: HomeAssistant, setup_entry: MockConfigEntry) -> None:
    """Each action sends the matching command, with the same field names as the built-in integration."""
    await call(hass, "set_runtime_value_bool", ihc_id=RELAY, value=True)
    await call(hass, "set_runtime_value_int", ihc_id=RELAY, value=42)
    await call(hass, "set_runtime_value_float", ihc_id=RELAY, value=21.5)
    await call(hass, "set_runtime_value_timer", ihc_id=TIMER, value=5000)
    await call(hass, "set_runtime_value_time", ihc_id=RELAY, value_hour=7, value_minute=30, value_second=0)
    assert controller_of(setup_entry).commands == [
        ("bool", RELAY, True),
        ("int", RELAY, 42),
        ("float", RELAY, 21.5),
        ("timer", TIMER, 5000),
        ("time", RELAY, (7, 30, 0)),
    ]


async def test_pulse_is_on_then_off(hass: HomeAssistant, setup_entry: MockConfigEntry) -> None:
    """A pulse is what a wall switch key does: on, then off."""
    await call(hass, "pulse", ihc_id=FLAG)
    assert controller_of(setup_entry).commands == [("bool", FLAG, True), ("bool", FLAG, False)]


async def test_a_resource_without_an_entity_can_still_be_set(hass: HomeAssistant, setup_entry: MockConfigEntry) -> None:
    """A function block's timer has no entity, and that is the point of addressing by id."""
    await call(hass, "set_runtime_value_timer", ihc_id=TIMER, value=600_000)
    assert controller_of(setup_entry).commands == [("timer", TIMER, 600_000)]


async def test_an_id_not_in_the_project_is_refused(hass: HomeAssistant, setup_entry: MockConfigEntry) -> None:
    """Addressing by number does not loosen the bound: the project still says what exists."""
    with pytest.raises(ServiceValidationError):
        await call(hass, "set_runtime_value_bool", ihc_id=NOT_IN_PROJECT, value=True)
    assert controller_of(setup_entry).commands == []


async def test_read_only_still_holds(hass: HomeAssistant, setup_entry: MockConfigEntry) -> None:
    """Read-only mode refuses an action exactly as it refuses an entity."""
    setup_entry.runtime_data.connection.read_only = True
    with pytest.raises(ServiceValidationError):
        await call(hass, "pulse", ihc_id=RELAY)
    assert controller_of(setup_entry).commands == []


async def test_controller_can_be_named_by_serial(hass: HomeAssistant, setup_entry: MockConfigEntry) -> None:
    """The controller field picks by serial number; a serial nobody has is an error, not a guess."""
    await call(hass, "set_runtime_value_bool", ihc_id=RELAY, value=False, controller=SERIAL)
    assert controller_of(setup_entry).commands == [("bool", RELAY, False)]
    with pytest.raises(ServiceValidationError):
        await call(hass, "set_runtime_value_bool", ihc_id=RELAY, value=False, controller="0000")


async def test_time_fields_are_range_checked(hass: HomeAssistant, setup_entry: MockConfigEntry) -> None:
    """25 o'clock is not a time; the schema refuses it before anything is sent."""
    with pytest.raises(vol_error_types()):
        await call(hass, "set_runtime_value_time", ihc_id=RELAY, value_hour=25, value_minute=0, value_second=0)
    assert controller_of(setup_entry).commands == []


def vol_error_types() -> tuple[type[Exception], ...]:
    """Schema failures surface as voluptuous errors, wrapped by Home Assistant on some versions."""
    import voluptuous as vol

    return (vol.Invalid, ServiceValidationError)
