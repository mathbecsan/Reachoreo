"""The show clock. The conductor owns it; every other process follows it.

Show time 0 is the first downbeat of the music. Negative show time is the countdown.
Followers estimate the conductor's clock from its broadcasts; network delay only ever
makes a message look older, so the best estimate is the freshest one in a short window.
"""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass

IDLE, COUNTDOWN, PLAYING, PAUSED, ENDED = "idle", "countdown", "playing", "paused", "ended"


def now() -> float:
    return time.monotonic()


@dataclass
class ShowClock:
    """Conductor side."""
    state: str = IDLE
    _t0: float = 0.0          # monotonic time at show time 0
    _held: float = 0.0        # show time while paused or idle

    def start(self, show_t: float):
        """Begin running so that the current instant is show time `show_t` (negative for a countdown)."""
        self._t0 = now() - show_t
        self.state = COUNTDOWN if show_t < 0 else PLAYING

    def pause(self):
        self._held = self.show_time()
        self.state = PAUSED

    def resume(self):
        self.start(self._held)

    def stop(self):
        self._held = self.show_time()
        self.state = ENDED

    def show_time(self) -> float:
        if self.state in (COUNTDOWN, PLAYING):
            t = now() - self._t0
            if self.state == COUNTDOWN and t >= 0:
                self.state = PLAYING
            return t
        return self._held

    def message(self, bpm: float) -> dict:
        return {"state": self.state, "show_t": self.show_time(), "bpm": bpm, "sent": time.time()}


class ClockFollower:
    """Agent side: turns clock broadcasts into a local estimate of show time."""

    def __init__(self, window_s: float = 2.0):
        self.window_s = window_s
        self.samples: deque = deque()
        self.state = IDLE
        self.held = 0.0
        self.last_rx = None

    def on_message(self, msg: dict, rx_time: float | None = None):
        rx = now() if rx_time is None else rx_time
        self.last_rx = rx
        self.state = msg["state"]
        if self.state in (COUNTDOWN, PLAYING):
            self.samples.append((rx, msg["show_t"] - rx))
            while self.samples and rx - self.samples[0][0] > self.window_s:
                self.samples.popleft()
        else:
            self.samples.clear()
            self.held = msg["show_t"]

    def age(self, at: float | None = None) -> float:
        if self.last_rx is None:
            return float("inf")
        return (now() if at is None else at) - self.last_rx

    def show_time(self, at: float | None = None) -> float:
        at = now() if at is None else at
        if self.state in (COUNTDOWN, PLAYING) and self.samples:
            offset = max(o for _, o in self.samples)
            return at + offset
        return self.held
