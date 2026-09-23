"""Shared fixtures: a config entry and an IHC controller that lives entirely in the test."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from homeassistant.const import CONF_PASSWORD, CONF_URL, CONF_USERNAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.lk_ihc.const import CONF_EXPOSE_BUTTONS, CONF_READ_ONLY, DOMAIN

FIXTURES = Path(__file__).parent / "fixtures"

SERIAL = "1062"
SYSTEM_INFO = {
    "serial_number": SERIAL,
    "brand": "LK",
    "version": "2.7.220",
    "hw_revision": "6.1",
    "sw_date": "2015-05-05T22:00:00Z",
    "dataline_version": "0.0.20",
}


@pytest.fixture
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let Home Assistant load the integration from custom_components."""


def load_project() -> str:
    """Return the invented project used by the tests."""
    return (FIXTURES / "project.xml").read_text(encoding="utf-8")


class FakeIHCController:
    """Stands in for ihcsdk's IHCController, with no network anywhere near it."""

    instances: list[FakeIHCController] = []

    def __init__(self, url: str, username: str, password: str) -> None:
        """Remember what it was asked to connect to."""
        self.url = url
        self.username = username
        self.password = password
        self.authenticated = False
        self.disconnected = False
        self.notifications: dict[int, Callable[[int, Any], None]] = {}
        self.commands: list[tuple[str, int, Any]] = []
        # What the test wants to happen
        self.auth_result = True
        self.auth_error: Exception | None = None
        self.project: str | None = load_project()
        self.command_result = True
        self.client = self._Client()
        FakeIHCController.instances.append(self)

    class _Client:
        """The bit of the sdk that answers for the controller itself."""

        def get_system_info(self) -> dict[str, Any]:
            return dict(SYSTEM_INFO)

    # --- the parts the integration uses ---
    def authenticate(self) -> bool:
        if self.auth_error is not None:
            raise self.auth_error
        self.authenticated = self.auth_result
        return self.auth_result

    def get_project(self) -> str | None:
        return self.project

    def disconnect(self) -> None:
        self.disconnected = True

    def add_notify_event(self, resource_id: int, callback: Callable[[int, Any], None], delayed: bool = False) -> bool:
        self.notifications[resource_id] = callback
        return True

    def set_runtime_value_bool(self, resource_id: int, value: bool) -> bool:
        self.commands.append(("bool", resource_id, value))
        return self.command_result

    def set_runtime_value_int(self, resource_id: int, value: int) -> bool:
        self.commands.append(("int", resource_id, value))
        return self.command_result

    def set_runtime_value_float(self, resource_id: int, value: float) -> bool:
        self.commands.append(("float", resource_id, value))
        return self.command_result

    def set_runtime_value_timer(self, resource_id: int, value: int) -> bool:
        self.commands.append(("timer", resource_id, value))
        return self.command_result

    def set_runtime_value_time(self, resource_id: int, hours: int, minutes: int, seconds: int) -> bool:
        self.commands.append(("time", resource_id, (hours, minutes, seconds)))
        return self.command_result

    # --- what the tests drive it with ---
    def notify(self, resource_id: int, value: Any) -> None:
        """Send a value the way the controller's notify thread would."""
        callback = self.notifications.get(resource_id)
        assert callback is not None, f"nothing subscribed to resource {resource_id}"
        callback(resource_id, value)


@pytest.fixture
def fake_controller():
    """Patch the sdk controller and hand the test the instance the integration made."""
    FakeIHCController.instances.clear()
    with patch("custom_components.lk_ihc.controller.IHCController", FakeIHCController):
        yield FakeIHCController


@pytest.fixture
def config_entry(hass: HomeAssistant) -> MockConfigEntry:
    """A configured controller that may be controlled."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="IHC controller 1062",
        data={
            CONF_URL: "http://192.0.2.10",
            CONF_USERNAME: "tester",
            CONF_PASSWORD: "secret",
        },
        options={CONF_READ_ONLY: False, CONF_EXPOSE_BUTTONS: True},
        unique_id=SERIAL,
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
async def setup_entry(hass: HomeAssistant, config_entry: MockConfigEntry, fake_controller) -> MockConfigEntry:
    """Set the entry up and return it, with the fake controller in place."""
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry


def controller_of(entry: MockConfigEntry) -> FakeIHCController:
    """Return the fake controller behind a set up entry."""
    return FakeIHCController.instances[-1]
