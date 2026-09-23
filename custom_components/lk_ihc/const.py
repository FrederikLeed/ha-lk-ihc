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

# The event types a key on a wall switch fires - see gestures.py for what each one means. press is
# the one there has always been; short_release, long_press and long_release are the names Home
# Assistant's Hue and Matter buttons use for the same gestures.
EVENT_PRESS: Final = "press"
EVENT_SINGLE_PRESS: Final = "single_press"
EVENT_DOUBLE_PRESS: Final = "double_press"
EVENT_LONG_PRESS: Final = "long_press"
EVENT_SHORT_RELEASE: Final = "short_release"
EVENT_LONG_RELEASE: Final = "long_release"
BUTTON_EVENT_TYPES: Final = [
    EVENT_PRESS,
    EVENT_SINGLE_PRESS,
    EVENT_DOUBLE_PRESS,
    EVENT_LONG_PRESS,
    EVENT_SHORT_RELEASE,
    EVENT_LONG_RELEASE,
]

# Seconds a key must be held before it is a long press.
LONG_PRESS_SECONDS: Final = 0.8
# Seconds after a short release in which a new press makes it a double press.
DOUBLE_PRESS_SECONDS: Final = 0.3
