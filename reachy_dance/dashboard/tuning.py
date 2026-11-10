"""Tunes each robot's timing from a run: how late its moves landed after the count becomes extra lead time.

Each agent sends a pose `latency_s` early so the motors arrive on the beat. A run measures where each robot
actually lands (Run.summary()["beat_ms"], + = late); adding that to latency_s puts it on the count, which also
puts the two robots together. The new values go to the running agents at once and into config/show.yaml.
"""
from __future__ import annotations

import re
from pathlib import Path

MAX_LATENCY_S = 0.40
MIN_CHANGE_MS = 15          # don't chase noise


def proposal(cfg: dict, beat_ms: dict) -> dict:
    out = {}
    for side in ("A", "B"):
        old = float(cfg["robots"][side].get("latency_s", 0.0))
        b = (beat_ms or {}).get(side)
        new = old if b is None or abs(b) < MIN_CHANGE_MS else min(MAX_LATENCY_S, max(0.0, old + b / 1000.0))
        out[side] = {"old_s": round(old, 3), "new_s": round(new, 3), "landed_ms": b, "change": b is not None and abs(b) >= MIN_CHANGE_MS}
    return out


def write_latency(path: Path, side: str, value: float):
    """Rewrites robots.<side>.latency_s in show.yaml, keeping every comment."""
    lines = Path(path).read_text().splitlines(keepends=True)
    in_robots = in_side = False
    for i, line in enumerate(lines):
        if re.match(r"^robots:\s*$", line):
            in_robots = True; continue
        if in_robots and re.match(r"^\S", line):
            break
        if in_robots and re.match(rf"^  {side}:\s*(#.*)?$", line):
            in_side = True; continue
        if in_side and re.match(r"^  \S", line):
            in_side = False
        if in_side and re.match(r"^\s+latency_s:", line):
            lines[i] = re.sub(r"(latency_s:\s*)[-0-9.]+", rf"\g<1>{value:.3f}", line, count=1)
            Path(path).write_text("".join(lines))
            return True
    return False
