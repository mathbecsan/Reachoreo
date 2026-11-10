"""Synchronization and timing scores for the Perform view. Pure functions and small classes, no sockets.

Three questions, each answered from bus messages alone:
  1. Do the physical robots keep up?   lag between what an agent commands and where the robot measures itself
  2. Are A and B together?             clock offset between the two, plus the difference in their physical lag
  3. Do they follow the dancer?        the dancer's cues against the counts in the phrase sheet, which robots
                                       answered each cue and how fast, and how far each head aims off the dancer
"""
from __future__ import annotations

import math
from bisect import bisect_left
from collections import deque
from dataclasses import dataclass, field

# Channels of the SDK lists the agents publish (see agent.sdk_list) used to judge physical tracking.
MOTION_CHANNELS = (0, 1, 2, 4)       # head yaw, head pitch, head roll, body yaw (all degrees)
LAGS_MS = range(0, 401, 10)


@dataclass
class Trace:
    """Recent (time, commanded, measured) samples for one robot, in SDK units."""
    window_s: float = 4.0
    samples: deque = field(default_factory=deque)

    shows: deque = field(default_factory=deque)      # (show time the cmd was meant for, cmd, robot clock time, meas)

    def add(self, t: float, cmd: list | None, meas: list | None, show_t: float | None = None, clock_t: float | None = None):
        if cmd is None or meas is None:
            return
        self.samples.append((t, cmd, meas))
        if show_t is not None and clock_t is not None:
            self.shows.append((show_t, cmd, clock_t, meas, t))
        while self.shows and t - self.shows[0][4] > self.window_s:
            self.shows.popleft()
        while self.samples and t - self.samples[0][0] > self.window_s:
            self.samples.popleft()

    def clear(self):
        self.samples.clear()
        self.shows.clear()


def _interp(ts: list, vs: list, t: float) -> float | None:
    i = bisect_left(ts, t)
    if i <= 0 or i >= len(ts):
        return None
    t0, t1 = ts[i - 1], ts[i]
    k = (t - t0) / (t1 - t0) if t1 > t0 else 0.0
    return vs[i - 1] + k * (vs[i] - vs[i - 1])


def estimate_lag(trace: Trace, min_motion_deg: float = 2.0) -> dict:
    """How long the robot takes to reach what it was told, and how far off it stays once aligned.

    Tries each lag L and compares measured(t) with commanded(t - L); the best L is the physical lag.
    Returns {lag_ms, err_deg, moving}. With too little motion, lag_ms is None (nothing to measure).
    """
    s = list(trace.samples)
    if len(s) < 20:
        return {"lag_ms": None, "err_deg": None, "moving": False}
    ts = [x[0] for x in s]
    span = 0.0
    for ch in MOTION_CHANNELS:
        vals = [x[1][ch] for x in s]
        span = max(span, max(vals) - min(vals))
    cmd = {ch: [x[1][ch] for x in s] for ch in MOTION_CHANNELS}
    best = None
    for lag_ms in LAGS_MS:
        L = lag_ms / 1000.0
        tot, n = 0.0, 0
        for t, _, m in s:
            for ch in MOTION_CHANNELS:
                c = _interp(ts, cmd[ch], t - L)
                if c is not None:
                    tot += abs(m[ch] - c)
                    n += 1
        if n and (best is None or tot / n < best[1]):
            best = (lag_ms, tot / n)
    if best is None:
        return {"lag_ms": None, "err_deg": None, "moving": False}
    moving = span >= min_motion_deg
    return {"lag_ms": best[0] if moving else None, "err_deg": round(best[1], 2), "moving": moving}


def estimate_beat_offset(trace: Trace, min_motion_deg: float = 2.0) -> int | None:
    """When the robot's head actually arrives, relative to the show clock: 0 = exactly on the count,
    positive = late. Compares where it measures itself at clock time c with the pose meant for show time c - L."""
    s = sorted(trace.shows, key=lambda x: x[0])
    if len(s) < 20:
        return None
    if max(max(x[1][ch] for x in s) - min(x[1][ch] for x in s) for ch in MOTION_CHANNELS) < min_motion_deg:
        return None
    ts = [x[0] for x in s]
    cmd = {ch: [x[1][ch] for x in s] for ch in MOTION_CHANNELS}
    best = None
    for L_ms in range(-150, 401, 10):
        L = L_ms / 1000.0
        tot, n = 0.0, 0
        for _, _, ct, m, _ in s:
            for ch in MOTION_CHANNELS:
                c = _interp(ts, cmd[ch], ct - L)
                if c is not None:
                    tot += abs(m[ch] - c)
                    n += 1
        if n and (best is None or tot / n < best[1]):
            best = (L_ms, tot / n)
    return best[0] if best else None


def aim_error_deg(score, side: str, cmd: list | None, dancer_x: float | None, yaw_deg: float = 40.0) -> float | None:
    """Degrees between where the robot's head points (world yaw) and the direction of the dancer."""
    if cmd is None or dancer_x is None:
        return None
    target = score.toward(score.POS[side], score.POS["C"] + dancer_x) * yaw_deg
    return round(cmd[0] - target, 1)


