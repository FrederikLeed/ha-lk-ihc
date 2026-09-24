"""Tests for the entities of the controller's own logic: its flags, enums and block outputs."""

from __future__ import annotations

import pytest
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.lk_ihc.const import DOMAIN

from . import conftest
from .conftest import SERIAL

pytestmark = pytest.mark.usefixtures("auto_enable_custom_integrations")

LIGHT_MODE_ID = 0xE101
BLOCK_OUTPUT_ID = 0x3020


async def test_a_block_output_is_a_disabled_binary_sensor(
    hass: HomeAssistant, config_entry: MockConfigEntry, fake_controller, monkeypatch
):
    """A function block's output is on the controller device, named with its block, and starts disabled."""
    block = '<functionblock id="_0x2009" name="1.1.01. Toggle block with on, off and timer">'
    output = f'<outputs><resource_output id="_0x{BLOCK_OUTPUT_ID:x}" name="Output"/></outputs>'
    project = conftest.load_project()
    assert block in project
    monkeypatch.setattr(conftest, "load_project", lambda: project.replace(block, block + output))
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    entities = er.async_get(hass)
    entry = entities.async_get(
        entities.async_get_entity_id(Platform.BINARY_SENSOR, DOMAIN, f"{SERIAL}-logic-{BLOCK_OUTPUT_ID}")
    )
    assert entry.original_name == "Output (Toggle block with on, off and timer)"
    assert entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION


async def test_logic_the_project_no_longer_has_is_removed(
    hass: HomeAssistant, config_entry: MockConfigEntry, fake_controller
):
    """An enum the project no longer holds, such as a value from a program, is removed at setup."""
    entities = er.async_get(hass)

    def registered(platform: Platform, unique_id: str) -> str:
        return entities.async_get_or_create(platform, DOMAIN, unique_id, config_entry=config_entry).entity_id

    gone = registered(Platform.SENSOR, f"{SERIAL}-logic-{0x7777}")
    kept = registered(Platform.SENSOR, f"{SERIAL}-logic-{LIGHT_MODE_ID}")
    # Not the controller's logic, so left alone even though the project has no such product.
    product = registered(Platform.LIGHT, f"{SERIAL}-{0x7778}")

    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert entities.async_get(gone) is None
    assert entities.async_get(kept) is not None
    assert entities.async_get(product) is not None
