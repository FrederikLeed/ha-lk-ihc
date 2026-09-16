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
        },
    }
