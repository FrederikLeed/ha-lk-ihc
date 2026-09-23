"""Tests for the connection: what it sends, what it refuses, and how it fails."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.lk_ihc.controller import (
    IHCAuthError,
    IHCConnectError,
    IHCConnection,
    IHCReadOnlyError,
    apply_http_timeout,
)

from .conftest import FakeIHCController

pytestmark = pytest.mark.usefixtures("auto_enable_custom_integrations")


@pytest.fixture
def connection(hass: HomeAssistant, fake_controller):
    """A connection with the fake controller behind it, allowed to write."""
    connection = IHCConnection(hass, "http://192.0.2.10", "tester", "secret")
    connection.read_only = False
    return connection


async def test_connect_and_project(connection):
    """Connecting reads the system information, and the project comes back as text."""
    info = await connection.async_connect()
    assert info["serial_number"] == "1062"
    assert connection.serial_number == "1062"
    assert "<utcs" in await connection.async_project()


async def test_refused_login(hass: HomeAssistant, connection):
    """A controller that refuses the login raises an auth error."""
    FakeIHCController.instances[-1].auth_result = False
    with pytest.raises(IHCAuthError):
        await connection.async_connect()


async def test_unreachable_controller(connection):
    """A transport error becomes a connect error, with the address in the message."""
    FakeIHCController.instances[-1].auth_error = OSError("no route to host")
    with pytest.raises(IHCConnectError, match="192.0.2.10"):
        await connection.async_connect()


async def test_executor_timeout_is_a_connection_problem(connection):
    """When the wait for the controller times out, setup sees a connection problem, not a crash."""
    with (
        patch.object(connection.hass, "async_add_executor_job", side_effect=TimeoutError),
        pytest.raises(IHCConnectError, match="in time"),
    ):
        await connection.async_connect()


async def test_http_requests_are_bounded(hass: HomeAssistant):
    """The sdk posts without a timeout, so the integration puts one on its session."""

    class FakeSession:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        def post(self, **kwargs):
            self.calls.append(kwargs)

    class FakeController:
        def __init__(self, *args) -> None:
            self.client = type("Client", (), {"connection": type("Conn", (), {"session": FakeSession()})()})()

    controller = FakeController()
    session = controller.client.connection.session
    assert apply_http_timeout(controller, timeout=12) is True
    session.post(url="http://192.0.2.10/ws/ResourceInteractionService")
    assert session.calls[0]["timeout"] == 12

    # A stand-in without a session is not a reason to fail setup.
    assert apply_http_timeout(object()) is False


async def test_empty_project(connection):
    """A controller that hands over no project is a connection problem."""
    await connection.async_connect()
    FakeIHCController.instances[-1].project = None
    with pytest.raises(IHCConnectError, match="did not return a project"):
        await connection.async_project()


async def test_commands(connection):
    """Every command type reaches the controller, for resources the project knows."""
    await connection.async_connect()
    connection.register([1, 2, 3])
    await connection.async_set_bool(1, True)
    await connection.async_set_int(2, 75)
    await connection.async_set_float(3, 21.5)
    await connection.async_pulse(1)
    assert FakeIHCController.instances[-1].commands == [
        ("bool", 1, True),
        ("int", 2, 75),
        ("float", 3, 21.5),
        ("bool", 1, True),
        ("bool", 1, False),
    ]


async def test_rejected_command(connection):
    """A command the controller will not take is reported, not silently dropped."""
    await connection.async_connect()
    connection.register([1])
    FakeIHCController.instances[-1].command_result = False
    with pytest.raises(IHCConnectError, match="rejected"):
        await connection.async_set_bool(1, True)


async def test_command_timeout(connection):
    """A command that does not come back in time is reported as a connection problem."""
    await connection.async_connect()
    connection.register([1])
    with (
        patch.object(connection.hass, "async_add_executor_job", side_effect=TimeoutError),
        pytest.raises(IHCConnectError, match="in time"),
    ):
        await connection.async_set_bool(1, True)


async def test_read_only_blocks_every_command(connection):
    """Read-only mode refuses each kind of command."""
    await connection.async_connect()
    connection.register([1])
    connection.read_only = True
    for call in (
        connection.async_set_bool(1, True),
        connection.async_set_int(1, 5),
        connection.async_set_float(1, 1.5),
    ):
        with pytest.raises(IHCReadOnlyError):
            await call
    assert FakeIHCController.instances[-1].commands == []


async def test_second_subscriber_gets_the_known_value(connection):
    """Two entities on one resource both get values, and the second starts with the last one."""
    await connection.async_connect()
    first: list[bool] = []
    second: list[bool] = []
    await connection.async_subscribe(7, first.append)
    FakeIHCController.instances[-1].notify(7, True)
    await asyncio.sleep(0)
    assert first == [True]
    assert connection.value(7) is True

    await connection.async_subscribe(7, second.append)
    assert second == [True]

    FakeIHCController.instances[-1].notify(7, False)
    await asyncio.sleep(0)
    assert first == [True, False]
    assert second == [True, False]


async def test_one_bad_listener_does_not_stop_the_others(connection, caplog):
    """An entity that raises while handling a value does not cost the others theirs."""
    await connection.async_connect()
    seen: list[bool] = []

    def explode(_value: bool) -> None:
        raise ValueError("boom")

    await connection.async_subscribe(7, explode)
    await connection.async_subscribe(7, seen.append)
    FakeIHCController.instances[-1].notify(7, True)
    await asyncio.sleep(0)
    assert seen == [True]
    assert "Error handling IHC value" in caplog.text


async def test_close_stops_listening(connection):
    """Closing logs out and forgets the subscriptions."""
    await connection.async_connect()
    await connection.async_subscribe(7, lambda _value: None)
    await connection.async_close()
    assert FakeIHCController.instances[-1].disconnected is True
    assert connection._listeners == {}


async def test_timer_and_time_commands(connection):
    """A timer takes milliseconds; a time of day takes three values, sent as one command."""
    connection.register([1, 2])
    await connection.async_set_timer(1, 1500)
    await connection.async_set_time(2, 6, 45, 30)
    assert FakeIHCController.instances[-1].commands == [("timer", 1, 1500), ("time", 2, (6, 45, 30))]
