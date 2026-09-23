"""Tests for working out a key's gestures from it going down and up.

KeyGestures knows nothing about Home Assistant, so these run on a clock the test moves by hand.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from custom_components.lk_ihc.const import DOUBLE_PRESS_SECONDS, LONG_PRESS_SECONDS
from custom_components.lk_ihc.gestures import KeyGestures


class Clock:
    """Calls scheduled for later, run when the test moves time on."""

    def __init__(self) -> None:
        """Start at zero with nothing waiting."""
        self.now = 0.0
        self._waiting: list[list] = []

    def schedule(self, seconds: float, action: Callable[[], None]) -> Callable[[], None]:
        """Schedule action, and return what cancels it."""
        call = [self.now + seconds, action, False]
        self._waiting.append(call)

        def cancel() -> None:
            call[2] = True

        return cancel

    def advance(self, seconds: float) -> None:
        """Move time on, running every call that falls due."""
        self.now += seconds
        for call in sorted(self._waiting, key=lambda waiting: waiting[0]):
            if call[0] <= self.now and not call[2]:
                call[2] = True
                call[1]()


@pytest.fixture
def clock() -> Clock:
    """A clock the test moves by hand."""
    return Clock()


@pytest.fixture
def fired() -> list[str]:
    """The events fired, in order."""
    return []


@pytest.fixture
def key(clock: Clock, fired: list[str]) -> KeyGestures:
    """One key, firing into the list."""
    return KeyGestures(fired.append, clock.schedule)


def test_a_short_press_is_a_single_press(key, clock, fired):
    """Down and up quickly: press at once, the release, and the single press once no second came."""
    key.down()
    assert fired == ["press"]
    clock.advance(0.2)
    key.up()
    assert fired == ["press", "short_release"]
    clock.advance(DOUBLE_PRESS_SECONDS)
    assert fired == ["press", "short_release", "single_press"]


def test_two_quick_presses_are_a_double_press(key, clock, fired):
    """A second press soon after a short release is a double press, and no single press follows."""
    key.down()
    clock.advance(0.1)
    key.up()
    clock.advance(DOUBLE_PRESS_SECONDS / 2)
    key.down()
    clock.advance(0.1)
    key.up()
    clock.advance(DOUBLE_PRESS_SECONDS * 2)
    assert fired == ["press", "short_release", "press", "double_press", "short_release"]


def test_a_second_press_too_late_is_two_single_presses(key, clock, fired):
    """Outside the window, each press is a single press of its own."""
    for _ in range(2):
        key.down()
        clock.advance(0.1)
        key.up()
        clock.advance(DOUBLE_PRESS_SECONDS * 2)
    assert fired == ["press", "short_release", "single_press"] * 2


def test_a_held_key_is_a_long_press(key, clock, fired):
    """Held long enough, the long press comes while the key is still down, and the release says so."""
    key.down()
    clock.advance(LONG_PRESS_SECONDS)
    assert fired == ["press", "long_press"]
    clock.advance(1.0)
    key.up()
    clock.advance(DOUBLE_PRESS_SECONDS * 2)
    assert fired == ["press", "long_press", "long_release"]


def test_a_release_without_a_press_is_ignored(key, clock, fired):
    """Coming up without having gone down fires nothing, and neither does going down twice."""
    key.up()
    key.down()
    key.down()
    assert fired == ["press"]


def test_cancel_stops_what_is_waiting(key, clock, fired):
    """When the entity goes away, a waiting long or single press never fires."""
    key.down()
    key.cancel()
    clock.advance(LONG_PRESS_SECONDS * 2)
    assert fired == ["press"]