@dataclass
class Run:
    """One performance from Start to its end: expected cues, what the dancer did, how the robots answered."""
    score: object
    sheet: dict
    start_t: float
    end_t: float
    started_rx: float
    cues: list = field(default_factory=list)           # detected dancer cues during the run
    drift_samples: list = field(default_factory=list)  # A-B clock offsets (ms)
    lags: dict = field(default_factory=lambda: {"A": [], "B": []})
    beats: dict = field(default_factory=lambda: {"A": [], "B": []})   # robot arrival vs the beat (ms)
    me_match: list = field(default_factory=list)                     # dancer pose match 0..1 (from the page)
    me_offset: list = field(default_factory=list)                    # dancer timing vs the choreography (ms)
    finished: bool = False

    def expected(self) -> list[dict]:
        out = []
        for i, ph in enumerate(self.sheet["phrases"]):
            for c in ph.get("cues", []):
                t = self.score.time_of(8 * i + c["count"] - 1)
                if self.start_t - 1e-6 <= t < self.end_t:
                    out.append({"phrase": ph["n"], "count": c["count"], "type": c["type"], "side": c.get("side"), "t": t})
        return out

    def robots_expected(self, cue: dict) -> list[str]:
        """Which robots the phrase sheet says should answer this cue."""
        i = self.score.phrase_at(max(cue["t"], 0.0))
        react = self.sheet["phrases"][i].get("react", {}) or {}
        sides = set()
        count0 = self.score.count_of(cue["t"]) - 8 * i
        for tr in react.get("triggers", []):
            lo, hi = tr.get("counts", [0, 7])
            if tr["when"] == cue["type"] and lo - 1 <= count0 < hi + 2:
                if tr.get("side", "any") == "any":
                    sides |= {"A", "B"}
                elif cue.get("side"):
                    sides.add(cue["side"])
        if sides and react.get("echo"):
            sides |= {"A", "B"}
        return sorted(sides)

    def grade(self, now_t: float, reactions: dict) -> list[dict]:
        """One row per expected cue: the dancer's timing and each robot's answer. reactions[side][id] = reaction."""
        beat = self.score.BEAT
        rows, used = [], set()
        for e in self.expected():
            row = {**e, "status": "upcoming", "offset_ms": None, "robots": {}}
            if now_t < e["t"] - beat:
                rows.append(row)
                continue
            match = None
            for c in self.cues:
                if c["id"] in used or c["type"] != e["type"]:
                    continue
                if e["side"] and c.get("side") != e["side"]:
                    continue
                if abs(c["show_t"] - e["t"]) <= beat and (match is None or abs(c["show_t"] - e["t"]) < abs(match["show_t"] - e["t"])):
                    match = c
            if match:
                used.add(match["id"])
                off = 1000 * (match["show_t"] - e["t"])
                row["offset_ms"] = round(off)
                row["status"] = "on beat" if abs(off) <= 150 else ("early" if off < 0 else "late")
                for side in self.robots_expected({**e, "side": match.get("side", e["side"])}):
                    r = _answer(reactions.get(side, {}), side, match)
                    row["robots"][side] = None if r is None else round(1000 * (r["rx"] - match["rx"]))
            elif now_t > e["t"] + beat:
                row["status"] = "missed"
            else:
                row["status"] = "now"
            rows.append(row)
        return rows

    def summary(self, now_t: float, reactions: dict) -> dict:
        rows = self.grade(now_t, reactions)
        done = [r for r in rows if r["status"] not in ("upcoming", "now")]
        hit = [r for r in done if r["offset_ms"] is not None]
        answers = [v for r in hit for v in r["robots"].values()]
        drift = [abs(d) for d in self.drift_samples]
        med = lambda v: sorted(v)[len(v) // 2] if v else None
        lag = {s: med(v) for s, v in self.lags.items()}
        beat = {s: med(v) for s, v in self.beats.items()}
        me_off = med(self.me_offset)
        return {
            "cues_total": len(done), "cues_hit": len(hit),
            "on_beat": sum(1 for r in hit if r["status"] == "on beat"),
            "mean_offset_ms": round(sum(abs(r["offset_ms"]) for r in hit) / len(hit)) if hit else None,
            "answers_expected": len(answers), "answers_given": sum(1 for v in answers if v is not None),
            "mean_answer_ms": round(sum(v for v in answers if v is not None) / max(1, sum(1 for v in answers if v is not None)))
                              if any(v is not None for v in answers) else None,
            "ab_drift_mean_ms": round(sum(drift) / len(drift), 1) if drift else None,
            "ab_drift_max_ms": round(max(drift), 1) if drift else None,
            "lag_ms": lag,
            "lag_gap_ms": abs(lag["A"] - lag["B"]) if lag["A"] is not None and lag["B"] is not None else None,
            "beat_ms": beat,
            "me_match": round(sum(self.me_match) / len(self.me_match), 3) if self.me_match else None,
            "me_offset_ms": me_off,
            "robots_vs_me_ms": {s: (me_off - b if me_off is not None and b is not None else None) for s, b in beat.items()},
        }


def _answer(reactions: dict, side: str, cue: dict) -> dict | None:
    """The robot's reaction to this cue: its own (id '<side>-<cue id>') or an echo of the other robot's."""
    own = reactions.get(f"{side}-{cue['id']}")
    if own:
        return own
    other = "B" if side == "A" else "A"
    return reactions.get(f"{side}-echo-{other}-{cue['id']}")
