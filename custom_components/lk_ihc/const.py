"""Constants for the LK IHC integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "lk_ihc"

CONF_READ_ONLY: Final = "read_only"
CONF_EXPOSE_BUTTONS: Final = "expose_buttons"

# A new entry starts read only: it shows the whole installation and never sends a command, so an
# installation can be looked over before anything in the house can be switched from Home Assistant.
DEFAULT_READ_ONLY: Final = True
DEFAULT_EXPOSE_BUTTONS: Final = True

# Seconds to wait for the controller when connecting or reading the project.
CONNECT_TIMEOUT: Final = 30
# Seconds to wait for a single command.
COMMAND_TIMEOUT: Final = 10
# Seconds any single HTTP request to the controller may take. The sdk sets none of its own.
HTTP_TIMEOUT: Final = 20

# The event type an event entity fires when a key is pressed, and the attribute that carries it.
EVENT_PRESS: Final = "press"
