"""The conductor: owns the show clock, plays the music, and prompts the dancer.

    python -m reachy_dance.conductor

Type commands and press Enter:
    start         start from the top (with a countdown)
    start 13      start from phrase 13
    start 6 9     play phrases 6 to 9 only (a short rehearsal or demo)
    load my-song  switch to a choreography from library/ (or back to: load encendido); the robots follow
    pause | resume | stop | quit
"""
from __future__ import annotations

import argparse
import queue
import shutil
import subprocess
import sys
import threading
import time

from . import clock as C
from .bus import Publisher, Subscriber
from .config import choreography_name, endpoint, load_choreography, load_config


class Music:
    def __init__(self, path, first_downbeat_s):
        self.path, self.offset, self.proc = path, first_downbeat_s, None

    def play_from(self, show_t: float):
        self.stop()
        if not self.path:
            return
        seek = max(0.0, self.offset + show_t)
        if shutil.which("ffplay"):
            self.proc = subprocess.Popen(["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", "-ss", f"{seek:.3f}", self.path])
        elif shutil.which("afplay") and seek < 0.05:
            self.proc = subprocess.Popen(["afplay", self.path])
        else:
            print("! install ffmpeg (ffplay) to play music from any point")

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
        self.proc = None


def read_commands(q: queue.Queue):
    for line in sys.stdin:
        q.put(line.strip())


