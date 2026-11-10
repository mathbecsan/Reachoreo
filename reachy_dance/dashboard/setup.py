"""The setup wizard's back end: find the robots, pair them to left/right, fix movement directions, remember progress.

Everything is written to config/show.yaml (comments kept) and applied to the running processes, so nobody has to
edit the file by hand. Progress lives in config/setup.json.
"""
from __future__ import annotations

import glob
import json
import re
import subprocess
import time
from pathlib import Path

from ..config import ROOT
from .launcher import port_open

SETUP_FILE = ROOT / "config" / "setup.json"
STEPS = ("found", "paired", "directions", "timing", "cameras", "framing")


def usb_ports() -> list[str]:
    """Serial ports a Reachy Mini Lite shows up as (macOS: /dev/cu.usbmodem*, Linux: /dev/ttyACM*)."""
    return sorted(set(glob.glob("/dev/cu.usbmodem*") + glob.glob("/dev/ttyACM*")))


def running_daemons() -> list[dict]:
    """reachy-mini-daemon processes on this computer and the serial/port each one uses."""
    try:
        out = subprocess.run(["ps", "-axo", "pid=,args="], capture_output=True, text=True, timeout=3).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    found = []
    for line in out.splitlines():
        if "reachy-mini-daemon" not in line or "grep" in line:
            continue
        m_serial = re.search(r"(?:-p|--serialport)\s+(\S+)", line)
        m_port = re.search(r"--fastapi-port\s+(\d+)", line)
        found.append({"pid": int(line.split()[0]), "serial": m_serial.group(1) if m_serial else None,
                      "port": int(m_port.group(1)) if m_port else 8000})
    return found


def scan(cfg: dict) -> dict:
    daemons = running_daemons()
    by_serial = {d["serial"]: d for d in daemons if d["serial"]}
    robots = []
    for p in usb_ports():
        d = by_serial.get(p)
        side = next((s for s in "AB" if cfg["robots"][s].get("serial") == p), None)
        robots.append({"serial": p, "daemon_port": d["port"] if d else None, "assigned": side,
                       "daemon_up": bool(d) and port_open("localhost", d["port"])})
    return {"usb": robots, "daemons": daemons,
            "config": {s: {k: cfg["robots"][s].get(k) for k in ("host", "port", "serial", "latency_s")} for s in "AB"}}


def load_state() -> dict:
    try:
        return json.loads(SETUP_FILE.read_text())
    except (OSError, ValueError):
        return {}


def mark(step: str, ok: bool = True, **extra):
    st = load_state()
    st[step] = {"ok": ok, "at": time.strftime("%Y-%m-%d %H:%M"), **extra}
    SETUP_FILE.write_text(json.dumps(st, indent=1))
    return st


def write_key(path: Path, section: str, sub: str | None, key: str, value) -> None:
    """Sets section[.sub].key in a YAML file, keeping every comment and the layout. Adds the key if it is missing."""
    text = value if isinstance(value, str) else ("true" if value is True else "false" if value is False else repr(value))
    lines = Path(path).read_text().splitlines(keepends=True)
    i, n = 0, len(lines)
    while i < n and not re.match(rf"^{re.escape(section)}:\s*(#.*)?$", lines[i]):
        i += 1
    if i == n:
        raise KeyError(section)
    start, indent = i + 1, "  "
    if sub is not None:
        j = start
        while j < n and not re.match(rf"^  {re.escape(sub)}:\s*(#.*)?$", lines[j]):
            if re.match(r"^\S", lines[j]):
                raise KeyError(f"{section}.{sub}")
            j += 1
        start, indent = j + 1, "    "
    end = start
    while end < n:
        ln = lines[end]
        if re.match(r"^\S", ln) and not ln.startswith("#"):
            break                                          # next top-level section
        if sub is not None and re.match(r"^  [^ #]", ln):
            break                                          # next robot block
        end += 1
    for k in range(start, end):
        m = re.match(rf"^({indent}{re.escape(key)}:\s*)(\S+)(.*)$", lines[k].rstrip("\n"))
        if m:
            lines[k] = f"{m.group(1)}{text}{m.group(3)}\n"      # only the value changes; spacing and comment stay
            break
    else:
        lines.insert(start, f"{indent}{key}: {text}\n")
    Path(path).write_text("".join(lines))


def assign(cfg: dict, path: Path, serial_a: str, serial_b: str) -> dict:
    """Pairs two USB robots to A (camera's left) and B (camera's right); reuses a running daemon's port."""
    if serial_a == serial_b:
        raise ValueError("pick two different robots")
    by_serial = {d["serial"]: d["port"] for d in running_daemons() if d["serial"]}
    used = set(by_serial.values())
    free = [p for p in (8000, 8001, 8002, 8003) if p not in used]
    for side, serial in (("A", serial_a), ("B", serial_b)):
        port = by_serial.get(serial) or free.pop(0)
        cfg["robots"][side].update({"serial": serial, "port": port, "host": "localhost"})
        for key, val in (("serial", serial), ("port", port), ("host", "localhost")):
            write_key(path, "robots", side, key, val)
    return cfg["robots"]


def swap(cfg: dict, path: Path) -> dict:
    """The robots are on the wrong sides: swap everything that belongs to the physical robot (port, serial, timing)."""
    ra, rb = cfg["robots"]["A"], cfg["robots"]["B"]
    for key in ("host", "port", "serial", "latency_s"):
        if key in ra or key in rb:
            ra[key], rb[key] = rb.get(key), ra.get(key)
            for side, r in (("A", ra), ("B", rb)):
                if r.get(key) is not None:
                    write_key(path, "robots", side, key, r[key])
    return cfg["robots"]


FLIPS = {
    "turn": ["yaw_left_sign"],                            # head and body turned the wrong way
    "pitch": ["pitch_down_sign"],                         # looked down instead of up
    "antenna_side": ["ant_swap"],                         # the other antenna moved
    "antenna_dir": ["ant_right_out_sign", "ant_left_out_sign"],   # it went down/inward instead of up/out
}


def flip(cfg: dict, path: Path, what: str) -> dict:
    cal = cfg.setdefault("calibration", {})
    changed = {}
    for key in FLIPS[what]:
        if key == "ant_swap":
            cal[key] = not bool(cal.get(key, False))
        else:
            cal[key] = -int(cal.get(key, -1 if key == "ant_left_out_sign" else 1))
        write_key(path, "calibration", None, key, cal[key])
        changed[key] = cal[key]
    return changed


def readiness(cfg: dict, fresh, procs: list[dict]) -> dict:
    """What a user still has to do before dancing, in plain words."""
    st = load_state()
    up = {p["name"]: p["running"] for p in procs}
    checks = [
        ("robots", all(cfg["robots"][s].get("serial") or cfg["robots"][s].get("host") not in ("localhost", "127.0.0.1") for s in "AB"),
         "both robots are paired to left and right"),
        ("running", fresh("clock") and fresh("A") and fresh("B"), "the clock and both robots are running"),
        ("paired", bool(st.get("paired", {}).get("ok")), "you checked which robot is on which side"),
        ("directions", bool(st.get("directions", {}).get("ok")), "the robots turn the right way"),
        ("timing", bool(st.get("timing", {}).get("ok")), "both robots land on the beat"),
        ("cameras", bool(st.get("cameras", {}).get("ok")), "each head camera is matched to its robot"),
    ]
    return {"ready": all(ok for _, ok, _ in checks), "checks": [{"key": k, "ok": ok, "text": t} for k, ok, t in checks],
            "state": st, "procs": up}
