"""What the dashboard knows about the show, and the checks it runs on it. No sockets here (pure, unit-tested).

Feed every bus message to `Monitor.ingest(topic, msg, rx)`, then call `Monitor.snapshot(now)` to get the
current picture: clock, both robots, the dancer, active alerts. Everything worth keeping (commands, phrase
changes, reactions, cues, alerts raised and cleared) goes into `Monitor.log`, which can be exported.

Checks between the two robots:
  stale       a process stopped publishing
  state       a robot's clock state disagrees with the conductor's
  lost        a robot reports it lost the conductor's clock
  drift       a robot's show time is off the conductor's, or A and B are off each other
  phrase      A and B report different phrases (outside the instant of a phrase change)
  one_sided   a reaction fired on one side only, in a phrase that expects both to react
"""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field

from .sync import Run, Trace, aim_error_deg, estimate_beat_offset, estimate_lag

PLAYING_STATES = ("countdown", "playing")
POSE_KEYS = ["yaw", "pitch", "roll", "body", "turn", "antL", "antR", "bob"]


@dataclass
class Source:
    msg: dict | None = None
    rx: float | None = None          # local monotonic receive time

    def age(self, now: float) -> float:
        return float("inf") if self.rx is None else now - self.rx

    def fresh(self, now: float, stale_after: float) -> bool:
        return self.age(now) <= stale_after


