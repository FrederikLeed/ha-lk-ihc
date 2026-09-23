"""Read the parts of the controller the project file does not describe.

The project file says what is installed. It says nothing about how the installation is doing:
whether a wireless switch is still being heard, whether the controller's clock has drifted, or
whether someone has changed the project since Home Assistant last read it. The controller knows
all of that, over SOAP services ihcsdk does not wrap.

Everything here is read-only on purpose. These are the controller's own settings - its address,
its clock, who may administer it - and changing them belongs in IHC Administrator, where an
installer can see what they are doing. Reading them costs one request and makes the difference
between an installation you can watch and one you can only hope about.

The calls are raw SOAP because ihcsdk has no client for these services. Each returns None when the
controller does not answer, which is normal: an older controller simply does not implement some of
them, and no controller should be nagged about a service it never had.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from xml.etree.ElementTree import Element

_LOGGER = logging.getLogger(__name__)

_AIRLINK = "/ws/AirlinkManagementService"
_CONTROLLER = "/ws/ControllerService"
_CONFIGURATION = "/ws/ConfigurationService"
_TIME = "/ws/TimeManagerService"


# The controller answers with its own namespace on every element, so a tag is matched on its local
# name. Doing it here keeps the callers free of namespace handling.
def _local(tag: str) -> str:
    """Return an element tag without its namespace."""
    return tag.rsplit("}", 1)[-1]


def _fields(item: Element | None) -> dict[str, str]:
    """Return one SOAP struct as plain strings, keyed by local tag name.

    An Element is falsy when it has no children, so callers must never lean on `or` to supply a
    default. None is accepted here instead, which is what a missing struct actually means.
    """
    if item is None:
        return {}
    return {_local(child.tag): (child.text or "").strip() for child in item}


def _first(root: Element, name: str) -> Element | None:
    """Return the first element with this local name, anywhere in the response."""
    return next((element for element in root.iter() if _local(element.tag) == name), None)


def _int(value: str | None, default: int | None = None) -> int | None:
    """Return a SOAP integer, or the default when it is missing or not a number."""
    try:
        return int(value) if value is not None and value != "" else default
    except ValueError:
        return default


def _ip(value: str | None) -> str | None:
    """Return an IPv4 address the controller sends as a signed 32 bit number.

    getDNSServers reports 8.8.8.8 as 134744072 and anything above 127.x as a negative number,
    because the value is read as signed. Masking to 32 bits undoes that before unpacking the bytes.
    """
    number = _int(value)
    if number is None:
        return None
    number &= 0xFFFFFFFF
    return ".".join(str((number >> shift) & 0xFF) for shift in (24, 16, 8, 0))


@dataclass(frozen=True, slots=True)
class RFDevice:
    """One wireless device as the controller currently hears it."""

    serial_number: int
    device_type: int
    # The controller reports battery as a flag, not a percentage: 1 is fine, 0 needs a battery.
    battery_ok: bool
    signal_strength: int
    detected: bool
    version: int | None = None

    @property
    def unique_key(self) -> str:
        """Return a stable key for this device, for an entity that outlives a restart."""
        return f"rf_{self.serial_number}"


@dataclass(frozen=True, slots=True)
class ControllerStatus:
    """What the controller says about itself, beyond the project file."""

    rf_devices: tuple[RFDevice, ...] = ()
    # The project's own revision. It changes when someone deploys a new project, which is the one
    # thing that can make every id Home Assistant holds go stale.
    project_major_revision: int | None = None
    project_minor_revision: int | None = None
    visual_major_version: int | None = None
    visual_minor_version: int | None = None
    controller_time: str | None = None
    time_synchronised: bool | None = None
    time_server: str | None = None
    gmt_offset_hours: int | None = None
    uses_dst: bool | None = None
    ip_address: str | None = None
    netmask: str | None = None
    gateway: str | None = None
    http_port: int | None = None
    https_port: int | None = None
    dns_servers: tuple[str, ...] = ()
    smtp_host: str | None = None

    @property
    def rf_devices_low_battery(self) -> int:
        """Return how many wireless devices are asking for a battery."""
        return sum(1 for device in self.rf_devices if not device.battery_ok)

    @property
    def rf_devices_unheard(self) -> int:
        """Return how many wireless devices the controller is not currently hearing."""
        return sum(1 for device in self.rf_devices if not device.detected)


class ControllerStatusReader:
    """Read the controller's own state over the SOAP services ihcsdk leaves alone."""

    def __init__(self, client: Any) -> None:
        """Keep the authenticated ihcsdk client; its connection carries the session cookie."""
        self._client = client

    def _call(self, service: str, action: str, payload: str = "") -> Element | None:
        """Send one SOAP action, returning None when the controller does not answer it."""
        try:
            result = self._client.connection.soap_action(service, action, payload)
        except Exception:  # noqa: BLE001 - a controller that misbehaves must not break setup
            _LOGGER.debug("IHC %s did not answer %s", service, action, exc_info=True)
            return None
        if result is False or result is None:
            # Not an error: older controllers do not implement every service.
            _LOGGER.debug("IHC %s has no %s", service, action)
            return None
        return result

    def read(self) -> ControllerStatus:
        """Read everything at once. Missing answers leave their fields as None."""
        return ControllerStatus(
            rf_devices=self._rf_devices(),
            **self._project_info(),
            **self._time(),
            **self._network(),
            smtp_host=self._smtp_host(),
        )

    def _rf_devices(self) -> tuple[RFDevice, ...]:
        """Return every wireless device the controller has registered."""
        root = self._call(_AIRLINK, "getDetectedDeviceList")
        if root is None:
            return ()
        devices: list[RFDevice] = []
        for item in root.iter():
            if _local(item.tag) != "arrayItem":
                continue
            data = _fields(item)
            serial = _int(data.get("serialNumber"))
            if serial is None:
                continue
            devices.append(
                RFDevice(
                    serial_number=serial,
                    device_type=_int(data.get("deviceType"), 0) or 0,
                    battery_ok=_int(data.get("batteryLevel"), 1) != 0,
                    signal_strength=_int(data.get("signalStrength"), 0) or 0,
                    detected=data.get("detected", "true") == "true",
                    version=_int(data.get("version")),
                )
            )
        return tuple(devices)

    def _project_info(self) -> dict[str, Any]:
        """Return the project's version and revision, which change when a project is deployed."""
        root = self._call(_CONTROLLER, "getProjectInfo")
        if root is None:
            return {}
        data = _fields(_first(root, "getProjectInfo1"))
        return {
            "project_major_revision": _int(data.get("projectMajorRevision")),
            "project_minor_revision": _int(data.get("projectMinorRevision")),
            "visual_major_version": _int(data.get("visualMajorVersion")),
            "visual_minor_version": _int(data.get("visualMinorVersion")),
        }

    def _time(self) -> dict[str, Any]:
        """Return the controller's clock and how it is kept.

        A controller runs its own time-based logic, so a clock that has drifted quietly changes
        when the house does things. Worth being able to see.
        """
        result: dict[str, Any] = {}
        settings = self._call(_TIME, "getSettings")
        if settings is not None:
            data = _fields(_first(settings, "getSettings1"))
            result |= {
                "time_synchronised": data.get("synchroniseTimeAgainstServer") == "true",
                "time_server": data.get("serverName") or None,
                "gmt_offset_hours": _int(data.get("gmtOffsetInHours")),
                "uses_dst": data.get("useDST") == "true",
            }
        now = self._call(_TIME, "getCurrentLocalTime")
        if now is not None:
            data = _fields(_first(now, "getCurrentLocalTime1"))
            year, month = _int(data.get("year")), _int(data.get("monthWithJanuaryAsOne"))
            day, hours = _int(data.get("day")), _int(data.get("hours"))
            minutes, seconds = _int(data.get("minutes")), _int(data.get("seconds"))
            if None not in (year, month, day, hours, minutes, seconds):
                result["controller_time"] = f"{year:04d}-{month:02d}-{day:02d}T{hours:02d}:{minutes:02d}:{seconds:02d}"
        return result

    def _network(self) -> dict[str, Any]:
        """Return the controller's address and name servers."""
        result: dict[str, Any] = {}
        settings = self._call(_CONFIGURATION, "getNetworkSettings")
        if settings is not None:
            data = _fields(_first(settings, "getNetworkSettings1"))
            result |= {
                "ip_address": data.get("ipAddress") or None,
                "netmask": data.get("netmask") or None,
                "gateway": data.get("gateway") or None,
                "http_port": _int(data.get("httpPort")),
                "https_port": _int(data.get("httpsPort")),
            }
        dns = self._call(_CONFIGURATION, "getDNSServers")
        if dns is not None:
            servers = [_ip(_fields(item).get("ipAddress")) for item in dns.iter() if _local(item.tag) == "arrayItem"]
            result["dns_servers"] = tuple(server for server in servers if server and server != "0.0.0.0")
        return result

    def _smtp_host(self) -> str | None:
        """Return the mail server the controller sends through, when one is configured."""
        root = self._call(_CONFIGURATION, "getSMTPSettings")
        if root is None:
            return None
        return _fields(_first(root, "getSMTPSettings1")).get("hostname") or None
