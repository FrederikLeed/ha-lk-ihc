"""Turn a key going down and up into the gestures an automation can pick from.

The controller says only two things about a key on a wall switch: it went down, and it came up.
Everything else - a short press, a long one, a double press - is a matter of timing, worked out
here, so an automation can pick the gesture it wants from the event entity's list instead of
timing the key itself.

This module knows nothing about Home Assistant. It is given a function that fires an event and one
that schedules a call, so it can be tested with a clock the test controls.
"""

from __future__ import annotations

from collections.abc import Callable

from .const import (
    DOUBLE_PRESS_SECONDS,
    EVENT_DOUBLE_PRESS,
    EVENT_LONG_PRESS,
    EVENT_LONG_RELEASE,
    EVENT_PRESS,
    EVENT_SHORT_RELEASE,
    EVENT_SINGLE_PRESS,
    LONG_PRESS_SECONDS,
)

# Schedule a call in some seconds, and return a function that cancels it.
type Schedule = Callable[[float, Callable[[], None]], Callable[[], None]]


class KeyGestures:
    """The gestures of one key.

    - press: every time the key goes down, at once.
    - long_press: the key has been held for LONG_PRESS_SECONDS, while it is still held.
    - long_release: the key came up after a long press.
    - short_release: the key came up before it became a long press.
    - double_press: the key went down again within DOUBLE_PRESS_SECONDS of a short release.
    - single_press: a short press that no second press followed. It comes DOUBLE_PRESS_SECONDS
      after the release, because only then is it known not to be the start of a double press.

    press still comes at once for every press, so nothing that only wants a press waits.
    """

    def __init__(self, fire: Callable[[str], None], schedule: Schedule) -> None:
        """Fire events with fire, and time the gestures with schedule."""
        self._fire = fire
        self._schedule = schedule
        self._down = False
        self._long = False
        # The second press of a double press has no single press of its own to wait for.
        self._second_press = False
        self._cancel_long: Callable[[], None] | None = None
        self._cancel_single: Callable[[], None] | None = None

    def down(self) -> None:
        """Handle the key going down."""
        if self._down:
            return
        self._down = True
        self._long = False
        self._fire(EVENT_PRESS)
        if self._cancel_single is not None:
            self._cancel_single()
            self._cancel_single = None
            self._second_press = True
            self._fire(EVENT_DOUBLE_PRESS)
        self._cancel_long = self._schedule(LONG_PRESS_SECONDS, self._held)

    def up(self) -> None:
        """Handle the key coming up."""
        if not self._down:
            return
        self._down = False
        if self._cancel_long is not None:
            self._cancel_long()
            self._cancel_long = None
        if self._long:
            self._second_press = False
            self._fire(EVENT_LONG_RELEASE)
            return
        self._fire(EVENT_SHORT_RELEASE)
        if self._second_press:
            self._second_press = False
            return
        self._cancel_single = self._schedule(DOUBLE_PRESS_SECONDS, self._no_second_press)

    def cancel(self) -> None:
        """Stop anything still waiting, when the entity goes away."""
        for cancel in (self._cancel_long, self._cancel_single):
            if cancel is not None:
                cancel()
        self._cancel_long = self._cancel_single = None

    def _held(self) -> None:
        """The key is still down after LONG_PRESS_SECONDS."""
        self._cancel_long = None
        if self._down:
            self._long = True
            self._fire(EVENT_LONG_PRESS)

    def _no_second_press(self) -> None:
        """No second press came in time, so the press was a single press."""
        self._cancel_single = None
        self._fire(EVENT_SINGLE_PRESS)
