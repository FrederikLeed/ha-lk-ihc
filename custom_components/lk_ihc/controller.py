"""Talk to the IHC controller without blocking Home Assistant, and without surprising the house.

The ihcsdk is synchronous and pushes notifications from a thread of its own, so everything it does
runs in an executor and every notification is handed back to the event loop before an entity sees
it.

Two rules are enforced here rather than in the platforms, so there is one place to check:

- In read-only mode no command is ever sent. Reading the installation stays fully available.
- A command is only sent for a resource that came from the project file, so a bad id cannot be
  written into an installation by mistake.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from ihcsdk.ihccontroller import IHCController

from .const import COMMAND_TIMEOUT, CONNECT_TIMEOUT, DOMAIN, HTTP_TIMEOUT
from .services import ControllerStatus, ControllerStatusReader

_LOGGER = logging.getLogger(__name__)

type ValueCallback = Callable[[Any], None]


class IHCAuthError(HomeAssistantError):
    """The controller refused the username or password."""


class IHCConnectError(HomeAssistantError):
    """The controller could not be reached, or did not answer in time."""


class IHCReadOnlyError(ServiceValidationError):
    """A command was attempted while the entry is in read-only mode.

    A validation error rather than a plain failure: nothing is broken, the integration is set up
    that way, and Home Assistant then shows the reason instead of a server error with a traceback.
    """


def apply_http_timeout(controller: IHCController, timeout: float = HTTP_TIMEOUT) -> bool:
    """Give the sdk's HTTP session a timeout, and say whether it could be set.

    ihcsdk posts to the controller with no timeout at all, so a controller that accepts a connection
    and then stops answering would hold on to a Home Assistant executor thread for as long as the
    socket stays open. Nothing above this can cut that short: a job already running in an executor
    cannot be cancelled. So the bound has to be on the request itself.
    """
    try:
        session = controller.client.connection.session
        original_post = session.post
    except AttributeError:  # a different sdk version, or a stand-in in a test
        _LOGGER.debug("Could not set an HTTP timeout on the IHC session")
        return False

    def post_with_timeout(*args: Any, **kwargs: Any) -> Any:
        kwargs.setdefault("timeout", timeout)
        return original_post(*args, **kwargs)

    session.post = post_with_timeout
    return True


def last_transport_error(controller: Any) -> Exception | None:
    """The exception the sdk swallowed on its last request, if there was one.

    The sdk's soap_action catches a transport or parse error, logs it and returns False, so a login
    that never reached the controller comes back exactly like one the controller refused. The
    connection object keeps the exception, and that is the only way to tell the two apart. When a
    Home Assistant host boots faster than the network or the controller answers, this is the
    difference between retrying setup and wrongly asking for the password.
    """
    try:
        return controller.client.connection.last_exception
    except AttributeError:  # a different sdk version, or a stand-in in a test
        return None


class IHCConnection:
    """One connection to one IHC controller."""

    def __init__(self, hass: HomeAssistant, url: str, username: str, password: str) -> None:
        """Prepare a connection. Nothing is sent until async_connect."""
        self.hass = hass
        self.url = url
        self._controller = IHCController(url, username, password)
        apply_http_timeout(self._controller)
        self._listeners: dict[int, list[ValueCallback]] = {}
        self._known_ids: set[int] = set()
        self._values: dict[int, Any] = {}
        self.info: dict[str, Any] = {}
        self.read_only = True

    # --- connecting ---------------------------------------------------------

    async def async_connect(self) -> dict[str, Any]:
        """Authenticate and return the controller's system information.

        The timeout here bounds the wait for an executor slot; the request itself is bounded by the
        HTTP timeout set in apply_http_timeout, because a running executor job cannot be cancelled.
        """
        try:
            async with asyncio.timeout(CONNECT_TIMEOUT):
                authenticated = await self.hass.async_add_executor_job(self._controller.authenticate)
        except TimeoutError as err:
            raise IHCConnectError(f"The IHC controller at {self.url} did not answer in time") from err
        except Exception as err:  # the sdk raises whatever the transport raised
            raise IHCConnectError(f"Could not reach the IHC controller at {self.url}: {err}") from err
        if not authenticated:
            transport_error = last_transport_error(self._controller)
            if transport_error is not None:
                # The login never reached the controller. Reported as a connection problem, so
                # setup is retried - an auth error would stop retrying and ask for the password.
                raise IHCConnectError(
                    f"Could not reach the IHC controller at {self.url}: {transport_error}"
                ) from transport_error
            raise IHCAuthError("The IHC controller refused the username or password")
        self.info = await self.hass.async_add_executor_job(self._controller.client.get_system_info) or {}
        return self.info

    async def async_project(self) -> str:
        """Return the project XML, which describes the whole installation."""
        try:
            async with asyncio.timeout(CONNECT_TIMEOUT):
                project = await self.hass.async_add_executor_job(self._controller.get_project)
        except TimeoutError as err:
            raise IHCConnectError("The IHC controller did not send the project in time") from err
        if not project:
            raise IHCConnectError("The IHC controller did not return a project")
        return project

    async def async_status(self) -> ControllerStatus:
        """Read what the controller says about itself, in an executor.

        Never fatal: a controller that will not answer these is still perfectly usable, and an
        installation should not fail to set up because it cannot report its own signal strength.
        """
        try:
            return await self.hass.async_add_executor_job(ControllerStatusReader(self._controller.client).read)
        except Exception:  # noqa: BLE001 - status is a nicety, the installation is not
            _LOGGER.debug("Could not read the controller's own status", exc_info=True)
            return ControllerStatus()

    async def async_close(self) -> None:
        """Stop notifications and log out."""
        self._listeners.clear()
        await self.hass.async_add_executor_job(self._controller.disconnect)

    @property
    def serial_number(self) -> str:
        """Return the controller's serial number, which identifies the config entry."""
        return str(self.info.get("serial_number") or "").strip()

    # --- reading ------------------------------------------------------------

    def register(self, ihc_ids: list[int]) -> None:
        """Record which resources exist, so a command can only go to one of them."""
        self._known_ids.update(ihc_ids)

    async def async_subscribe(self, ihc_id: int, value_callback: ValueCallback) -> None:
        """Call value_callback whenever the controller reports a new value for this resource.

        The first value arrives the same way, because the sdk asks for the current value when the
        notification is enabled, so entities start with the real state of the house.
        """
        self._listeners.setdefault(ihc_id, []).append(value_callback)
        if len(self._listeners[ihc_id]) == 1:
            await self.hass.async_add_executor_job(
                self._controller.add_notify_event, ihc_id, self._on_notification, True
            )
        elif ihc_id in self._values:
            value_callback(self._values[ihc_id])

    def _on_notification(self, ihc_id: int, value: Any) -> None:
        """Handle a value from the sdk's notify thread. Runs outside the event loop."""
        self.hass.loop.call_soon_threadsafe(self._dispatch, ihc_id, value)

    @callback
    def _dispatch(self, ihc_id: int, value: Any) -> None:
        """Hand a new value to the entities that asked for it."""
        self._values[ihc_id] = value
        for value_callback in self._listeners.get(ihc_id, []):
            try:
                value_callback(value)
            except Exception:  # one bad entity must not stop the others
                _LOGGER.exception("Error handling IHC value for resource %s", ihc_id)

    def value(self, ihc_id: int) -> Any | None:
        """Return the last value seen for a resource."""
        return self._values.get(ihc_id)

    # --- writing ------------------------------------------------------------

    async def async_set_bool(self, ihc_id: int, value: bool) -> None:
        """Switch a resource on or off."""
        await self._async_command(self._controller.set_runtime_value_bool, ihc_id, value)

    async def async_set_int(self, ihc_id: int, value: int) -> None:
        """Set a whole number on a resource, such as a light level."""
        await self._async_command(self._controller.set_runtime_value_int, ihc_id, value)

    async def async_set_float(self, ihc_id: int, value: float) -> None:
        """Set a decimal number on a resource."""
        await self._async_command(self._controller.set_runtime_value_float, ihc_id, value)

    async def async_set_timer(self, ihc_id: int, milliseconds: int) -> None:
        """Set a timer resource, such as a function block's own timer."""
        await self._async_command(self._controller.set_runtime_value_timer, ihc_id, milliseconds)

    async def async_set_time(self, ihc_id: int, hours: int, minutes: int, seconds: int) -> None:
        """Set a time-of-day resource."""
        await self._async_command(self._controller.set_runtime_value_time, ihc_id, hours, minutes, seconds)

    async def async_pulse(self, ihc_id: int) -> None:
        """Send a short on and off, the way a wall switch does."""
        await self.async_set_bool(ihc_id, True)
        await asyncio.sleep(0.1)
        await self.async_set_bool(ihc_id, False)

    async def _async_command(self, method: Callable[..., bool], ihc_id: int, *values: Any) -> None:
        """Send one command, after the two safety checks. Most take one value; a time takes three."""
        if self.read_only:
            raise IHCReadOnlyError(translation_domain=DOMAIN, translation_key="read_only")
        if ihc_id not in self._known_ids:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="unknown_resource",
                translation_placeholders={"resource": str(ihc_id)},
            )
        try:
            async with asyncio.timeout(COMMAND_TIMEOUT):
                sent = await self.hass.async_add_executor_job(method, ihc_id, *values)
        except TimeoutError as err:
            raise IHCConnectError(f"The IHC controller did not accept the command for {ihc_id} in time") from err
        if not sent:
            raise IHCConnectError(f"The IHC controller rejected the command for resource {ihc_id}")
