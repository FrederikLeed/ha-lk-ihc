"""Diagnostics for an IHC controller entry, with nothing personal in them."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD, CONF_URL, CONF_USERNAME
from homeassistant.core import HomeAssistant

from . import IHCConfigEntry
from .catalog import is_known

# The address and the login say where the house is and how to get in; the product names and
# positions say what the rooms are called. None of it helps with a bug report.
REDACT = {CONF_PASSWORD, CONF_USERNAME, CONF_URL}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: IHCConfigEntry) -> dict[str, Any]:
    """Return what the installation is made of, without saying whose it is."""
    data = entry.runtime_data
    connection = data.connection
    return {
        "entry": {
            "options": dict(entry.options),
            "data": async_redact_data(dict(entry.data), REDACT),
        },
        "controller": {
            "version": connection.info.get("version"),
            "hw_revision": connection.info.get("hw_revision"),
            "sw_date": connection.info.get("sw_date"),
            "brand": connection.info.get("brand"),
            "dataline_version": connection.info.get("dataline_version"),
            "read_only": connection.read_only,
        },
        "installation": {
            "groups": len(data.project.groups),
            "products": len(data.project.products),
            "resources": len(data.project.resources),
            "roles": data.project.counts(),
            # The identifiers, not the readable model names: an unrecognised product takes its name
            # from the project file, which is text the owner wrote about their own house.
            "product_ids": sorted({product.model_id for product in data.project.products if product.model_id}),
            "unrecognised_products": sum(1 for product in data.project.products if not is_known(product.identifier)),
            "function_blocks": len(data.project.function_blocks),
            # How much of the installation's own logic we could trace. A product with no wiring
            # is either driven by nothing or by something the link graph does not reach.
            "products_with_wiring": sum(1 for product in data.project.products if product.controlled_by),
        },
        # What the controller says about itself. None of it is controlled from here, but an
        # installation you cannot see the state of is one you can only guess about.
        "status": _status(data),
    }


def _status(data: Any) -> dict[str, Any]:
    """Return the controller's own state, or why there is none."""
    status = getattr(data, "status", None)
    if status is None:
        return {}
    return {
        "rf_devices": len(status.rf_devices),
        "rf_devices_low_battery": status.rf_devices_low_battery,
        "rf_devices_unheard": status.rf_devices_unheard,
        # Signal strength per device, without the serial numbers, which identify someone's hardware.
        "rf_signal_strength": sorted(device.signal_strength for device in status.rf_devices),
        "project_major_revision": status.project_major_revision,
        "project_minor_revision": status.project_minor_revision,
        "controller_time": status.controller_time,
        "time_synchronised": status.time_synchronised,
        "gmt_offset_hours": status.gmt_offset_hours,
        "uses_dst": status.uses_dst,
        "http_port": status.http_port,
        "https_port": status.https_port,
        "smtp_configured": bool(status.smtp_host),
    }
