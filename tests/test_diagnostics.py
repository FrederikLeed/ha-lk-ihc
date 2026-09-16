"""Tests that diagnostics describe the installation without identifying it."""

from __future__ import annotations

import json

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.lk_ihc.diagnostics import async_get_config_entry_diagnostics

pytestmark = pytest.mark.usefixtures("auto_enable_custom_integrations")


async def test_diagnostics(hass: HomeAssistant, setup_entry: MockConfigEntry):
    """The file says what the installation is made of, and nothing about who owns it."""
    diagnostics = await async_get_config_entry_diagnostics(hass, setup_entry)

    assert diagnostics["installation"] == {
        "groups": 2,
        "products": 7,
        "resources": 12,
        "roles": {"light": 2, "button": 4, "switch": 2, "binary_sensor": 3, "sensor": 1},
        "product_ids": ["0x2101", "0x210e", "0x2124", "0x2202", "0x4203", "0x4406", "0x9999"],
        "unrecognised_products": 1,
    }
    assert diagnostics["controller"]["version"] == "2.7.220"
    assert diagnostics["controller"]["read_only"] is False

    text = json.dumps(diagnostics)
    for secret in ("secret", "tester", "192.0.2.10"):
        assert secret not in text
    # Nothing that names a room or a product position either.
    # Including the name of a product the catalogue does not know, which comes from the owner.
    for private in ("Living room", "by the terrace door", "Lamp outlet", "Something unknown"):
        assert private not in text