def main(argv=None):
    ap = argparse.ArgumentParser(description="Run the show clock.")
    ap.add_argument("--config", default=None)
    ap.add_argument("--autostart", type=int, default=None, help="start immediately from this phrase")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    score, sheet = load_choreography(cfg["choreography"])
    name = choreography_name(score)
    cc = cfg["conductor"]
    pub = Publisher(endpoint(cfg, "conductor", bind=True))
    mon = Subscriber([endpoint(cfg, "perception"), endpoint(cfg, "robot_A"), endpoint(cfg, "robot_B")],
                     ["dancer", "robot.A", "robot.B"])
    clock, music = C.ShowClock(), Music(cc.get("music"), cc.get("first_downbeat_s", 0.0))
    music_at = None
    end_t, start_t = score.DURATION, 0.0
    q: queue.Queue = queue.Queue()
    threading.Thread(target=read_commands, args=(q,), daemon=True).start()
    # The dashboard sends the same text commands over the bus; this process stays the only clock.
    cmds = Subscriber([endpoint(cfg, "dashboard")], ["cmd"]) if "dashboard" in cfg["bus"] else None

    def say(text: str):
        print(text)
        pub.send("event", {"source": "conductor", "text": text.strip("> ").strip(), "sent": time.time()})

    def load(slug: str):
        nonlocal score, sheet, name, end_t, start_t, music
        try:
            score, sheet = load_choreography(slug)
        except (OSError, ValueError, KeyError, ModuleNotFoundError) as e:
            say(f"? can't load {slug}: {e}")
            return
        name = choreography_name(score)
        end_t, start_t = score.DURATION, 0.0
        # A song from the library plays in the browser (rehearsal page), in sync with this clock.
        music = Music(cc.get("music") if name == cfg["choreography"] else None, cc.get("first_downbeat_s", 0.0))
        say(f"> loaded {name}: {score.N_PHRASES} phrases at {score.BPM:g} counts a minute")

    def start(phrase: int, last: int | None = None):
        nonlocal music_at, end_t, start_t
        end_t = score.time_of(8 * (last or score.N_PHRASES))
        start_t = t0 = score.time_of(8 * (phrase - 1))
        pre = score.time_of(8 * (phrase - 1) - cc.get("countdown_beats", 8))     # on the song's own beats
        clock.start(pre)
        # From phrase 1 the countdown is silent; from a later phrase the pre-roll plays with music.
        music_at = max(pre, 0.0) - cc.get("audio_latency_s", 0.0)
        lead = "countdown" if phrase == 1 else "pre-roll of the previous material"
        upto = f" to {last}" if last and last < score.N_PHRASES else ""
        say(f"> starting at phrase {phrase}{upto} after a {cc.get('countdown_beats', 8)}-beat {lead}")

    if args.autostart:
        start(args.autostart)
    else:
        print("Conductor ready. Type 'start' (or 'start 13') and press Enter.")

    health = {"A": None, "B": None, "dancer": None}
    last_phrase, last_health = None, 0.0
    period = 1.0 / cc.get("clock_hz", 100)
    try:
        while True:
            tick = time.monotonic()
            if cmds:
                for _, m in cmds.drain():
                    q.put(str(m.get("cmd", "")))
            while not q.empty():
                cmd = q.get().split()
                if not cmd:
                    continue
                if cmd[0] == "start":
                    try:
                        n = int(cmd[1]) if len(cmd) > 1 else 1
                        last = int(cmd[2]) if len(cmd) > 2 else None
                    except ValueError:
                        n, last = 0, None
                    if 1 <= n <= score.N_PHRASES and (last is None or n <= last <= score.N_PHRASES):
                        start(n, last)
                    else:
                        say(f"? start takes a phrase from 1 to {score.N_PHRASES}, optionally a last phrase")
                elif cmd[0] == "load" and len(cmd) > 1:
                    if clock.state in (C.COUNTDOWN, C.PLAYING, C.PAUSED):
                        clock.stop(); music.stop(); music_at = None
                    load(cmd[1])
                elif cmd[0] == "pause" and clock.state in (C.COUNTDOWN, C.PLAYING):
                    clock.pause(); music.stop(); music_at = None; say("> paused")
                elif cmd[0] == "resume" and clock.state == C.PAUSED:
                    clock.resume(); music_at = clock.show_time(); say("> resumed")
                elif cmd[0] == "stop":
                    clock.stop(); music.stop(); music_at = None; say("> stopped")
                elif cmd[0] == "quit":
                    raise KeyboardInterrupt
                else:
                    print("? commands: start [phrase], load <choreography>, pause, resume, stop, quit")

            t = clock.show_time()
            if music_at is not None and clock.state in (C.COUNTDOWN, C.PLAYING) and t >= music_at:
                # The player takes audio_latency_s to start, so seek to where the show will be by then.
                music.play_from(t + cc.get("audio_latency_s", 0.0))
                music_at = None
            if clock.state == C.PLAYING and t >= end_t + (1.0 if end_t >= score.DURATION else 0.0):
                clock.stop(); music.stop(); say("> show complete")

            msg = clock.message(score.BPM)
            msg["phrase"] = score.phrase_at(max(t, 0.0)) + 1
            msg["end_t"], msg["start_t"] = end_t, start_t
            msg["choreo"], msg["phrases"] = name, score.N_PHRASES
            pub.send("clock", msg)

            for topic, m in mon.drain():
                key = "dancer" if topic == "dancer" else topic[-1]
                health[key] = (time.monotonic(), m)

            if clock.state in (C.COUNTDOWN, C.PLAYING):
                if t < 0:
                    beats_left = int(-score.count_of(t)) + 1
                    if last_phrase != -beats_left:
                        last_phrase = -beats_left
                        print(f"  countdown {beats_left}")
                else:
                    i = score.phrase_at(t)
                    if i != last_phrase:
                        last_phrase = i
                        ph = sheet["phrases"][i]
                        print(f"\n== {ph['act']}  phrase {ph['n']}: {ph['name']}\n   YOU: {ph['dancer']}")
            if tick - last_health > 2.0 and clock.state in (C.COUNTDOWN, C.PLAYING):
                last_health = tick
                parts = []
                for k in ("A", "B", "dancer"):
                    h = health[k]
                    if h is None or tick - h[0] > 1.0:
                        parts.append(f"{k}: --")
                    elif k == "dancer":
                        parts.append(f"dancer: {'seen' if h[1].get('seen') else 'not seen'}")
                    else:
                        conductor_then = t - (tick - h[0])   # conductor time when that status arrived
                        parts.append(f"{k}: drift {1000 * (h[1]['clock_t'] - conductor_then):+.0f} ms, phrase {h[1]['phrase']}")
                print("   [" + " | ".join(parts) + "]")
            time.sleep(max(0.0, period - (time.monotonic() - tick)))
    except KeyboardInterrupt:
        pass
    finally:
        clock.stop()
        for _ in range(20):
            m = clock.message(score.BPM); m["choreo"] = name
            pub.send("clock", m); time.sleep(0.01)
        music.stop(); pub.close(); mon.close()
        if cmds:
            cmds.close()


if __name__ == "__main__":
    main()
