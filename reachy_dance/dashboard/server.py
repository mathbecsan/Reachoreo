"""The control dashboard: a local web page to run and debug the show.

    python -m reachy_dance.dashboard          # then open http://localhost:8080

It joins the bus like any other process: it listens to the clock, the dancer and both robots, and sends
text commands (start N, pause, resume, stop) to the conductor, which stays the only owner of the clock.
Standard library only, besides what the rest of the project already uses.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import shutil
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import mimetypes

import zmq

from ..bus import Publisher, Subscriber
from ..choreography import library
from ..config import ROOT, choreography_name, endpoint, load_choreography, load_config
from ..perception.features import FeatureTracker
from .launcher import Launcher
from .monitor import Monitor
from . import setup as setup_mod
from . import tuning

STATIC = Path(__file__).resolve().parent / "static"
MODELS = ROOT / "models"
ALLOWED = ("start", "pause", "resume", "stop", "load")
PAGES = {"/": "home.html", "/index.html": "home.html", "/control": "index.html", "/perform": "perform.html",
         "/perform.html": "perform.html", "/create": "create.html", "/setup": "setup.html"}
MAX_SONG_BYTES = 80_000_000
MAX_VIDEO_BYTES = 1_500_000_000
TYPES = {".mjs": "text/javascript", ".js": "text/javascript", ".wasm": "application/wasm", ".task": "application/octet-stream",
         ".html": "text/html; charset=utf-8", ".css": "text/css"}


class CameraBridge:
    """Turns pose landmarks from the browser's camera into dancer messages on the bus.

    The browser runs the pose model next to the live video; this side runs the same, unit-tested
    FeatureTracker as the standalone tracker, stamps events with the conductor's show time, and publishes
    on the perception port, so the agents cannot tell it from pose_tracker.py.
    """

    def __init__(self, cfg: dict, monitor: Monitor, lock: threading.Lock):
        pc = cfg.get("perception", {})
        self.cfg, self.monitor, self.lock = cfg, monitor, lock
        self.framing = pc.get("framing", "upper")
        self.tracker = FeatureTracker(pc.get("stage_px_per_frame", 900), pc.get("center_offset_px", 0), framing=self.framing)
        self.pub = None
        self.error = None
        self._tried = -1e9
        self.last_rx = None
        self.last_lm = None
        self.seen = False
        self.ids = 0

    def _publisher(self):
        """Bind the perception port on first use; if another tracker holds it, retry once a second."""
        if self.pub is None and time.monotonic() - self._tried > 1.0:
            self._tried = time.monotonic()
            try:
                self.pub = Publisher(endpoint(self.cfg, "perception", bind=True))
                self.error = None
            except zmq.ZMQError:
                self.error = ("Another perception process (fake_dancer or pose_tracker) is already publishing. "
                              "Stop it to use the camera here.")
        return self.pub

    def on_frame(self, lm: list | None) -> dict:
        now = time.monotonic()
        pub = self._publisher()
        if pub is None:
            return {"ok": False, "msg": self.error}
        self.last_rx = now
        with self.lock:
            show_t = self.monitor.show_time(now)
        if lm and len(lm) >= 33:
            pts = [(float(p[0]), float(p[1])) for p in lm[:33]]
            self.last_lm = pts
            state, events = self.tracker.update(pts, now)
            for ev in events:
                self.ids += 1
                ev["show_t"] = show_t
                ev["id"] = f"web{int(time.time())}-{self.ids}"
            state["events"] = events
            self.seen = True
        else:
            state, self.seen = {"seen": False, "events": []}, False
        state["show_t"] = show_t
        state["source"] = "dashboard-camera"
        pub.send("dancer", state)
        return {"ok": True, "state": {k: v for k, v in state.items() if k != "events"},
                "events": [e["type"] + (f">{e['side']}" if e.get("side") else "") for e in state["events"]]}

    def calibrate(self) -> dict:
        if not self.last_lm:
            return {"ok": False, "msg": "no pose seen yet: stand in front of the camera"}
        self.tracker.calibrate(self.last_lm)
        self.tracker.center_offset_px = -((self.last_lm[11][0] + self.last_lm[12][0]) / 2 - 0.5) * self.tracker.stage_px_per_frame \
            if self.framing == "upper" else self.tracker.center_offset_px
        return {"ok": True, "msg": "calibrated: where you stand now is the center mark"}

    def tick(self):
        """If the page stops sending (tab closed, camera off), tell the agents the dancer is gone."""
        if self.pub and self.last_rx and 0.5 < time.monotonic() - self.last_rx < 5.0:
            self.pub.send("dancer", {"seen": False, "events": [], "source": "dashboard-camera"})

    def close(self):
        if self.pub:
            self.pub.close()


def timeline(score, sheet, cal: dict | None = None) -> dict:
    """Everything the pages need to draw the phrases, their dancer cues and reaction windows."""
    phrases = []
    for i, ph in enumerate(sheet["phrases"]):
        react = ph.get("react", {}) or {}
        phrases.append({
            "n": ph["n"], "act": ph["act"], "name": ph["name"], "dancer": ph["dancer"],
            "start": score.time_of(8 * i), "end": score.time_of(8 * i + 8), "react": react, "cues": ph.get("cues", []),
            "robots": ph.get("robots", {}), "src": ph.get("src", i), "mirror": ph.get("mirror", False),
            "halves": ph.get("halves"),
            "learned": ph.get("learned", False),
            # trigger counts are 0-based in the sheet; the page shows 1-based
            "windows": [{"when": t["when"], "action": t["action"], "side": t.get("side", "any"),
                         "from": t["counts"][0] + 1, "to": t["counts"][1] + 1} for t in react.get("triggers", [])],
        })
    name = choreography_name(score)
    ch = getattr(score, "choreo", None)
    song = None
    if ch and library.song_file(name):
        song = {**ch.get("song", {}), "url": f"/library/{name}/song"}
    return {"name": name, "title": ch.get("title", name) if ch else "Encendido", "song": song,
            "beats_per_count": ch.get("beats_per_count", 1) if ch else 1,
            "bpm": score.BPM, "beat": score.BEAT, "phrase_s": score.PH, "beats": score.PHRASE_BEATS, "cal": cal or {},
            "duration": score.DURATION, "phrases": phrases, "pos": score.POS,
            # show time of every count, when the dance follows a song's real (drifting) beat
            "counts": [round(c, 4) for c in score.counts] if hasattr(score, "counts") and ch and ch.get("counts") else None,
            "learned": ch.get("learned") if ch else None, "video": video_info(name, ch)}


def video_info(name: str, ch: dict | None) -> dict | None:
    """The reference video a dance was learned from, if it was kept: where to fetch it and where it sits in the song."""
    f = library.video_file(name) if ch else None
    src = ((ch or {}).get("learned") or {}).get("video") or {}
    return {"url": f"/library/{name}/video", "offset_s": src.get("offset_s", 0.0), "mirrored": src.get("mirrored", False)} if f else None


class Dashboard:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.score, self.sheet = load_choreography(cfg["choreography"])
        self.choreo = choreography_name(self.score)
        dc = cfg.get("dashboard", {})
        self.monitor = Monitor(self.score, self.sheet, drift_warn_ms=dc.get("drift_warn_ms", 40),
                               stale_after_s=dc.get("stale_after_s", 1.0),
                               echo_delay_beats=cfg.get("reactive", {}).get("echo_delay_beats", 1),
                               yaw_deg=cfg.get("calibration", {}).get("yaw_deg", 40))
        self.lock = threading.Lock()
        self.sub = Subscriber([endpoint(cfg, "conductor"), endpoint(cfg, "perception"),
                               endpoint(cfg, "robot_A"), endpoint(cfg, "robot_B")],
                              ["clock", "event", "dancer", "robot.A", "robot.B"])
        self.pub = Publisher(endpoint(cfg, "dashboard", bind=True))
        self.timeline = timeline(self.score, self.sheet, cfg.get("calibration"))
        self.camera = CameraBridge(cfg, self.monitor, self.lock)
        self.launcher = Launcher(cfg)
        self.config_path = ROOT / "config" / "show.yaml"
        self.running = True

    def follow_choreo(self):
        """The conductor says which choreography is loaded; the dashboard (and its pages) follow it."""
        want = (self.monitor.clock.msg or {}).get("choreo")
        if not want or want == self.choreo:
            return
        try:
            score, sheet = load_choreography(want)
        except Exception as e:
            self.monitor.note(f"can't load {want}: {e}")
            self.choreo = want
            return
        self.score, self.sheet, self.choreo = score, sheet, want
        self.monitor.score, self.monitor.sheet = score, sheet
        self.timeline = timeline(score, sheet, self.cfg.get("calibration"))
        self.monitor.note(f"choreography: {want}")

    def setup_action(self, what: str, body: dict) -> tuple[dict, int]:
        """The setup wizard's actions. Returns (json, http status)."""
        path = self.config_path
        try:
            if what == "move":                       # a test move: wiggle, nod, turn_right, look_up, left_antenna_up
                side = body.get("side", "both")
                if side not in ("A", "B", "both"):
                    return {"ok": False, "msg": "side must be A, B or both"}, 400
                with self.lock:
                    st = (self.monitor.clock.msg or {}).get("state")
                if st in ("playing", "countdown"):
                    return {"ok": False, "msg": "stop the dance first"}, 400
                self.pub.send("setup", {"side": side, "action": str(body.get("action", "wiggle")), "sent": time.time()})
                up = [s for s in ("A", "B") if (side in (s, "both")) and self.fresh(s)]
                return {"ok": bool(up), "msg": "moving" if up else "that robot's agent isn't running: press Start everything"}, 200
            if what == "assign":
                setup_mod.assign(self.cfg, path, body["A"], body["B"])
                self.launcher.cfg = self.cfg
                started = self.launcher.start(self.fresh)
                setup_mod.mark("found")
                return {"ok": True, "msg": "paired; started " + (", ".join(started) or "nothing new"), "robots": self.cfg["robots"]}, 200
            if what == "swap":
                setup_mod.swap(self.cfg, path)
                ok, msg = self.launcher.restart_agents(self.fresh)
                return {"ok": ok, "msg": ("swapped Reachy 1 and Reachy 2. " + msg) if ok else msg, "robots": self.cfg["robots"]}, 200 if ok else 409
            if what == "flip":
                changed = setup_mod.flip(self.cfg, path, str(body.get("what")))
                self.pub.send("tune", {"calibration": changed, "sent": time.time()})
                with self.lock:
                    self.monitor.note(f"calibration changed: {changed}")
                return {"ok": True, "msg": "fixed: " + ", ".join(f"{k} = {v}" for k, v in changed.items()), "changed": changed}, 200
            if what == "mark":
                step = str(body.get("step"))
                if step not in setup_mod.STEPS:
                    return {"ok": False, "msg": "unknown step"}, 400
                return {"ok": True, "state": setup_mod.mark(step, bool(body.get("ok", True)), **(body.get("extra") or {}))}, 200
            if what == "reset":
                setup_mod.SETUP_FILE.unlink(missing_ok=True)
                return {"ok": True, "msg": "setup progress cleared"}, 200
        except (KeyError, ValueError, TypeError) as e:
            return {"ok": False, "msg": f"can't do that: {e}"}, 400
        return {"ok": False, "msg": "unknown setup action"}, 404

    def fresh(self, key: str) -> bool:
        now = time.monotonic()
        with self.lock:
            src = self.monitor.clock if key == "clock" else self.monitor.robots[key]
            return src.fresh(now, self.monitor.stale_after_s)

    def pump(self):
        last_tick = 0.0
        while self.running:
            if time.monotonic() - last_tick > 0.2:
                last_tick = time.monotonic()
                self.camera.tick()
            msgs = self.sub.drain()
            now = time.monotonic()
            with self.lock:
                for topic, m in msgs:
                    self.monitor.ingest(topic, m, now)
                self.follow_choreo()
            time.sleep(0.01)

    def snapshot(self) -> dict:
        with self.lock:
            snap = self.monitor.snapshot()
        snap["choreo"] = {"name": self.choreo, "title": self.timeline.get("title"), "phrases": self.score.N_PHRASES}
        return snap

    def system(self) -> dict:
        return {"procs": self.launcher.status(self.fresh)}

    def log_since(self, i: int) -> list:
        with self.lock:
            return self.monitor.log[i:]

    def command(self, text: str) -> tuple[bool, str]:
        parts = text.strip().split()
        if not parts or parts[0] not in ALLOWED:
            return False, f"unknown command: {text!r}"
        if parts[0] == "load":
            if len(parts) < 2 or not (parts[1] == "encendido" or library.exists(parts[1])):
                return False, "no such choreography"
            parts = parts[:2]
        if parts[0] == "start":
            nums = parts[1:3]
            if not all(p.isdigit() and 1 <= int(p) <= self.score.N_PHRASES for p in nums):
                return False, f"phrases must be 1 to {self.score.N_PHRASES}"
            if len(nums) == 2 and int(nums[0]) > int(nums[1]):
                return False, "the last phrase must not come before the first"
        clean = " ".join(parts[:3])
        self.pub.send("cmd", {"cmd": clean, "sent": time.time()})
        with self.lock:
            self.monitor.note(f"sent: {clean}")
            conductor_up = self.monitor.clock.fresh(time.monotonic(), self.monitor.stale_after_s)
        return True, "sent" if conductor_up else "sent, but the conductor is not running"

    def close(self):
        self.running = False
        self.launcher.close()
        self.sub.close(); self.pub.close(); self.camera.close()


