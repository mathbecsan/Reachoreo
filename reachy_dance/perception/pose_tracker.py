"""Live dancer tracking with a camera and MediaPipe Pose.

    python -m reachy_dance.perception.pose_tracker

Put the camera where the audience camera will be, so "left" means the same thing as in the
score. Press c with the dancer on the front center mark to calibrate, q to quit.
"""
from __future__ import annotations

import argparse
import itertools
import time

from .. import clock as C
from ..bus import Publisher, Subscriber
from ..config import endpoint, load_config
from .features import FeatureTracker


def main(argv=None):
    ap = argparse.ArgumentParser(description="Track the dancer and publish their state.")
    ap.add_argument("--config", default=None)
    args = ap.parse_args(argv)
    cfg = load_config(args.config)
    pc = cfg["perception"]

    import cv2
    import mediapipe as mp

    cap = cv2.VideoCapture(pc.get("camera", 0))
    if not cap.isOpened():
        raise SystemExit(f"Could not open camera {pc.get('camera', 0)}")
    pose = mp.solutions.pose.Pose(model_complexity=1, min_detection_confidence=0.5, min_tracking_confidence=0.5)
    drawer = mp.solutions.drawing_utils

    pub = Publisher(endpoint(cfg, "perception", bind=True))
    sub = Subscriber([endpoint(cfg, "conductor")], ["clock"])
    follower = C.ClockFollower()
    tracker = FeatureTracker(pc.get("stage_px_per_frame", 900), pc.get("center_offset_px", 0))
    ids = itertools.count()
    print("Tracking. Press c to calibrate on the center mark, q to quit.")
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                time.sleep(0.01)
                continue
            if pc.get("mirror_image"):
                frame = cv2.flip(frame, 1)
            for _, msg in sub.drain():
                follower.on_message(msg)
            t_local = time.monotonic()
            show_t = follower.show_time(t_local)
            res = pose.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            if res.pose_landmarks:
                lm = [(p.x, p.y) for p in res.pose_landmarks.landmark]
                state, events = tracker.update(lm, t_local)
                for ev in events:
                    ev["show_t"] = show_t
                    ev["id"] = f"cam{next(ids)}"
                state["events"] = events
                if events:
                    print("  event:", ", ".join(e["type"] + (f"->{e['side']}" if "side" in e else "") for e in events))
            else:
                state = {"seen": False, "events": []}
            state["show_t"] = show_t
            pub.send("dancer", state)

            if pc.get("show_window", True):
                if res.pose_landmarks:
                    drawer.draw_landmarks(frame, res.pose_landmarks, mp.solutions.pose.POSE_CONNECTIONS)
                label = f"x {state.get('x', 0):+.0f}  energy {state.get('energy', 0):.2f}" if state["seen"] else "dancer not seen"
                cv2.putText(frame, label, (16, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (80, 220, 255), 2)
                cv2.imshow("reachy-dance perception", frame)
                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    break
                if key == ord("c") and res.pose_landmarks:
                    tracker.calibrate(lm); print("  calibrated")
    finally:
        cap.release(); pub.close(); sub.close()
        if pc.get("show_window", True):
            cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
