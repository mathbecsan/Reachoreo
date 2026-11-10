"""A scripted stand-in for the dancer, so the whole system can be rehearsed without a camera.

    python -m reachy_dance.perception.fake_dancer            # perfect dancer
    python -m reachy_dance.perception.fake_dancer --sloppy   # late, early and missed cues
"""
from __future__ import annotations

import argparse
import random
import time

from .. import clock as C
from ..bus import Publisher, Subscriber
from ..config import endpoint, load_choreography, load_config



def scripted_events(sheet) -> list[tuple]:
    """(phrase number on the page, count on the page, event, side), from the phrase sheet's cues."""
    return [(ph["n"], c["count"], c["type"], c.get("side")) for ph in sheet["phrases"] for c in ph.get("cues", [])]
ENERGY_BY_ACT = {"I. Off": 0.05, "II. The reboot": 0.3, "III. The spark": 0.75, "IV. Switched on": 0.9}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Publish a scripted dancer.")
    ap.add_argument("--config", default=None)
    ap.add_argument("--sloppy", action="store_true", help="add timing jitter and miss some cues")
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args(argv)
    cfg = load_config(args.config)
    score, sheet = load_choreography(cfg["choreography"])
    rng = random.Random(args.seed)

    events = []
    for n, count, kind, side in scripted_events(sheet):
        if args.sloppy and rng.random() < 0.2:
            continue
        jitter = rng.uniform(-0.3, 0.4) if args.sloppy else 0.0
        events.append({"type": kind, "side": side, "show_t": score.time_of(8 * (n - 1) + count - 1 + jitter),
                       "id": f"fake{n}.{count}.{kind}"})
    pending = sorted(events, key=lambda e: e["show_t"])

    pub = Publisher(endpoint(cfg, "perception", bind=True))
    sub = Subscriber([endpoint(cfg, "conductor")], ["clock"])
    follower = C.ClockFollower()
    print(f"Fake dancer ready ({len(pending)} cues{', sloppy' if args.sloppy else ''}).")
    try:
        while True:
            for _, msg in sub.drain():
                follower.on_message(msg)
            t = follower.show_time()
            playing = follower.state in (C.COUNTDOWN, C.PLAYING)
            if playing and t >= 0:
                x, depth = score.scripted_dancer(t)
                if args.sloppy:
                    x += 25 * rng.uniform(-1, 1)
                act = sheet["phrases"][score.phrase_at(t)]["act"]
                pending = [e for e in pending if e["show_t"] > t - 0.5]   # skip cues before a mid-show start
                fire = [e for e in pending if e["show_t"] <= t]
                pending = [e for e in pending if e["show_t"] > t]
                for e in fire:
                    print(f"  cue {e['type']}{'->' + e['side'] if e['side'] else ''} at {e['show_t']:.2f}s")
                msg = {"seen": True, "x": x, "depth": depth, "energy": ENERGY_BY_ACT.get(act, 0.5),
                       "events": [{k: v for k, v in e.items() if v is not None} for e in fire], "show_t": t}
            else:
                msg = {"seen": False, "events": [], "show_t": t}
            pub.send("dancer", msg)
            time.sleep(1 / 30)
    except KeyboardInterrupt:
        pass
    finally:
        pub.close(); sub.close()


if __name__ == "__main__":
    main()
