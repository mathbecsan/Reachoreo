"""Reactions: how a robot bends its score toward the live dancer and answers the other robot.

The score is the floor, never the ceiling: everything here is added on top of the scripted
pose, and fades back to zero when the dancer can't be seen. That keeps the show safe and
on time even if perception fails mid-performance.
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field

from .clock import now
from .pose import RobotPose
from .util import clamp, pulse

EARLY_BEATS = 0.25     # a cue this much before its window's first count still counts


@dataclass
class Impulse:
    action: str
    start: float          # show time
    amp: float = 1.0
    source: str = "dancer"
    id: str = ""
    cause: str = ""        # the dancer gesture that set it off (arm_out, jump, ...), for the pages


@dataclass
class DancerView:
    seen: bool = False
    x: float = 0.0
    depth: float = 0.0
    energy: float = 0.0
    rx: float = -1e9      # local monotonic receive time


@dataclass
class Reactor:
    side: str                       # "A" or "B"
    score: object                   # choreography module
    sheet: dict                     # phrase sheet (yaml)
    max_gaze_deg: float = 25.0
    yaw_deg: float = 40.0
    event_decay_s: float = 0.6
    echo_delay_beats: float = 1.0
    lost_after_s: float = 0.7
    dancer: DancerView = field(default_factory=DancerView)
    impulses: list = field(default_factory=list)
    fired: deque = field(default_factory=lambda: deque(maxlen=20))
    _seen_ids: set = field(default_factory=set)
    _fired_in_phrase: dict = field(default_factory=dict)

    @property
    def my_x(self) -> float:
        return self.score.POS[self.side]

    def phrase_react(self, t: float) -> dict:
        i = self.score.phrase_at(max(t, 0.0))
        return self.sheet["phrases"][i].get("react", {}) or {}

    def reset(self):
        """Forget reactions from a previous run. Call when the show (re)starts: rehearsing a section again
        replays the same show times, and old reactions must not count as duplicates of new ones."""
        self.impulses.clear()
        self.fired.clear()
        self._fired_in_phrase.clear()

    # ---- inputs ----
    def confidence(self, at: float | None = None) -> float:
        """1 while the dancer is freshly seen, fading to 0 over lost_after_s."""
        if not self.dancer.seen:
            return 0.0
        age = (now() if at is None else at) - self.dancer.rx
        return clamp(1 - max(0.0, age - 0.1) / self.lost_after_s)

    def on_dancer(self, msg: dict, show_t: float, rx: float | None = None):
        rx = now() if rx is None else rx
        if msg.get("seen"):
            self.dancer = DancerView(True, float(msg["x"]), float(msg.get("depth", 0.0)), float(msg.get("energy", 0.0)), rx)
        else:
            self.dancer.seen = False
        for ev in msg.get("events", []):
            self._on_event(ev, show_t)

    def on_peer(self, msg: dict, show_t: float):
        """The other robot reacted: echo it one beat later if this phrase allows."""
        for r in msg.get("reactions", []):
            key = f"peer:{r['id']}"
            if key in self._seen_ids:
                continue
            self._seen_ids.add(key)
            if r.get("source") == "echo" or not self.phrase_react(r["show_t"]).get("echo"):
                continue
            if any(f["source"] == "dancer" and abs(f["show_t"] - r["show_t"]) < 0.3 for f in self.fired):
                continue      # we already reacted to the same moment ourselves
            start = r["show_t"] + self.echo_delay_beats * self.score.BEAT
            if start >= show_t - self.event_decay_s:
                self._fire(Impulse(r["action"], start, 0.5, "echo", f"{self.side}-echo-{r['id']}"))

    def _on_event(self, ev: dict, show_t: float):
        eid = ev.get("id") or f"{ev['type']}@{ev.get('show_t', show_t):.2f}"
        if eid in self._seen_ids:
            return
        self._seen_ids.add(eid)
        t_ev = ev.get("show_t", show_t)
        if t_ev < show_t - 1.0:
            return            # stale (e.g. replayed after a restart); reacting now would be off the beat
        i0 = self.score.phrase_at(max(t_ev, 0.0))
        # A cue just before a phrase starts may belong to that phrase's first count.
        nxt = i0 + 1
        c_ev = self.score.count_of(t_ev)
        phrases = [i0] + ([nxt] if nxt < self.score.N_PHRASES and 8 * nxt - c_ev <= EARLY_BEATS else [])
        for i in phrases:
            count = c_ev - 8 * i
            react = self.sheet["phrases"][i].get("react", {}) or {}
            for trig in react.get("triggers", []):
                if trig["when"] != ev["type"]:
                    continue
                lo, hi = trig.get("counts", [0, 7])
                if not (lo - EARLY_BEATS <= count < hi + 1):    # dancers often land a hair before the count
                    continue
                if trig.get("side", "any") == "mine" and ev.get("side") != self.side:
                    continue
                once_key = (i, trig["when"], trig["action"])
                if self._fired_in_phrase.get(once_key, -1e9) > t_ev - 0.5:
                    continue      # debounce repeated detections
                self._fired_in_phrase[once_key] = t_ev
                self._fire(Impulse(trig["action"], t_ev, 1.0, "dancer", f"{self.side}-{eid}", trig["when"]))
                return

    def _fire(self, imp: Impulse):
        if imp.source == "dancer":
            # A reaction of our own replaces an echo scheduled for the same moment.
            clash = lambda s: abs(s - imp.start) < 0.3
            self.impulses = [i for i in self.impulses if not (i.source == "echo" and clash(i.start))]
            for f in [f for f in self.fired if f["source"] == "echo" and clash(f["show_t"])]:
                self.fired.remove(f)
        self.impulses.append(imp)
        self.fired.append({"id": imp.id, "action": imp.action, "show_t": imp.start, "source": imp.source, "cause": imp.cause})

    # ---- outputs ----
    def score_inputs(self, t: float):
        """Live dancer position for phrases that track, else None (the score uses its scripted path)."""
        if not self.phrase_react(t).get("track"):
            return None, None
        k = self.confidence()
        if k <= 0:
            return None, None
        sx, sd = self.score.scripted_dancer(t)
        return sx + k * (self.dancer.x - sx), sd + k * (self.dancer.depth - sd)

    def apply(self, base: RobotPose, t: float) -> RobotPose:
        p = base.copy()
        react = self.phrase_react(t)
        k = self.confidence()
        bl = self.score.count_of(t)
        hx = self.score.POS["C"] + self.dancer.x

        if k > 0 and react.get("gaze"):
            target = self.score.toward(self.my_x, hx)
            lim = self.max_gaze_deg / self.yaw_deg
            p.yaw += clamp(react["gaze"] * k * (target - p.yaw), -lim, lim)

        if k > 0 and react.get("energy"):
            extra = react["energy"] * k * (self.dancer.energy - 0.5)
            pp = pulse(bl)
            p.bob += -6 * pp * extra
            p.antL += 0.3 * pp * extra
            p.antR += 0.3 * pp * extra

        if k > 0 and react.get("lean"):
            d = abs(hx - self.my_x)
            if d < 320:
                w = react["lean"] * k * (1 - d / 320)
                p.roll += w * 0.2 * (1 if hx > self.my_x else -1)
                p.pitch += w * 0.15

        alive = []
        for imp in self.impulses:
            dt = t - imp.start
            if dt < 0:
                alive.append(imp)
                continue
            if dt > 4 * self.event_decay_s:
                continue
            alive.append(imp)
            e = imp.amp * math.exp(-dt / self.event_decay_s)
            if imp.action == "pop":
                p.pitch += 0.35 * e; p.antL += 0.9 * e; p.antR += 0.9 * e; p.bob += -10 * e
            elif imp.action == "recoil":
                p.pitch += 0.5 * e; p.antL += 1.0 * e; p.antR += 1.0 * e; p.bob += -8 * e
            elif imp.action == "cheer":
                w = math.sin(2 * math.pi * 4 * dt)
                p.antL += 0.5 * e * w; p.antR -= 0.5 * e * w; p.bob += -6 * e; p.pitch += 0.2 * e
            elif imp.action == "laugh":
                w = math.sin(2 * math.pi * 6 * dt)
                p.roll += 0.2 * e * w; p.bob += -4 * e * abs(w)
        self.impulses = alive
        return p
