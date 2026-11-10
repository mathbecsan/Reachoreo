"""One-click start for the show's other processes, so nobody has to juggle five terminals.

The dashboard can start (and stop) what isn't already running: each robot's daemon (when its USB serial
port is in config/show.yaml), the conductor and both agents. Anything you started yourself in a terminal
is detected and left alone. Output goes to runs/logs/<name>.log.
"""
from __future__ import annotations

import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

from ..config import ROOT

LOGS = ROOT / "runs" / "logs"


def port_open(host: str, port: int, timeout: float = 0.15) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _daemon_exe() -> str | None:
    here = Path(sys.executable).parent / "reachy-mini-daemon"
    return str(here) if here.exists() else shutil.which("reachy-mini-daemon")


class Launcher:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.procs: dict[str, subprocess.Popen] = {}
        self.started_at: dict[str, float] = {}

    def plan(self) -> list[dict]:
        """Every process the show needs, in start order, with the command that starts it."""
        py = sys.executable
        out = []
        for side in ("A", "B"):
            r = self.cfg["robots"][side]
            serial = r.get("serial")
            host, port = r.get("host", "localhost"), int(r.get("port", 8000))
            exe = _daemon_exe()
            cmd = None
            if serial and exe and host in ("localhost", "127.0.0.1"):
                cmd = [exe, "-p", serial, "--fastapi-port", str(port), "--robot-name", f"reachy_port{port}", "--no-media", "--headless"]
            out.append({"name": f"daemon_{side}", "label": f"Reachy {1 if side == 'A' else 2} daemon", "cmd": cmd,
                        "probe": ("port", host, port),
                        "why_not": None if cmd else ("robot is on another computer" if host not in ("localhost", "127.0.0.1")
                                                     else "add robots.%s.serial to config/show.yaml" % side if not serial
                                                     else "reachy-mini-daemon is not installed")})
        out.append({"name": "conductor", "label": "Conductor (show clock)", "cmd": [py, "-m", "reachy_dance.conductor"], "probe": ("bus", "clock")})
        for side in ("A", "B"):
            out.append({"name": f"agent_{side}", "label": f"Reachy {1 if side == 'A' else 2} agent",
                        "cmd": [py, "-m", "reachy_dance.agent", "--side", side], "probe": ("bus", side)})
        return out

    def _mine(self, name: str) -> bool:
        p = self.procs.get(name)
        return p is not None and p.poll() is None

    def status(self, fresh) -> list[dict]:
        """fresh(key) says whether the bus has heard from 'clock', 'A' or 'B' recently."""
        rows = []
        for p in self.plan():
            kind = p["probe"]
            up = port_open(kind[1], kind[2]) if kind[0] == "port" else fresh(kind[1])
            mine = self._mine(p["name"])
            exited = p["name"] in self.procs and not mine
            rows.append({"name": p["name"], "label": p["label"], "running": up or mine, "ours": mine,
                         "can_start": p["cmd"] is not None, "why_not": p.get("why_not"),
                         "exit_code": self.procs[p["name"]].returncode if exited else None,
                         "log": f"runs/logs/{p['name']}.log" if p["name"] in self.procs else None})
        return rows

    def start(self, fresh, dry_run: bool = False) -> list[str]:
        LOGS.mkdir(parents=True, exist_ok=True)
        started = []
        for p in self.plan():
            kind = p["probe"]
            up = port_open(kind[1], kind[2]) if kind[0] == "port" else fresh(kind[1])
            if up or self._mine(p["name"]) or not p["cmd"]:
                continue
            cmd = list(p["cmd"]) + (["--dry-run"] if dry_run and p["name"].startswith("agent") else [])
            log = open(LOGS / f"{p['name']}.log", "w")
            # stdin stays open (a pipe nobody writes), so the conductor's command reader just waits for the dashboard.
            self.procs[p["name"]] = subprocess.Popen(cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.PIPE,
                                                     env={**os.environ, "PYTHONUNBUFFERED": "1"}, start_new_session=True)
            self.started_at[p["name"]] = time.time()
            started.append(p["label"])
            if p["name"].startswith("daemon"):
                for _ in range(40):              # give the daemon time to open its port before the agent connects
                    if port_open(kind[1], kind[2]):
                        break
                    time.sleep(0.25)
        return started

    def stop(self) -> list[str]:
        """Stops only what this dashboard started, agents first (they ease the robots to rest), daemons last."""
        order = ["agent_A", "agent_B", "conductor", "daemon_A", "daemon_B"]
        stopped = []
        for name in order:
            p = self.procs.get(name)
            if p and p.poll() is None:
                p.send_signal(signal.SIGINT)
                try:
                    p.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    p.terminate()
                stopped.append(name)
        return stopped

    def restart_agents(self, fresh, dry_run: bool = False) -> tuple[bool, str]:
        """Restart both robot agents so they reconnect (after the robots were swapped). Only works for agents this
        dashboard started; agents started in a terminal have to be restarted there."""
        mine = [n for n in ("agent_A", "agent_B") if self._mine(n)]
        if not mine and (fresh("A") or fresh("B")):
            return False, "the robot agents were started in a terminal: stop them there (Ctrl-C) and press Start everything"
        for name in mine:
            p = self.procs[name]
            p.send_signal(signal.SIGINT)
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.terminate()
        time.sleep(0.5)
        started = self.start(lambda k: False if k in ("A", "B") else fresh(k), dry_run)
        return True, "restarted " + (", ".join(started) or "nothing")

    def close(self):
        self.stop()
