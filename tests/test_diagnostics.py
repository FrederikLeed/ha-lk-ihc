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
        "products": 9,
        "resources": 14,
        "roles": {"light": 2, "button": 5, "switch": 3, "binary_sensor": 3, "sensor": 1},
        "product_ids": ["0x2101", "0x2102", "0x210e", "0x2124", "0x2202", "0x4101", "0x4203", "0x4406", "0x9999"],
        "unrecognised_products": 1,
        "function_blocks": 1,
        "products_with_wiring": 1,
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


async def test_diagnostics_report_the_controllers_own_state(hass: HomeAssistant, setup_entry: MockConfigEntry) -> None:
    """What we do not control is still reported, so an installation can be looked at."""
    diagnostics = await async_get_config_entry_diagnostics(hass, setup_entry)
    status = diagnostics["status"]
    assert status["rf_devices"] == 0
    assert status["rf_devices_low_battery"] == 0
    assert status["rf_devices_unheard"] == 0
    # A controller that answers none of these still reports, rather than omitting the section.
    assert "controller_time" in status
    assert "time_synchronised" in status
    assert status["smtp_configured"] is False
