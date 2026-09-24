"""Tests for which area a product's device lands in.

The invented project has two groups, "Living room" and "Utility room". An installation often has
its areas already, under names of its own, so the group is matched by name, alias and id before a
new area is made.
"""

from __future__ import annotations

import pytest
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.lk_ihc.const import DOMAIN

from .conftest import SERIAL

pytestmark = pytest.mark.usefixtures("auto_enable_custom_integrations")

# Found by unique id, since the entity id is built from the area's name and so follows the area.
LAMP = (Platform.LIGHT, 0x3001)
RELAY = (Platform.SWITCH, 0x3007)


async def _set_up(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()


def _area_of(hass: HomeAssistant, entity: tuple[Platform, int]) -> str | None:
    entities = er.async_get(hass)
    platform, ihc_id = entity
    device_id = entities.async_get(entities.async_get_entity_id(platform, DOMAIN, f"{SERIAL}-{ihc_id}")).device_id
    return dr.async_get(hass).async_get(device_id).area_id


async def test_a_group_without_an_area_gets_one(hass: HomeAssistant, config_entry: MockConfigEntry, fake_controller):
    """With no area to match, the group becomes a new area, as before."""
    await _set_up(hass, config_entry)
    assert _area_of(hass, LAMP) == "living_room"
    assert ar.async_get(hass).async_get_area("living_room").name == "Living room"


async def test_a_renamed_area_is_found_by_its_id(hass: HomeAssistant, config_entry: MockConfigEntry, fake_controller):
    """An area created as "Living room" and renamed keeps its id, and the group still lands there."""
    areas = ar.async_get(hass)
    areas.async_update(areas.async_create("Living room").id, name="Stue")
    await _set_up(hass, config_entry)
    assert _area_of(hass, LAMP) == "living_room"
    assert areas.async_get_area_by_name("Living room") is None


async def test_an_area_is_found_by_its_alias(hass: HomeAssistant, config_entry: MockConfigEntry, fake_controller):
    """An area that lists the group's name as an alias takes the group's products."""
    areas = ar.async_get(hass)
    utility = areas.async_create("Bryggers", aliases={"Utility room"})
    await _set_up(hass, config_entry)
    assert _area_of(hass, RELAY) == utility.id
    assert areas.async_get_area_by_name("Utility room") is None
