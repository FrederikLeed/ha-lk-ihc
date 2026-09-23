"""The controller's own state, read from the services ihcsdk does not wrap."""

from __future__ import annotations

from xml.etree.ElementTree import fromstring

import pytest

from custom_components.lk_ihc.services import ControllerStatusReader, _ip

DEVICE_LIST = """<Envelope xmlns="utcs"><Body><getDetectedDeviceList1>
  <arrayItem><batteryLevel>1</batteryLevel><deviceType>2049</deviceType>
    <serialNumber>109955577299476</serialNumber><version>1</version>
    <detected>true</detected><signalStrength>22</signalStrength></arrayItem>
  <arrayItem><batteryLevel>0</batteryLevel><deviceType>2057</deviceType>
    <serialNumber>109989939381363</serialNumber><version>1</version>
    <detected>false</detected><signalStrength>0</signalStrength></arrayItem>
</getDetectedDeviceList1></Body></Envelope>"""

TIME_SETTINGS = """<Envelope xmlns="utcs"><Body><getSettings1>
  <synchroniseTimeAgainstServer>true</synchroniseTimeAgainstServer>
  <useDST>true</useDST><gmtOffsetInHours>1</gmtOffsetInHours>
  <serverName>europe.pool.ntp.org</serverName></getSettings1></Body></Envelope>"""

LOCAL_TIME = """<Envelope xmlns="utcs"><Body><getCurrentLocalTime1>
  <day>23</day><monthWithJanuaryAsOne>9</monthWithJanuaryAsOne><year>2026</year>
  <hours>12</hours><minutes>20</minutes><seconds>2</seconds>
</getCurrentLocalTime1></Body></Envelope>"""

DNS = """<Envelope xmlns="utcs"><Body><getDNSServers1>
  <arrayItem><ipAddress>134744072</ipAddress></arrayItem>
  <arrayItem><ipAddress>-1062729206</ipAddress></arrayItem>
  <arrayItem><ipAddress>0</ipAddress></arrayItem>
</getDNSServers1></Body></Envelope>"""


class FakeConnection:
    """Answer the actions a controller implements, and refuse the rest like an old one does."""

    def __init__(self, answers: dict[str, str]) -> None:
        self.answers = answers
        self.calls: list[tuple[str, str]] = []

    def soap_action(self, service: str, action: str, payload: str = ""):
        self.calls.append((service, action))
        body = self.answers.get(action)
        return fromstring(body) if body is not None else False


class FakeClient:
    def __init__(self, answers: dict[str, str]) -> None:
        self.connection = FakeConnection(answers)


def test_reads_rf_devices() -> None:
    """Battery is a flag, not a percentage, and a device can be registered but unheard."""
    status = ControllerStatusReader(FakeClient({"getDetectedDeviceList": DEVICE_LIST})).read()
    assert len(status.rf_devices) == 2
    first, second = status.rf_devices
    assert first.battery_ok is True
    assert first.signal_strength == 22
    assert first.unique_key == "rf_109955577299476"
    assert second.battery_ok is False
    assert second.detected is False
    assert status.rf_devices_low_battery == 1
    assert status.rf_devices_unheard == 1


def test_reads_the_clock_and_how_it_is_kept() -> None:
    """A controller runs its own time-based logic, so its clock is worth seeing."""
    status = ControllerStatusReader(
        FakeClient({"getSettings": TIME_SETTINGS, "getCurrentLocalTime": LOCAL_TIME})
    ).read()
    assert status.controller_time == "2026-09-23T12:20:02"
    assert status.time_synchronised is True
    assert status.time_server == "europe.pool.ntp.org"
    assert status.gmt_offset_hours == 1
    assert status.uses_dst is True


def test_reads_dns_servers_sent_as_signed_numbers() -> None:
    """The controller reports an address as a signed 32 bit number; unset servers are dropped."""
    status = ControllerStatusReader(FakeClient({"getDNSServers": DNS})).read()
    assert status.dns_servers == ("8.8.8.8", "192.168.10.10")


@pytest.mark.parametrize(
    ("number", "expected"),
    [("134744072", "8.8.8.8"), ("-1062729206", "192.168.10.10"), ("0", "0.0.0.0"), ("", None), (None, None)],
)
def test_ip_from_signed_number(number: str | None, expected: str | None) -> None:
    """Anything above 127.x arrives negative, because the controller reads the value as signed."""
    assert _ip(number) == expected


def test_a_controller_without_these_services_reads_as_empty() -> None:
    """An older controller implements only some of this, and must not be treated as broken."""
    client = FakeClient({})
    status = ControllerStatusReader(client).read()
    assert status.rf_devices == ()
    assert status.controller_time is None
    assert status.ip_address is None
    # Every service was still asked once, so a controller that gains one is picked up on reload.
    assert ("/ws/AirlinkManagementService", "getDetectedDeviceList") in client.connection.calls