def make_handler(app: Dashboard):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            if "Cache-Control" not in (extra or {}):
                self.send_header("Cache-Control", "no-store")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, code=200):
            self._send(code, json.dumps(obj).encode(), "application/json")

        def do_GET(self):
            path = self.path.split("?")[0]
            if path in PAGES:
                self._send(200, (STATIC / PAGES[path]).read_bytes(), "text/html; charset=utf-8")
            elif path == "/api/library":
                self._json({"items": library.listing(), "active": app.choreo})
            elif path.startswith("/api/library/"):
                slug = path.rsplit("/", 1)[1]
                if slug == "encendido":
                    sc, sh = load_choreography("encendido")
                    return self._json({"builtin": True, "timeline": timeline(sc, sh)})
                if not library.exists(slug):
                    return self._send(404, b"not found", "text/plain")
                self._json({"builtin": False, "choreo": library.load(slug)})
            elif path.startswith("/library/") and path.endswith("/video"):
                f = library.video_file(path.split("/")[2])
                if not f:
                    return self._send(404, b"no video", "text/plain")
                self.send_file(f)
            elif path.startswith("/library/") and path.endswith("/song"):
                f = library.song_file(path.split("/")[2])
                if not f:
                    return self._send(404, b"no song", "text/plain")
                self.send_file(f)
            elif path == "/api/moves":
                self._json({"moves": library.MOVES})
            elif path == "/api/system":
                self._json(app.system())
            elif path == "/api/setup/status":
                procs = app.system()["procs"]
                self._json({**setup_mod.readiness(app.cfg, app.fresh, procs), "scan": setup_mod.scan(app.cfg), "procs_list": procs,
                            "calibration": app.cfg.get("calibration", {}), "choreo": app.choreo, "phrases": app.score.N_PHRASES})
            elif path.startswith("/static/") or path.startswith("/models/"):
                base = STATIC if path.startswith("/static/") else MODELS
                f = (base / path.split("/", 2)[2]).resolve()
                if base.resolve() not in f.parents or not f.is_file():
                    return self._send(404, b"not found", "text/plain")
                ctype = TYPES.get(f.suffix) or mimetypes.guess_type(f.name)[0] or "application/octet-stream"
                cache = "max-age=3600" if "/vendor/" in path or path.startswith("/models/") else "no-cache"
                self._send(200, f.read_bytes(), ctype, {"Cache-Control": cache})
            elif path == "/api/timeline":
                self._json(app.timeline)
            elif path == "/api/state":
                self._json(app.snapshot())
            elif path == "/api/stream":
                self.stream()
            elif path == "/api/log.json":
                body = json.dumps(app.log_since(0), indent=1).encode()
                self._send(200, body, "application/json", {"Content-Disposition": f'attachment; filename="{stamp()}.json"'})
            elif path == "/api/log.csv":
                buf = io.StringIO()
                w = csv.writer(buf)
                w.writerow(["wall", "mono", "show_t", "phrase", "count", "kind", "source", "text", "data"])
                for e in app.log_since(0):
                    w.writerow([f"{e['wall']:.3f}", e["mono"], e["show_t"], e["phrase"], e["count"], e["kind"],
                                e["source"], e["text"], json.dumps(e["data"])])
                self._send(200, buf.getvalue().encode(), "text/csv", {"Content-Disposition": f'attachment; filename="{stamp()}.csv"'})
            else:
                self._send(404, b"not found", "text/plain")

        def send_file(self, f: Path):
            """Audio or video with byte ranges, so the browser can seek. Streamed from disk in chunks."""
            size = f.stat().st_size
            ctype = mimetypes.guess_type(f.name)[0] or ("video/mp4" if f.suffix.lower() in (".mp4", ".m4v", ".mov") else "application/octet-stream")
            start, end = 0, size - 1
            rng = self.headers.get("Range", "")
            if rng.startswith("bytes="):
                a, _, b = rng[6:].split(",")[0].partition("-")
                if a:
                    start, end = int(a), min(int(b) if b else size - 1, size - 1)
                else:
                    start = max(0, size - int(b))
                self.send_response(206)
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            else:
                self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(end - start + 1))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            try:
                with open(f, "rb") as fh:
                    fh.seek(start)
                    left = end - start + 1
                    while left > 0:
                        chunk = fh.read(min(1 << 20, left))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        left -= len(chunk)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_POST(self):
            if self.path.startswith("/api/songs"):
                return self.upload_song()
            if self.path.startswith("/api/videos"):
                return self.upload_video()
            try:
                n = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(n) or b"{}")
            except (ValueError, json.JSONDecodeError):
                return self._json({"ok": False, "msg": "bad request"}, 400)
            if self.path == "/api/cmd":
                ok, msg = app.command(str(body.get("cmd", "")))
                self._json({"ok": ok, "msg": msg}, 200 if ok else 400)
            elif self.path == "/api/landmarks":
                if isinstance(body.get("me"), dict):
                    with app.lock:
                        app.monitor.on_me(body["me"], time.monotonic())
                self._json(app.camera.on_frame(body.get("lm")))
            elif self.path == "/api/calibrate":
                self._json(app.camera.calibrate())
            elif self.path == "/api/generate":
                try:
                    ch = library.generate(body["analysis"], body.get("title", "My song"), body.get("seed"))
                except (KeyError, ValueError, TypeError) as e:
                    return self._json({"ok": False, "msg": str(e)}, 400)
                if body.get("slug"):
                    ch["slug"] = body["slug"]
                self._json({"ok": True, "choreo": ch, "texts": [library.phrase_texts_for(p) for p in ch["phrases"]]})
            elif self.path == "/api/assess":
                try:
                    ch = library.validate(body["choreo"])
                except (KeyError, ValueError, TypeError) as e:
                    return self._json({"ok": False, "msg": str(e)}, 400)
                self._json({"ok": True, "quality": library.assess(ch["phrases"], ch.get("accents")),
                            "texts": [library.phrase_texts_for(p) for p in ch["phrases"]]})
            elif self.path == "/api/library/save":
                try:
                    ch = library.save(body["choreo"])
                except (KeyError, ValueError, TypeError) as e:
                    return self._json({"ok": False, "msg": str(e)}, 400)
                self._json({"ok": True, "choreo": ch})
            elif self.path == "/api/library/delete":
                slug = library.slugify(str(body.get("slug", "")))
                if slug == app.choreo:
                    return self._json({"ok": False, "msg": "that one is loaded: switch to another first"}, 400)
                d = library.LIBRARY / slug
                if not library.exists(slug):
                    return self._json({"ok": False, "msg": "no such choreography"}, 404)
                shutil.rmtree(d)
                self._json({"ok": True})
            elif self.path == "/api/tune":
                with app.lock:
                    last = app.monitor.runs[-1] if app.monitor.runs else None
                if not last or not last.get("beat_ms") or all(v is None for v in last["beat_ms"].values()):
                    return self._json({"ok": False, "msg": "play a section first (with moving phrases) so the robots' timing can be measured"}, 400)
                prop = tuning.proposal(app.cfg, last["beat_ms"])
                if body.get("apply"):
                    for side, p in prop.items():
                        if p["change"]:
                            app.cfg["robots"][side]["latency_s"] = p["new_s"]
                            tuning.write_latency(app.config_path, side, p["new_s"])
                    app.pub.send("tune", {"latency_s": {s2: app.cfg["robots"][s2]["latency_s"] for s2 in "AB"}, "sent": time.time()})
                    with app.lock:
                        app.monitor.note("timing tuned: " + ", ".join(f"{s2} {p['old_s']:.2f}->{p['new_s']:.2f} s" for s2, p in prop.items() if p["change"]))
                self._json({"ok": True, "proposal": prop, "applied": bool(body.get("apply"))})
            elif self.path.startswith("/api/setup/"):
                self._json(*app.setup_action(self.path.rsplit("/", 1)[1], body))
            elif self.path == "/api/activate":
                ok, msg = app.command(f"load {library.slugify(str(body.get('slug', '')))}" if body.get("slug") != "encendido" else "load encendido")
                self._json({"ok": ok, "msg": msg}, 200 if ok else 400)
            elif self.path == "/api/system":
                if body.get("action") == "start":
                    started = app.launcher.start(app.fresh, dry_run=bool(body.get("dry_run")))
                    self._json({"ok": True, "msg": ("started " + ", ".join(started)) if started else "everything is already running", **app.system()})
                elif body.get("action") == "stop":
                    stopped = app.launcher.stop()
                    self._json({"ok": True, "msg": f"stopped {len(stopped)} process(es) this page started" if stopped
                                else "nothing to stop (only processes started from this page can be stopped here)", **app.system()})
                else:
                    self._json(app.system())
            else:
                self._send(404, b"not found", "text/plain")

        def upload_song(self):
            from urllib.parse import parse_qs, urlparse
            q = parse_qs(urlparse(self.path).query)
            n = int(self.headers.get("Content-Length", 0))
            if not 0 < n <= MAX_SONG_BYTES:
                return self._json({"ok": False, "msg": "the file must be under 80 MB"}, 400)
            data = self.rfile.read(n)
            if n < 4096:                          # an error page or an empty file, not a song: don't make a folder for it
                return self._json({"ok": False, "msg": "that file is too small to be a song"}, 400)
            title = (q.get("title") or ["My song"])[0]
            ext = (q.get("ext") or [".mp3"])[0]
            slug = (q.get("slug") or [None])[0] or library.unique_slug(title)
            try:
                f = library.save_song(slug, ext, data)
            except ValueError as e:
                return self._json({"ok": False, "msg": str(e)}, 400)
            self._json({"ok": True, "slug": library.slugify(slug), "file": f.name})

        def upload_video(self):
            """The reference video a dance was learned from, kept so the rehearsal page can show it next to you."""
            from urllib.parse import parse_qs, urlparse
            q = parse_qs(urlparse(self.path).query)
            n = int(self.headers.get("Content-Length", 0))
            if not 0 < n <= MAX_VIDEO_BYTES:
                return self._json({"ok": False, "msg": "the video must be under 1.5 GB"}, 400)
            slug = (q.get("slug") or [""])[0]
            if not slug:
                return self._json({"ok": False, "msg": "which dance is this video for?"}, 400)
            try:
                f = library.video_target(slug, (q.get("ext") or [".mp4"])[0])
            except ValueError as e:
                return self._json({"ok": False, "msg": str(e)}, 400)
            left = n
            with open(f, "wb") as out:
                while left > 0:
                    chunk = self.rfile.read(min(1 << 20, left))
                    if not chunk:
                        break
                    out.write(chunk)
                    left -= len(chunk)
            self._json({"ok": left == 0, "file": f.name, "mb": round(n / 1e6, 1)})

        def stream(self):
            """Server-sent events: a snapshot 20 times a second, plus new log entries."""
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            sent = 0
            try:
                while app.running:
                    snap = app.snapshot()
                    new = app.log_since(sent)
                    sent += len(new)
                    snap["log"] = new
                    self.wfile.write(f"data: {json.dumps(snap)}\n\n".encode())
                    self.wfile.flush()
                    time.sleep(0.05)
            except (BrokenPipeError, ConnectionResetError):
                pass

    return Handler


def stamp() -> str:
    return time.strftime("reachoreo-log-%Y%m%d-%H%M%S")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Serve the show control dashboard.")
    ap.add_argument("--config", default=None)
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--host", default="127.0.0.1", help="use 0.0.0.0 to open it from another device")
    args = ap.parse_args(argv)
    cfg = load_config(args.config)
    port = args.port or cfg.get("dashboard", {}).get("http_port", 8080)
    app = Dashboard(cfg)
    app.config_path = Path(args.config) if args.config else ROOT / "config" / "show.yaml"
    threading.Thread(target=app.pump, daemon=True).start()
    srv = ThreadingHTTPServer((args.host, port), make_handler(app))
    srv.daemon_threads = True
    print(f"Dashboard on http://localhost:{port}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        app.close(); srv.server_close()


if __name__ == "__main__":
    main()
