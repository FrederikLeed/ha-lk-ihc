"""Tests for setting a controller up from the user interface."""

from __future__ import annotations

import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_PASSWORD, CONF_URL, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.lk_ihc.const import CONF_EXPOSE_BUTTONS, CONF_READ_ONLY, DOMAIN

from .conftest import SERIAL

pytestmark = pytest.mark.usefixtures("auto_enable_custom_integrations")

USER_INPUT = {CONF_URL: "http://192.0.2.10", CONF_USERNAME: "tester", CONF_PASSWORD: "secret"}


async def test_user_flow(hass: HomeAssistant, fake_controller):
    """A working controller becomes an entry that starts read-only."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == f"IHC controller {SERIAL}"
    assert result["data"] == USER_INPUT
    assert result["options"] == {CONF_READ_ONLY: True, CONF_EXPOSE_BUTTONS: True}
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert entry.unique_id == SERIAL


async def test_wrong_password(hass: HomeAssistant, fake_controller):
    """A refused login is shown on the form, and the flow stays open."""
    original = fake_controller.__init__

    def refusing_init(self, *args, **kwargs):
        original(self, *args, **kwargs)
        self.auth_result = False

    fake_controller.__init__ = refusing_init
    try:
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    finally:
        fake_controller.__init__ = original

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}

    # The same form then works with a controller that answers.
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_controller_not_answering(hass: HomeAssistant, fake_controller):
    """A controller that cannot be reached is reported as such."""
    original = fake_controller.__init__

    def failing_init(self, *args, **kwargs):
        original(self, *args, **kwargs)
        self.auth_error = OSError("no route to host")

    fake_controller.__init__ = failing_init
    try:
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    finally:
        fake_controller.__init__ = original

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_no_project(hass: HomeAssistant, fake_controller):
    """A controller that will not hand over its project is a connection problem, not an entry."""
    original = fake_controller.__init__

    def empty_project_init(self, *args, **kwargs):
        original(self, *args, **kwargs)
        self.project = None

    fake_controller.__init__ = empty_project_init
    try:
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    finally:
        fake_controller.__init__ = original

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_same_controller_twice(hass: HomeAssistant, fake_controller, config_entry: MockConfigEntry):
    """A controller that is already set up is not added a second time."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_options_flow(hass: HomeAssistant, setup_entry: MockConfigEntry):
    """The options flow saves read-only and the button setting."""
    result = await hass.config_entries.options.async_init(setup_entry.entry_id)
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_READ_ONLY: True, CONF_EXPOSE_BUTTONS: False}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert setup_entry.options == {CONF_READ_ONLY: True, CONF_EXPOSE_BUTTONS: False}
