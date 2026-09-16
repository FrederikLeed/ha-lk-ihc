"""The LK IHC integration: an IHC controller set up from the user interface."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_URL, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr

from .const import CONF_READ_ONLY, DEFAULT_READ_ONLY, DOMAIN
from .controller import IHCAuthError, IHCConnectError, IHCConnection
from .project import Project, parse_project

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.EVENT,
    Platform.LIGHT,
    Platform.SENSOR,
    Platform.SWITCH,
]


@dataclass
class IHCData:
    """What the platforms need: the connection, the installation, and the controller's device."""

    connection: IHCConnection
    project: Project
    # The registry id of the controller device, so every product device can point at it.
    controller_device_id: str = ""


type IHCConfigEntry = ConfigEntry[IHCData]


async def async_setup_entry(hass: HomeAssistant, entry: IHCConfigEntry) -> bool:
    """Connect to the controller, read the installation and create the entities."""
    connection = IHCConnection(
        hass,
        entry.data[CONF_URL],
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
    )
    try:
        await connection.async_connect()
        project_xml = await connection.async_project()
    except IHCAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except IHCConnectError as err:
        raise ConfigEntryNotReady(str(err)) from err

    project = parse_project(project_xml)
    connection.register([resource.ihc_id for _product, resource in project.resources])
    connection.read_only = entry.options.get(CONF_READ_ONLY, DEFAULT_READ_ONLY)
    _LOGGER.debug(
        "IHC controller %s: %s products, %s resources %s",
        connection.serial_number,
        len(project.products),
        len(project.resources),
        project.counts(),
    )

    device_registry = dr.async_get(hass)
    controller_device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, connection.serial_number)},
        manufacturer="LK",
        name=entry.title,
        model="IHC controller",
        sw_version=connection.info.get("version"),
        hw_version=connection.info.get("hw_revision"),
        configuration_url=entry.data[CONF_URL],
        serial_number=connection.serial_number,
    )
    entry.runtime_data = IHCData(
        connection=connection,
        project=project,
        controller_device_id=controller_device.id,
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: IHCConfigEntry) -> bool:
    """Close the connection and remove the entities."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.connection.async_close()
    return unloaded


async def _async_options_updated(hass: HomeAssistant, entry: IHCConfigEntry) -> None:
    """Reload after an option change, so read-only and the exposed entities always match the options."""
    await hass.config_entries.async_reload(entry.entry_id)
