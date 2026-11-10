"""One robot's agent. Run one per Reachy:

    python -m reachy_dance.agent --side A
    python -m reachy_dance.agent --side B

Each agent follows the conductor's clock, evaluates the shared score for its own side,
layers on reactions to the dancer and to the other robot, and streams the result.
"""
from __future__ import annotations

import argparse
import csv
import math
import time

from . import clock as C
from .bus import Publisher, Subscriber
from .config import choreography_name, endpoint, load_choreography, load_config
from .pose import Calibration, RobotPose, SlewLimiter, mix, to_sdk
from .reactive import Reactor
from .robot_io import DryRunIO, ReachyIO
from .util import ease

REST = RobotPose(antL=0.15, antR=0.15)
SETUP_S = 2.4          # how long a setup test move lasts


def setup_pose(action: str, u: float) -> RobotPose:
    """The setup wizard's test moves (score units, so they go through the same calibration as the dance)."""
    k = ease(min(u, SETUP_S - u) / 0.35)                  # ease in, hold, ease out
    if action == "turn_right":                            # head and body toward the camera's right
        return RobotPose(yaw=0.7 * k, body=0.3 * k, antL=0.4, antR=0.4)
    if action == "look_up":
        return RobotPose(pitch=0.75 * k, antL=0.4, antR=0.4)
    if action == "left_antenna_up":                       # the antenna on the camera's left goes up and out
        return RobotPose(antL=0.15 + 1.15 * k, antR=0.15)
    if action == "nod":
        return RobotPose(pitch=0.45 * math.sin(2 * math.pi * 2.5 * u) * k, antL=0.5, antR=0.5)
    w = math.sin(2 * math.pi * 3 * u) * k                 # wiggle: antennas flap in turn, a little head roll
    return RobotPose(antL=0.7 + 0.6 * w, antR=0.7 - 0.6 * w, roll=0.15 * w, pitch=0.15)


def sdk_list(c) -> list:
    return [round(v, 3) for v in (c.head_yaw_deg, c.head_pitch_deg, c.head_roll_deg, c.head_z_mm,
                                  math.degrees(c.body_yaw_rad), c.antennas_rad[0], c.antennas_rad[1])]


