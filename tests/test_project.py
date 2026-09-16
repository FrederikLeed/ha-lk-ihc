"""Tests for reading the project file into products and resources."""

from __future__ import annotations

import pytest

from custom_components.lk_ihc.catalog import ResourceRole, icon_for, model_name, role_for
from custom_components.lk_ihc.project import parse_project

from .conftest import load_project


@pytest.fixture
def project():
    """The parsed test project."""
    return parse_project(load_project())


def test_products_and_groups(project):
    """Every product in the file is found, with its group, position and model name."""
    assert [group for group in project.groups] == ["Living room", "Utility room"]
    assert len(project.products) == 7
    lamp = next(p for p in project.products if p.product_id == 0x2001)
    assert lamp.group == "Living room"
    assert lamp.device_name == "Lamp outlet (in the ceiling)"
    assert lamp.model == "Dataline lamp outlet"
    assert lamp.model_id == "0x2202"


def test_roles(project):
    """Each resource becomes what its product says it is."""
    roles = {resource.ihc_id: resource.role for _product, resource in project.resources}
    assert roles[0x3001] is ResourceRole.LIGHT  # lamp outlet output
    assert roles[0x3002] is ResourceRole.LIGHT  # dimmer output
    assert roles[0x3003] is ResourceRole.BUTTON  # a key on the combi dimmer
    assert roles[0x3005] is ResourceRole.BUTTON  # a key on the wall switch
    assert roles[0x3007] is ResourceRole.SWITCH  # universal relay
    assert roles[0x3008] is ResourceRole.BINARY_SENSOR  # PIR movement
    assert roles[0x300B] is ResourceRole.SENSOR  # temperature


def test_dimmable_and_device_classes(project):
    """A dimmer can dim, a plain outlet cannot, and sensors carry their device class."""
    by_id = {resource.ihc_id: resource for _product, resource in project.resources}
    assert by_id[0x3002].dimmable is True
    assert by_id[0x3001].dimmable is False
    assert by_id[0x3008].device_class == "motion"
    assert by_id[0x300B].device_class == "temperature"


def test_settings_and_extra_inputs_are_not_exposed(project):
    """A setting node is skipped, and a PIR's second contact is created disabled."""
    ids = {resource.ihc_id for _product, resource in project.resources}
    assert 0x300A not in ids  # setting="yes"
    by_id = {resource.ihc_id: resource for _product, resource in project.resources}
    assert by_id[0x3008].enabled_default is True
    assert by_id[0x3009].enabled_default is False


def test_unknown_product_still_usable(project):
    """An unknown product keeps its output as a switch and its input as a disabled sensor."""
    by_id = {resource.ihc_id: resource for _product, resource in project.resources}
    assert by_id[0x300C].role is ResourceRole.SWITCH
    assert by_id[0x300D].role is ResourceRole.BINARY_SENSOR
    assert by_id[0x300D].enabled_default is False
    unknown = next(p for p in project.products if p.identifier == "_0x9999")
    assert unknown.model == "Something unknown"  # the product's own name, when the catalogue has none
    assert unknown.model_id == "0x9999"


def test_counts(project):
    """The summary counts every role, which is what the setup log and diagnostics show."""
    assert parse_project(load_project()).counts() == {
        "light": 2,
        "button": 4,
        "switch": 2,
        "binary_sensor": 3,
        "sensor": 1,
    }


def test_catalog_helpers():
    """Model names come from the catalogue, and an unknown identifier falls back."""
    assert model_name("_0x2101", "fallback") == "Dataline wall switch, 2 keys"
    assert model_name("_0x9999", "fallback") == "fallback"
    assert role_for("_0x9999", "airlink_dimming", 1).dimmable is True


def test_icons(project):
    """Keys and relays get an icon; lights and sensors keep the one their device class gives them."""
    by_id = {resource.ihc_id: resource for _product, resource in project.resources}
    assert by_id[0x3005].icon == "mdi:gesture-tap-button"  # a key
    assert by_id[0x3007].icon == "mdi:electric-switch"  # a relay
    assert by_id[0x3001].icon is None  # a light
    assert by_id[0x3008].icon is None  # a PIR
    assert icon_for("_0x4201", ResourceRole.SWITCH) == "mdi:power-socket"  # a plug outlet


def test_project_without_products():
    """A file with nothing in it parses to an empty project rather than failing."""
    project = parse_project("<utcs><groups><group name='Empty'/></groups></utcs>")
    assert project.products == []
    assert project.counts() == {}
