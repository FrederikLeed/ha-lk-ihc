"""Tests for the entities of the controller's own logic: its flags and enums."""

from __future__ import annotations

import pytest
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.lk_ihc.const import DOMAIN

from .conftest import SERIAL

pytestmark = pytest.mark.usefixtures("auto_enable_custom_integrations")

LIGHT_MODE_ID = 0xE101


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