def main(argv=None):
    ap = argparse.ArgumentParser(description="Drive one Reachy Mini in the show.")
    ap.add_argument("--side", required=True, choices=["A", "B"], help="A = camera's left, B = camera's right")
    ap.add_argument("--config", default=None)
    ap.add_argument("--dry-run", action="store_true", help="print commands instead of moving a robot")
    ap.add_argument("--log", default=None, help="CSV file of every commanded pose and reaction")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    score, sheet = load_choreography(cfg["choreography"])
    me, other = args.side, ("B" if args.side == "A" else "A")
    rcfg, ctl = cfg["robots"][me], cfg["control"]
    cal = Calibration.from_dict(cfg.get("calibration"))
    dt = 1.0 / ctl["rate_hz"]

    subs = [endpoint(cfg, "conductor"), endpoint(cfg, "perception"), endpoint(cfg, f"robot_{other}")]
    topics = ["clock", "dancer", f"robot.{other}"]
    if "dashboard" in cfg["bus"]:          # the dashboard's "Tune timing" and setup wizard
        subs.append(endpoint(cfg, "dashboard")); topics += ["tune", "setup"]
    sub = Subscriber(subs, topics)
    pub = Publisher(endpoint(cfg, f"robot_{me}", bind=True))
    follower = C.ClockFollower()
    rx_cfg = cfg.get("reactive", {})
    def make_reactor():
        return Reactor(me, score, sheet, max_gaze_deg=rx_cfg.get("max_gaze_deg", 25), yaw_deg=cal.yaw_deg,
                       event_decay_s=rx_cfg.get("event_decay_s", 0.6), echo_delay_beats=rx_cfg.get("echo_delay_beats", 1),
                       lost_after_s=cfg.get("perception", {}).get("lost_after_s", 0.7))
    reactor = make_reactor()
    name = choreography_name(score)
    slew = SlewLimiter(dt)

    io = DryRunIO(me) if args.dry_run else ReachyIO(rcfg["host"], rcfg["port"], wake=rcfg.get("wake_on_start", True))
    opening = score.robot_pose(me, -1.0)
    io.goto(to_sdk(opening, cal), 2.0)
    slew.last = to_sdk(opening, cal)
    print(f"[{me}] ready in opening pose; waiting for the conductor")

    log = None
    if args.log:
        log = csv.writer(open(args.log, "w", newline=""))
        log.writerow(["mono", "show_t", "state", "yaw", "pitch", "roll", "body", "turn", "antL", "antR", "bob", "reactions"])

    last_pose, rest_from, rest_t0, slept = opening, None, None, False
    score_pose = opening
    last_status, published = 0.0, set()
    sent = slew.last
    prev_state = C.IDLE
    wanted = name
    setup_act, setup_t0 = None, 0.0
    try:
        while True:
            tick = time.monotonic()
            for topic, msg in sub.drain():
                if topic == "clock":
                    follower.on_message(msg)
                    wanted = msg.get("choreo") or wanted
                elif topic == "dancer":
                    reactor.on_dancer(msg, follower.show_time())
                elif topic == f"robot.{other}":
                    reactor.on_peer(msg, follower.show_time())
                elif topic == "tune":
                    if me in (msg.get("latency_s") or {}):
                        rcfg["latency_s"] = float(msg["latency_s"][me])
                        print(f"[{me}] timing tuned: sending moves {1000 * rcfg['latency_s']:.0f} ms early")
                    if msg.get("calibration"):
                        cal = Calibration.from_dict({**vars(cal), **msg["calibration"]})
                        print(f"[{me}] calibration updated: {msg['calibration']}")
                elif topic == "setup" and msg.get("side") in (me, "both"):
                    setup_act, setup_t0 = msg.get("action", "wiggle"), tick
                    print(f"[{me}] setup test move: {setup_act}")

            state, age = follower.state, follower.age()
            if wanted != name and state not in (C.COUNTDOWN, C.PLAYING, C.PAUSED):
                # The conductor switched choreography: learn the new one and move to its opening pose.
                try:
                    score, sheet = load_choreography(wanted)
                    reactor, name = make_reactor(), wanted
                    opening = score.robot_pose(me, -1.0)
                    print(f"[{me}] learned {name}: {score.N_PHRASES} phrases at {score.BPM:g} counts a minute")
                except Exception as e:      # keep dancing the old one rather than crash mid-show
                    print(f"[{me}] can't load {wanted}: {e}")
                    wanted = name
            if state in (C.COUNTDOWN, C.PLAYING) and prev_state not in (C.COUNTDOWN, C.PLAYING, C.PAUSED):
                reactor.reset()          # a new run: earlier runs' reactions are not duplicates of this one's
            prev_state = state
            t = follower.show_time(tick + rcfg.get("latency_s", 0.0))
            lost = state in (C.COUNTDOWN, C.PLAYING) and age > ctl["lost_conductor_hold_s"]

            if state in (C.COUNTDOWN, C.PLAYING) and not lost:
                dx, dd = reactor.score_inputs(t)
                pose = reactor.apply(score.robot_pose(me, t, dx, dd), t)
                score_pose = score.robot_pose(me, t)     # the pure score, for the dashboard
                rest_from = None
                slept = False
            elif state == C.ENDED or (lost and age > ctl["lost_conductor_rest_s"]):
                if rest_from is None:
                    rest_from, rest_t0 = last_pose, tick
                pose = score_pose = mix(rest_from, REST, ease((tick - rest_t0) / 1.5))
                if state == C.ENDED and rcfg.get("sleep_on_end") and not slept and tick - rest_t0 > 1.6:
                    io.sleep(); slept = True
            elif state == C.IDLE:
                pose = score_pose = opening
            else:  # paused, or briefly lost: hold still
                pose = last_pose
            if setup_act and state not in (C.COUNTDOWN, C.PLAYING):
                if tick - setup_t0 < SETUP_S:             # a setup wizard test move, layered on whatever it holds
                    sp = setup_pose(setup_act, tick - setup_t0)
                    pose = score_pose = sp
                    slept = False
                else:
                    setup_act = None

            last_pose = pose
            if not slept:
                sent = slew(to_sdk(pose, cal))
                io.send(sent)

            if tick - last_status > 0.04:
                last_status = tick
                recent = list(reactor.fired)
                pub.send(f"robot.{me}", {"side": me, "state": state, "choreo": name, "show_t": t, "clock_t": follower.show_time(tick), "clock_age": age,
                                         "phrase": score.phrase_at(max(t, 0)) + 1, "reactions": recent,
                                         "pose": [round(v, 4) for v in pose.as_list()],
                                         "score": [round(v, 4) for v in score_pose.as_list()],
                                         "lost": lost, "dancer_k": round(reactor.confidence(), 3),
                                         "dry_run": args.dry_run, "sent": time.time(),
                                         # SDK units: [head_yaw_deg, head_pitch_deg, head_roll_deg, head_z_mm, body_yaw_deg, ant_r, ant_l]
                                         "cmd": sdk_list(sent) if not slept else None, "meas": io.measured()})
                new = [r for r in recent if r["id"] not in published]
                for r in new:
                    published.add(r["id"])
                    print(f"[{me}] reaction {r['action']} ({r['source']}) at {r['show_t']:.2f}s")
            if log:
                log.writerow([f"{tick:.4f}", f"{t:.4f}", state] + [f"{v:.4f}" for v in pose.as_list()]
                             + [len(reactor.fired)])

            time.sleep(max(0.0, dt - (time.monotonic() - tick)))
    except KeyboardInterrupt:
        print(f"[{me}] stopping: easing to rest")
        try:
            io.goto(to_sdk(REST, cal), 1.5)
        except Exception as e:
            print(f"[{me}] rest move failed: {e}")
    finally:
        io.close(); sub.close(); pub.close()


if __name__ == "__main__":
    main()
