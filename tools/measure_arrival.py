"""How late each robot's head actually arrives, relative to the show clock (the beat).

    python tools/measure_arrival.py 6 9      # plays phrases 6-9 through the dashboard and measures both robots

Each agent sends a pose meant for show time `show_t` (already `latency_s` ahead) and reports where the robot
measures itself at its own clock time `clock_t`. Matching the two series gives the arrival delay behind the
beat: 0 ms means the move lands exactly on the count. If A and B differ, raise the later robot's latency_s
in config/show.yaml by the difference. Needs the dashboard, conductor and both agents running.
"""
from __future__ import annotations

import bisect
import json
import sys
import time
import urllib.request

import zmq

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))
from reachy_dance.config import endpoint, load_config  # noqa: E402

CH = (0, 1, 2, 4)     # head yaw, pitch, roll, body yaw (degrees)


def post(path, body):
    req = urllib.request.Request("http://localhost:8080" + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req))


def arrival_ms(samples):
    """samples: (show_t of cmd, cmd, clock_t, meas). Best L with meas(clock_t) ~= cmd at show time clock_t - L."""
    samples.sort(key=lambda s: s[0])
    ts = [s[0] for s in samples]
    best = None
    for L_ms in range(-100, 401, 5):
        L = L_ms / 1000
        err, n = 0.0, 0
        for _, _, ct, meas in samples:
            i = bisect.bisect_left(ts, ct - L)
            if 0 < i < len(ts):
                a, b = samples[i - 1], samples[i]
                k = (ct - L - a[0]) / (b[0] - a[0]) if b[0] > a[0] else 0
                for ch in CH:
                    err += abs(meas[ch] - (a[1][ch] + k * (b[1][ch] - a[1][ch])))
                    n += 1
        if n and (best is None or err / n < best[1]):
            best = (L_ms, err / n)
    return best


def main():
    first, last = (sys.argv[1], sys.argv[2]) if len(sys.argv) > 2 else ("6", "9")
    cfg = load_config()
    sock = zmq.Context.instance().socket(zmq.SUB)
    for side in "AB":
        sock.connect(endpoint(cfg, f"robot_{side}"))
        sock.setsockopt(zmq.SUBSCRIBE, f"robot.{side}".encode())
    time.sleep(0.5)
    print(post("/api/cmd", {"cmd": f"start {first} {last}"})["msg"])
    data = {"A": [], "B": []}
    seen_playing, deadline = False, time.time() + 120
    while time.time() < deadline:
        if not sock.poll(500):
            continue
        topic, raw = sock.recv_multipart()
        m = json.loads(raw)
        if m["state"] == "playing":
            seen_playing = True
            if m.get("cmd") and m.get("meas"):
                data[m["side"]].append((m["show_t"], m["cmd"], m["clock_t"], m["meas"]))
        elif seen_playing and m["state"] == "ended":
            break
    for side in "AB":
        L, err = arrival_ms(data[side])
        lat = cfg["robots"][side].get("latency_s", 0) * 1000
        print(f"Reachy {side}: lands {L:+d} ms after the beat (latency_s {lat:.0f} ms, so physical lag ~{L + lat:.0f} ms), "
              f"residual {err:.1f} deg, {len(data[side])} samples")


if __name__ == "__main__":
    main()
