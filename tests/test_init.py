"""Tests for setting the entry up, tearing it down, and the safety rails."""

from __future__ import annotations

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_ENTITY_ID, CONF_PASSWORD, SERVICE_TURN_ON, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.lk_ihc.const import CONF_READ_ONLY, DOMAIN
from custom_components.lk_ihc.controller import IHCReadOnlyError

from .conftest import SERIAL, controller_of

pytestmark = pytest.mark.usefixtures("auto_enable_custom_integrations")


async def test_setup_creates_devices_and_entities(hass: HomeAssistant, setup_entry: MockConfigEntry):
    """Every product becomes a device, and every exposed resource an entity on it."""
    assert setup_entry.state is ConfigEntryState.LOADED

    devices = dr.async_get(hass)
    controller = devices.async_get_device_by_identifier((DOMAIN, SERIAL), setup_entry.entry_id)
    assert controller is not None
    assert controller.sw_version == "2.7.220"

    lamp = devices.async_get_device_by_identifier((DOMAIN, f"{SERIAL}-8193"), setup_entry.entry_id)  # 0x2001
    assert lamp is not None
    assert lamp.name == "Lamp outlet (in the ceiling)"
    assert lamp.model == "Dataline lamp outlet"
    assert lamp.model_id == "0x2202"
    assert lamp.via_device_id == controller.id

    entities = er.async_get(hass)
    entries = er.async_entries_for_config_entry(entities, setup_entry.entry_id)
    by_platform: dict[str, int] = {}
    for entry in entries:
        by_platform[entry.domain] = by_platform.get(entry.domain, 0) + 1
    assert by_platform == {"light": 2, "switch": 2, "binary_sensor": 3, "sensor": 1, "event": 4}


async def test_disabled_entities_are_registered_but_not_created(hass: HomeAssistant, setup_entry: MockConfigEntry):
    """A PIR's second contact exists in the registry, disabled, rather than being dropped."""
    entities = er.async_get(hass)
    entry = entities.async_get_entity_id("binary_sensor", DOMAIN, f"{SERIAL}-12297")  # 0x3009
    assert entry is not None
    assert entities.async_get(entry).disabled_by is er.RegistryEntryDisabler.INTEGRATION
    assert hass.states.get(entry) is None


async def test_unload_disconnects(hass: HomeAssistant, setup_entry: MockConfigEntry):
    """Unloading the entry logs out of the controller."""
    controller = controller_of(setup_entry)
    assert await hass.config_entries.async_unload(setup_entry.entry_id)
    await hass.async_block_till_done()
    assert setup_entry.state is ConfigEntryState.NOT_LOADED
    assert controller.disconnected is True


async def test_cannot_connect_is_retried(hass: HomeAssistant, config_entry: MockConfigEntry, fake_controller):
    """A controller that is not answering leaves the entry waiting instead of failing for good."""
    fake_controller.instances.clear()
    original = fake_controller.__init__

    def failing_init(self, *args, **kwargs):
        original(self, *args, **kwargs)
        self.auth_error = OSError("no route to host")

    fake_controller.__init__ = failing_init
    try:
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()
    finally:
        fake_controller.__init__ = original
    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_wrong_password_asks_for_a_new_one(hass: HomeAssistant, config_entry: MockConfigEntry, fake_controller):
    """A refused login starts reauthentication rather than retrying forever."""
    fake_controller.instances.clear()
    original = fake_controller.__init__

    def refusing_init(self, *args, **kwargs):
        original(self, *args, **kwargs)
        self.auth_result = False

    fake_controller.__init__ = refusing_init
    try:
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()
    finally:
        fake_controller.__init__ = original
    assert config_entry.state is ConfigEntryState.SETUP_ERROR
    assert any(flow["context"]["source"] == "reauth" for flow in hass.config_entries.flow.async_progress())


async def test_read_only_refuses_commands(hass: HomeAssistant, config_entry: MockConfigEntry, fake_controller):
    """In read-only mode the entities work, but nothing is ever sent to the installation."""
    hass.config_entries.async_update_entry(config_entry, options={CONF_READ_ONLY: True})
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    controller = controller_of(config_entry)

    with pytest.raises(IHCReadOnlyError):
        await hass.services.async_call(
            Platform.LIGHT,
            SERVICE_TURN_ON,
            {ATTR_ENTITY_ID: "light.living_room_lamp_outlet_in_the_ceiling"},
            blocking=True,
        )
    assert controller.commands == []


async def test_options_change_reloads(hass: HomeAssistant, setup_entry: MockConfigEntry):
    """Turning read-only on takes effect without a restart."""
    hass.config_entries.async_update_entry(setup_entry, options={CONF_READ_ONLY: True})
    await hass.async_block_till_done()
    assert setup_entry.runtime_data.connection.read_only is True


async def test_command_to_an_unknown_resource_is_refused(hass: HomeAssistant, setup_entry: MockConfigEntry):
    """A resource that is not part of this installation is never written to."""
    connection = setup_entry.runtime_data.connection
    with pytest.raises(ServiceValidationError, match="not part of this IHC installation"):
        await connection.async_set_bool(999999, True)


async def test_reauth_updates_the_password(hass: HomeAssistant, setup_entry: MockConfigEntry):
    """The reauth flow saves the new password and reloads the entry."""
    result = await setup_entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"username": "tester", "password": "new-secret"}
    )
    await hass.async_block_till_done()
    assert result["type"] == "abort"
    assert result["reason"] == "reauth_successful"
    assert setup_entry.data[CONF_PASSWORD] == "new-secret"
