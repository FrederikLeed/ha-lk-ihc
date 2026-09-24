"""The LK IHC integration: an IHC controller set up from the user interface."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_URL, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.typing import ConfigType

from .actions import async_register_actions
from .const import CONF_READ_ONLY, DEFAULT_READ_ONLY, DOMAIN
from .controller import IHCAuthError, IHCConnectError, IHCConnection
from .logic import Logic, parse_logic, parse_resource_ids
from .project import Project, parse_project
from .services import ControllerStatus

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
    # What the controller says about itself: wireless devices, its clock, its address. Read once at
    # setup, because none of it changes without someone visiting the controller.
    status: ControllerStatus = field(default_factory=ControllerStatus)
    # Flags, enums and block outputs from the controller's own logic, shown read-only on the controller.
    logic: Logic = field(default_factory=Logic)
    # The registry id of the controller device, so every product device can point at it.
    controller_device_id: str = ""


type IHCConfigEntry = ConfigEntry[IHCData]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the domain's actions. They exist once, and pick their controller per call."""
    async_register_actions(hass)
    return True


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
    logic = parse_logic(project_xml)
    status = await connection.async_status()
    # Every resource in the project may be the target of a command - not only the ones with an
    # entity. A timer inside a function block has no entity, but an action may want to set it.
    # Subscriptions are still made per entity; this only says what a command may be sent to.
    connection.register(sorted(parse_resource_ids(project_xml)))
    connection.read_only = entry.options.get(CONF_READ_ONLY, DEFAULT_READ_ONLY)
    _LOGGER.debug(
        "IHC controller %s: %s products, %s resources %s, %s wireless devices",
        connection.serial_number,
        len(project.products),
        len(project.resources),
        project.counts(),
        len(status.rf_devices),
    )
    _LOGGER.debug(
        "IHC logic: %s flags, %s enums, %s block outputs", len(logic.flags), len(logic.enums), len(logic.outputs)
    )
    _async_remove_stale_logic(hass, entry, connection.serial_number, logic)

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
        status=status,
        logic=logic,
        controller_device_id=controller_device.id,
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


@callback
def _async_remove_stale_logic(hass: HomeAssistant, entry: IHCConfigEntry, serial: str, logic: Logic) -> None:
    """Remove the entities of flags, enums and block outputs the project no longer has.

    Earlier versions read the values written inside the function blocks' programs as enums too -
    several hundred on a real installation - and a project changes whenever an installer edits it.
    Home Assistant keeps an entity the integration stops providing, so they would otherwise stay
    behind as unavailable. Only the controller's logic is touched, never a product's entities.
    """
    prefix = f"{serial}-logic-"
    wanted = {f"{prefix}{resource.ihc_id}" for resource in logic.resources}
    entities = er.async_get(hass)
    for registry_entry in er.async_entries_for_config_entry(entities, entry.entry_id):
        if registry_entry.unique_id.startswith(prefix) and registry_entry.unique_id not in wanted:
            entities.async_remove(registry_entry.entity_id)


async def async_unload_entry(hass: HomeAssistant, entry: IHCConfigEntry) -> bool:
    """Close the connection and remove the entities."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.connection.async_close()
    return unloaded


async def _async_options_updated(hass: HomeAssistant, entry: IHCConfigEntry) -> None:
    """Reload after an option change, so read-only and the exposed entities always match the options."""
    await hass.config_entries.async_reload(entry.entry_id)
