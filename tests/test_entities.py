"""Tests for what the entities show and what they send."""

from __future__ import annotations

from datetime import timedelta

import pytest
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
    STATE_UNKNOWN,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from .conftest import controller_of

pytestmark = pytest.mark.usefixtures("auto_enable_custom_integrations")

LAMP = "light.living_room_lamp_outlet_in_the_ceiling"
DIMMER = "light.living_room_combi_dimmer_4_keys_by_the_door"
RELAY = "switch.utility_room_universal_relay_on_the_wall"
PIR = "binary_sensor.utility_room_pir_outside"
TEMPERATURE = "sensor.utility_room_temperature_sensor_by_the_window"
KEY_LEFT = "event.living_room_wall_switch_2_keys_by_the_terrace_door_key_left"

LAMP_ID = 0x3001
DIMMER_ID = 0x3002
RELAY_ID = 0x3007
PIR_ID = 0x3008
TEMPERATURE_ID = 0x300B
KEY_LEFT_ID = 0x3005


async def test_light_follows_the_controller(hass: HomeAssistant, setup_entry: MockConfigEntry):
    """An on/off light shows what the controller reports."""
    controller = controller_of(setup_entry)
    controller.notify(LAMP_ID, True)
    await hass.async_block_till_done()
    assert hass.states.get(LAMP).state == STATE_ON

    controller.notify(LAMP_ID, False)
    await hass.async_block_till_done()
    assert hass.states.get(LAMP).state == STATE_OFF


async def test_light_commands(hass: HomeAssistant, setup_entry: MockConfigEntry):
    """Turning an on/off light on and off sends a boolean to its resource."""
    controller = controller_of(setup_entry)
    await hass.services.async_call(Platform.LIGHT, SERVICE_TURN_ON, {ATTR_ENTITY_ID: LAMP}, blocking=True)
    await hass.services.async_call(Platform.LIGHT, SERVICE_TURN_OFF, {ATTR_ENTITY_ID: LAMP}, blocking=True)
    assert controller.commands == [("bool", LAMP_ID, True), ("bool", LAMP_ID, False)]


async def test_dimmer_levels(hass: HomeAssistant, setup_entry: MockConfigEntry):
    """A dimmer reports a level from 0 to 100 and is set the same way."""
    controller = controller_of(setup_entry)
    controller.notify(DIMMER_ID, 50)
    await hass.async_block_till_done()
    state = hass.states.get(DIMMER)
    assert state.state == STATE_ON
    assert state.attributes["brightness"] == 128  # 50% of 255, rounded

    await hass.services.async_call(
        Platform.LIGHT, SERVICE_TURN_ON, {ATTR_ENTITY_ID: DIMMER, "brightness": 255}, blocking=True
    )
    await hass.services.async_call(Platform.LIGHT, SERVICE_TURN_OFF, {ATTR_ENTITY_ID: DIMMER}, blocking=True)
    assert controller.commands == [("int", DIMMER_ID, 100), ("int", DIMMER_ID, 0)]

    controller.notify(DIMMER_ID, 0)
    await hass.async_block_till_done()
    assert hass.states.get(DIMMER).state == STATE_OFF


async def test_switch(hass: HomeAssistant, setup_entry: MockConfigEntry):
    """A relay shows its state and is switched with a boolean."""
    controller = controller_of(setup_entry)
    controller.notify(RELAY_ID, True)
    await hass.async_block_till_done()
    assert hass.states.get(RELAY).state == STATE_ON

    await hass.services.async_call(Platform.SWITCH, SERVICE_TURN_OFF, {ATTR_ENTITY_ID: RELAY}, blocking=True)
    assert controller.commands == [("bool", RELAY_ID, False)]


async def test_binary_sensor_and_device_class(hass: HomeAssistant, setup_entry: MockConfigEntry):
    """A PIR reports movement, with the device class from the catalogue."""
    controller = controller_of(setup_entry)
    controller.notify(PIR_ID, True)
    await hass.async_block_till_done()
    state = hass.states.get(PIR)
    assert state.state == STATE_ON
    assert state.attributes["device_class"] == "motion"
    assert state.attributes["ihc_id"] == PIR_ID


async def test_sensor(hass: HomeAssistant, setup_entry: MockConfigEntry):
    """A temperature resource becomes a temperature sensor in degrees."""
    controller = controller_of(setup_entry)
    controller.notify(TEMPERATURE_ID, 21.5)
    await hass.async_block_till_done()
    state = hass.states.get(TEMPERATURE)
    assert state.state == "21.5"
    assert state.attributes["device_class"] == "temperature"
    assert state.attributes["unit_of_measurement"] == "°C"


async def test_button_press_fires_an_event(hass: HomeAssistant, setup_entry: MockConfigEntry):
    """A key on a wall switch fires press when it goes down, and short_release when it comes up."""
    controller = controller_of(setup_entry)
    assert hass.states.get(KEY_LEFT).state == STATE_UNKNOWN

    # The value the subscription starts with must not look like a press.
    controller.notify(KEY_LEFT_ID, False)
    await hass.async_block_till_done()
    assert hass.states.get(KEY_LEFT).state == STATE_UNKNOWN

    controller.notify(KEY_LEFT_ID, True)
    await hass.async_block_till_done()
    pressed = hass.states.get(KEY_LEFT)
    assert pressed.state != STATE_UNKNOWN
    assert pressed.attributes["event_type"] == "press"

    assert pressed.attributes["event_types"] == [
        "press",
        "single_press",
        "double_press",
        "long_press",
        "short_release",
        "long_release",
    ]

    controller.notify(KEY_LEFT_ID, False)
    await hass.async_block_till_done()
    assert hass.states.get(KEY_LEFT).attributes["event_type"] == "short_release"


async def test_button_single_and_long_press(hass: HomeAssistant, setup_entry: MockConfigEntry):
    """A single press comes once the double press window has passed; a long press while the key is held."""
    controller = controller_of(setup_entry)
    controller.notify(KEY_LEFT_ID, False)  # the value the subscription starts with
    await hass.async_block_till_done()

    controller.notify(KEY_LEFT_ID, True)
    controller.notify(KEY_LEFT_ID, False)
    await hass.async_block_till_done()
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=1))
    await hass.async_block_till_done()
    assert hass.states.get(KEY_LEFT).attributes["event_type"] == "single_press"

    controller.notify(KEY_LEFT_ID, True)
    await hass.async_block_till_done()
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=1))
    await hass.async_block_till_done()
    assert hass.states.get(KEY_LEFT).attributes["event_type"] == "long_press"

    controller.notify(KEY_LEFT_ID, False)
    await hass.async_block_till_done()
    assert hass.states.get(KEY_LEFT).attributes["event_type"] == "long_release"


async def test_a_held_key_at_startup_is_not_a_press(hass: HomeAssistant, setup_entry: MockConfigEntry):
    """A key that happens to be held when Home Assistant starts does not fire an event."""
    controller = controller_of(setup_entry)
    controller.notify(KEY_LEFT_ID, True)  # first value ever seen for this resource
    await hass.async_block_till_done()
    assert hass.states.get(KEY_LEFT).state == STATE_UNKNOWN


async def test_buttons_can_be_left_out(hass: HomeAssistant, config_entry: MockConfigEntry, fake_controller):
    """With the option off, no event entities are created at all."""
    hass.config_entries.async_update_entry(config_entry, options={"read_only": False, "expose_buttons": False})
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(KEY_LEFT) is None
    assert hass.states.get(LAMP) is not None