@dataclass
class Monitor:
    score: object                    # choreography module
    sheet: dict                      # phrase sheet
    drift_warn_ms: float = 40.0
    stale_after_s: float = 1.0
    echo_delay_beats: float = 1.0
    reaction_window_s: float = 0.8   # grace after the expected echo before calling a reaction one-sided
    clock: Source = field(default_factory=Source)
    robots: dict = field(default_factory=lambda: {"A": Source(), "B": Source()})
    dancer: Source = field(default_factory=Source)
    reactions: dict = field(default_factory=lambda: {"A": {}, "B": {}})     # id -> reaction, per side
    cues: deque = field(default_factory=lambda: deque(maxlen=30))
    log: list = field(default_factory=list)
    alerts: dict = field(default_factory=dict)                          # key -> alert
    _checked_reactions: set = field(default_factory=set)
    _cue_ids: set = field(default_factory=set)
    _last_phrase: int | None = None
    _last_state: str | None = None
    _robot_state: dict = field(default_factory=dict)
    _mismatch_since: dict = field(default_factory=dict)
    yaw_deg: float = 40.0
    traces: dict = field(default_factory=lambda: {"A": Trace(), "B": Trace()})
    run: Run | None = None
    runs: list = field(default_factory=list)          # summaries of finished runs
    _lag_cache: dict = field(default_factory=dict)
    _lag_at: float = -1e9
    me: dict = field(default_factory=dict)            # the dancer's live pose match / timing, from the page

    # ---------- timing helpers ----------
    def show_time(self, now: float) -> float:
        """The conductor's show time right now, extrapolated from its last broadcast."""
        m = self.clock.msg
        if not m:
            return 0.0
        t = m["show_t"]
        if m["state"] in PLAYING_STATES:
            t += now - self.clock.rx
        return t

    def position(self, t: float) -> tuple[int, int]:
        """(phrase, count), both 1-based as on the page. Countdown gives phrase 0 and the beats left."""
        if t < 0:
            return 0, int(-self.score.count_of(t)) + 1
        i = self.score.phrase_at(t)
        c = int(self.score.count_of(t) - 8 * i)
        return i + 1, min(c, self.score.PHRASE_BEATS - 1) + 1

    def robot_time(self, side: str, now: float) -> float | None:
        """A robot's own clock, extrapolated to `now`, from its last status."""
        s = self.robots[side]
        if not s.msg:
            return None
        t = s.msg["clock_t"]
        if s.msg["state"] in PLAYING_STATES:
            t += now - s.rx
        return t

    def phrase_react(self, t: float) -> dict:
        return self.sheet["phrases"][self.score.phrase_at(max(t, 0.0))].get("react", {}) or {}

    # ---------- input ----------
    def ingest(self, topic: str, msg: dict, rx: float | None = None):
        rx = time.monotonic() if rx is None else rx
        if topic == "clock":
            self.clock = Source(msg, rx)
            prev = self._last_state
            if msg["state"] in PLAYING_STATES and prev not in PLAYING_STATES and prev != "paused":
                self._begin_run(msg, rx)
            elif msg["state"] in ("ended", "idle") and self.run and not self.run.finished:
                self._end_run(rx)
            if msg["state"] != self._last_state:
                if self._last_state is not None:
                    self._log(rx, "state", "conductor", f"show {msg['state']}")
                self._last_state = msg["state"]
            if msg["state"] in PLAYING_STATES and msg["show_t"] >= 0:
                p, _ = self.position(msg["show_t"])
                if p != self._last_phrase:
                    self._last_phrase = p
                    ph = self.sheet["phrases"][p - 1]
                    self._log(rx, "phrase", "conductor", f"phrase {p}: {ph['name']}", {"dancer": ph["dancer"]})
            elif msg["state"] not in PLAYING_STATES:
                self._last_phrase = None
        elif topic in ("robot.A", "robot.B"):
            side = topic[-1]
            self.robots[side] = Source(msg, rx)
            if msg.get("state") != self._robot_state.get(side):
                self._robot_state[side] = msg.get("state")
                self._log(rx, "state", side, f"robot {side} {msg.get('state')}")
            self.traces[side].add(rx, msg.get("cmd"), msg.get("meas"),
                                  msg.get("show_t") if msg.get("state") == "playing" else None, msg.get("clock_t"))
            if side == "B" and self.run and not self.run.finished:
                ra, rb = self.robots["A"], self.robots["B"]
                if ra.msg and ra.fresh(rx, self.stale_after_s) and ra.msg["state"] == "playing" and msg["state"] == "playing":
                    self.run.drift_samples.append(1000 * (self.robot_time("A", rx) - self.robot_time("B", rx)))
            for r in msg.get("reactions", []):
                if r["id"] not in self.reactions[side]:
                    r = {**r, "rx": rx}
                    self.reactions[side][r["id"]] = r
                    self._log(rx, "reaction", side, f"{side} {r['action']} ({r['source']})", r, show_t=r["show_t"])
        elif topic == "dancer":
            self.dancer = Source(msg, rx)
            for ev in msg.get("events", []):
                eid = ev.get("id") or f"{ev['type']}@{ev.get('show_t', 0):.2f}"
                if eid in self._cue_ids:
                    continue
                self._cue_ids.add(eid)
                cue = {**ev, "id": eid, "show_t": ev.get("show_t", msg.get("show_t", self.show_time(rx))), "rx": rx}
                self.cues.append(cue)
                if self.run and not self.run.finished:
                    self.run.cues.append(cue)
                to = f" toward {ev['side']}" if ev.get("side") else ""
                self._log(rx, "cue", "dancer", f"cue {ev['type']}{to}", cue, show_t=cue["show_t"])
        elif topic == "event":
            self._log(rx, "command", msg.get("source", "?"), msg.get("text", ""))

    # ---------- runs ----------
    def _begin_run(self, msg: dict, rx: float):
        if self.run and not self.run.finished:
            self._end_run(rx)
        self.run = Run(self.score, self.sheet, msg.get("start_t", 0.0), msg.get("end_t", self.score.DURATION), rx)
        for t in self.traces.values():
            t.clear()

    def _end_run(self, rx: float):
        run = self.run
        run.finished = True
        summ = run.summary(self.show_time(rx) + 10.0, self.reactions)
        p0, p1 = self.score.phrase_at(run.start_t) + 1, self.score.phrase_at(max(run.end_t - 1e-3, 0)) + 1
        summ.update({"phrases": [p0, p1], "wall": time.time()})
        self.runs.append(summ)
        txt = (f"run {p0}-{p1}: cues {summ['cues_hit']}/{summ['cues_total']} seen ({summ['on_beat']} on beat), "
               f"robots answered {summ['answers_given']}/{summ['answers_expected']}, A-B drift max {summ['ab_drift_max_ms']} ms")
        self._log(rx, "summary", "dashboard", txt, summ)

    def sync_state(self, now: float) -> dict:
        """Physical lag per robot (cached for 0.5 s; it is the expensive part), aim at the dancer, A-B offset."""
        if now - self._lag_at > 0.5:
            self._lag_at = now
            self._lag_cache = {s: {**estimate_lag(self.traces[s]), "beat_ms": estimate_beat_offset(self.traces[s])}
                               for s in ("A", "B")}
            if self.run and not self.run.finished and (self.clock.msg or {}).get("state") == "playing":
                for s, v in self._lag_cache.items():
                    if v["lag_ms"] is not None:
                        self.run.lags[s].append(v["lag_ms"])
                    if v["beat_ms"] is not None:
                        self.run.beats[s].append(v["beat_ms"])
        dm = self.dancer.msg or {}
        seen = self.dancer.fresh(now, self.stale_after_s) and dm.get("seen")
        react = self.phrase_react(self.show_time(now))
        out = {"gaze_phrase": bool(react.get("gaze") or react.get("track"))}
        for side in ("A", "B"):
            m = self.robots[side].msg or {}
            lag = self._lag_cache.get(side, {"lag_ms": None, "err_deg": None, "moving": False})
            out[side] = {**lag, "cmd": m.get("cmd"), "meas": m.get("meas"),
                         "aim_deg": aim_error_deg(self.score, side, m.get("cmd"), dm.get("x") if seen else None, self.yaw_deg)}
        ta, tb = self.robot_time("A", now), self.robot_time("B", now)
        both = all(self.robots[s].fresh(now, self.stale_after_s) for s in "AB")
        out["ab_offset_ms"] = round(1000 * (ta - tb), 1) if both and ta is not None and tb is not None else None
        me = self.me if self.me and now - self.me.get("rx", -1e9) < 1.0 else {}
        out["me"] = {k: me.get(k) for k in ("match", "offset_ms")}
        for side in ("A", "B"):
            b = out[side].get("beat_ms")
            out[side]["vs_me_ms"] = me["offset_ms"] - b if me.get("offset_ms") is not None and b is not None else None
        ba, bb = out["A"].get("beat_ms"), out["B"].get("beat_ms")
        out["beat_gap_ms"] = ba - bb if ba is not None and bb is not None else None
        la, lb = out["A"]["lag_ms"], out["B"]["lag_ms"]
        out["lag_gap_ms"] = abs(la - lb) if la is not None and lb is not None else None
        return out

    def run_state(self, now: float) -> dict | None:
        if not self.run:
            return None
        t = self.show_time(now) if not self.run.finished else self.run.end_t + 10.0
        return {"start_t": self.run.start_t, "end_t": self.run.end_t, "finished": self.run.finished,
                "rows": self.run.grade(t, self.reactions), "summary": self.run.summary(t, self.reactions)}

    def on_me(self, me: dict, rx: float):
        """The page's live comparison of the dancer against the choreography: {match: 0..1, offset_ms}."""
        self.me = {**me, "rx": rx}
        if self.run and not self.run.finished and (self.clock.msg or {}).get("state") == "playing":
            if me.get("match") is not None:
                self.run.me_match.append(float(me["match"]))
            if me.get("offset_ms") is not None and me.get("fresh"):
                self.run.me_offset.append(int(me["offset_ms"]))

    def note(self, text: str, source: str = "dashboard", now: float | None = None):
        self._log(time.monotonic() if now is None else now, "command", source, text)

    def _log(self, rx: float, kind: str, source: str, text: str, data: dict | None = None, show_t: float | None = None):
        t = self.show_time(rx) if show_t is None else show_t
        p, c = self.position(t)
        self.log.append({"wall": time.time(), "mono": round(rx, 4), "show_t": round(t, 3), "phrase": p, "count": c,
                         "kind": kind, "source": source, "text": text, "data": data or {}})

    # ---------- checks ----------
    def check(self, now: float) -> list[dict]:
        found: dict[str, dict] = {}

        def flag(key, level, text):
            found[key] = {"key": key, "level": level, "text": text}

        cm = self.clock.msg
        running = bool(cm) and cm["state"] in PLAYING_STATES
        ct = self.show_time(now)

        # Who is publishing
        if not self.clock.fresh(now, self.stale_after_s):
            flag("stale:conductor", "error" if self.clock.msg else "warn", "Conductor is not publishing a clock")
        for side in ("A", "B"):
            if not self.robots[side].fresh(now, self.stale_after_s):
                flag(f"stale:{side}", "error" if running else "warn", f"Robot {side} is not publishing")
        if running and not self.dancer.fresh(now, self.stale_after_s):
            flag("stale:dancer", "warn", "Perception is not publishing (the score carries the show)")

        fresh = {s: self.robots[s].fresh(now, self.stale_after_s) for s in ("A", "B")}

        for side in ("A", "B"):
            if not fresh[side]:
                self._mismatch_since.pop(side, None)
                continue
            m = self.robots[side].msg
            if m.get("lost"):
                flag(f"lost:{side}", "error", f"Robot {side} lost the conductor's clock")
            # State disagreement, tolerated briefly while a command propagates
            if cm and self.clock.fresh(now, self.stale_after_s) and m["state"] != cm["state"]:
                since = self._mismatch_since.setdefault(side, now)
                if now - since > 0.5:
                    flag(f"state:{side}", "warn", f"Robot {side} is {m['state']}, conductor is {cm['state']}")
            else:
                self._mismatch_since.pop(side, None)
            # Drift against the conductor
            if running and self.clock.fresh(now, self.stale_after_s) and m["state"] in PLAYING_STATES:
                d = 1000 * (self.robot_time(side, now) - ct)
                if abs(d) > self.drift_warn_ms:
                    flag(f"drift:{side}", "warn", f"Robot {side} clock is {d:+.0f} ms off the conductor")

        if fresh["A"] and fresh["B"]:
            a, b = self.robots["A"].msg, self.robots["B"].msg
            both_running = a["state"] in PLAYING_STATES and b["state"] in PLAYING_STATES
            if both_running:
                ta, tb = self.robot_time("A", now), self.robot_time("B", now)
                d = 1000 * (ta - tb)
                if abs(d) > self.drift_warn_ms:
                    flag("drift:AB", "error", f"A and B disagree on show time by {d:+.0f} ms")
                # Phrase mismatch, ignoring the instant of a phrase change
                pa, pb = a.get("phrase"), b.get("phrase")
                ca, cb = self.score.count_of(ta) / 8, self.score.count_of(tb) / 8
                near_edge = min(abs(ca - round(ca)), abs(cb - round(cb))) * self.score.PH < 0.15
                if pa != pb and not near_edge:
                    flag("phrase:AB", "error", f"A is in phrase {pa}, B is in phrase {pb}")

            # One-sided reactions
            if running:
                for side, other in (("A", "B"), ("B", "A")):
                    for rid, r in self.reactions[side].items():
                        if rid in self._checked_reactions or r["source"] == "echo":
                            continue
                        deadline = r["show_t"] + self.echo_delay_beats * self.score.BEAT + self.reaction_window_s
                        if ct < deadline:
                            continue
                        self._checked_reactions.add(rid)
                        if not self.expects_both(r):
                            continue
                        lo, hi = r["show_t"] - 0.3, r["show_t"] + self.echo_delay_beats * self.score.BEAT + 0.3
                        if not any(lo <= o["show_t"] <= hi for o in self.reactions[other].values()):
                            p, c = self.position(r["show_t"])
                            self._log(now, "check", "dashboard",
                                      f"one-sided: {side} did {r['action']} at phrase {p} count {c}, {other} did not answer",
                                      r, show_t=r["show_t"])
                            flag(f"one_sided:{rid}", "warn",
                                 f"{side} {r['action']} at {p}.{c} had no answer from {other}")

        # Keep one-sided alerts visible for a few seconds after they appear
        for key, al in self.alerts.items():
            if key.startswith("one_sided:") and key not in found and now - al["since"] < 6.0:
                found[key] = {k: al[k] for k in ("key", "level", "text")}

        # Raise / clear
        for key, al in found.items():
            if key not in self.alerts:
                al["since"] = now
                self.alerts[key] = al
                if not key.startswith("one_sided:"):
                    self._log(now, "alert", "dashboard", al["text"], {"level": al["level"], "key": key})
            else:
                self.alerts[key]["text"] = al["text"]
        for key in [k for k in self.alerts if k not in found]:
            al = self.alerts.pop(key)
            if not key.startswith("one_sided:"):
                self._log(now, "alert", "dashboard", f"cleared: {al['text']}", {"level": "ok", "key": key})
        return sorted(self.alerts.values(), key=lambda a: ({"error": 0, "warn": 1}.get(a["level"], 2), a["since"]))

    def expects_both(self, r: dict) -> bool:
        """Does the phrase where this reaction fired expect the other robot to react too?"""
        react = self.phrase_react(r["show_t"])
        if react.get("echo"):
            return True
        return any(tr.get("action") == r["action"] and tr.get("side", "any") == "any"
                   for tr in react.get("triggers", []))

    # ---------- output ----------
    def snapshot(self, now: float | None = None) -> dict:
        now = time.monotonic() if now is None else now
        alerts = self.check(now)
        cm = self.clock.msg or {"state": "offline", "show_t": 0.0}
        t = self.show_time(now)
        p, c = self.position(t)
        robots = {}
        for side in ("A", "B"):
            s = self.robots[side]
            m = s.msg or {}
            rt = self.robot_time(side, now)
            robots[side] = {
                "connected": s.fresh(now, self.stale_after_s),
                "age": None if s.rx is None else round(now - s.rx, 2),
                "state": m.get("state", "offline"),
                "phrase": m.get("phrase"),
                "drift_ms": None if rt is None or cm["state"] not in PLAYING_STATES else round(1000 * (rt - t), 1),
                "lost": m.get("lost", False),
                "dry_run": m.get("dry_run"),
                "dancer_k": m.get("dancer_k"),
                "pose": dict(zip(POSE_KEYS, m["pose"])) if m.get("pose") else None,
                "score": dict(zip(POSE_KEYS, m["score"])) if m.get("score") else None,
                "reactions": sorted(self.reactions[side].values(), key=lambda r: r["show_t"])[-6:],
                "choreo": m.get("choreo"),
            }
        dm = self.dancer.msg or {}
        return {
            "now": time.time(),
            "clock": {"state": cm["state"], "show_t": round(t, 3), "phrase": p, "count": c,
                      "connected": self.clock.fresh(now, self.stale_after_s), "choreo": cm.get("choreo")},
            "robots": robots,
            "dancer": {"connected": self.dancer.fresh(now, self.stale_after_s), "seen": bool(dm.get("seen")),
                       "x": dm.get("x"), "depth": dm.get("depth"), "energy": dm.get("energy"),
                       "cues": list(self.cues)[-8:]},
            "alerts": alerts,
            "sync": self.sync_state(now),
            "run": self.run_state(now),
            "last_run": self.runs[-1] if self.runs else None,
            "log_len": len(self.log),
        }
