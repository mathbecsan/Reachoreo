"""Pure functions from body landmarks to dancer features and events. No camera code here,
so this is easy to unit-test and to swap for another pose model."""
from __future__ import annotations

from dataclasses import dataclass, field

# MediaPipe Pose landmark indices
NOSE, L_SH, R_SH, L_EL, R_EL, L_WR, R_WR, L_HIP, R_HIP = 0, 11, 12, 13, 14, 15, 16, 23, 24


@dataclass
class FeatureTracker:
    stage_px_per_frame: float = 900.0
    center_offset_px: float = 0.0
    debounce_s: float = 0.6
    framing: str = "full"         # "full": whole body in frame; "upper": close-up from the chest up
    baseline_torso: float | None = None
    baseline_shoulders: float | None = None
    _prev: dict | None = None
    _energy: float = 0.0
    _face_since: float | None = None
    _last_event: dict = field(default_factory=dict)

    def calibrate(self, lm):
        """Call with the dancer standing on the front center mark, facing the camera."""
        self.baseline_torso = abs(_mid(lm, L_HIP, R_HIP)[1] - _mid(lm, L_SH, R_SH)[1])
        self.baseline_shoulders = abs(lm[L_SH][0] - lm[R_SH][0])

    def update(self, lm, t: float) -> tuple[dict, list[dict]]:
        """lm: list of (x, y) in normalized IMAGE coordinates (x right, y down), as the camera sees it.
        Returns (state, new_events). Stage x is positive toward the camera's right."""
        if self.framing == "upper":
            return self._update_upper(lm, t)
        hip = _mid(lm, L_HIP, R_HIP)
        sh = _mid(lm, L_SH, R_SH)
        torso = abs(hip[1] - sh[1])
        shoulders = abs(lm[L_SH][0] - lm[R_SH][0])
        if self.baseline_torso is None:
            self.calibrate(lm)

        x = (hip[0] - 0.5) * self.stage_px_per_frame + self.center_offset_px
        depth = max(0.0, min(1.0, (1 - torso / self.baseline_torso) / 0.3)) if self.baseline_torso else 0.0
        facing = min(1.0, shoulders / self.baseline_shoulders) if self.baseline_shoulders else 1.0

        pts = [lm[i] for i in (L_WR, R_WR, L_HIP, R_HIP, NOSE)]
        jump_v = 0.0
        if self._prev is not None:
            dt = max(1e-3, t - self._prev["t"])
            speed = sum(((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5 for a, b in zip(pts, self._prev["pts"])) / (len(pts) * dt)
            self._energy += (min(1.0, speed / 1.2) - self._energy) * min(1.0, dt * 4)
            jump_v = (hip[1] - self._prev["hip_y"]) / dt
        self._prev = {"t": t, "pts": pts, "hip_y": hip[1]}

        nose = lm[NOSE]
        arms_up = lm[L_WR][1] < nose[1] and lm[R_WR][1] < nose[1]
        near = lambda w: ((w[0] - nose[0]) ** 2 + (w[1] - nose[1]) ** 2) ** 0.5 < 0.1
        hands_face = near(lm[L_WR]) and near(lm[R_WR])

        events = []
        if arms_up:
            self._emit(events, "arms_up", t)
        if hands_face:
            if self._face_since is None:
                self._face_since = t
        else:
            if self._face_since is not None and t - self._face_since > 0.25:
                self._emit(events, "hands_open", t)
            self._face_since = None
        if hands_face:
            self._emit(events, "hands_face", t)
        if jump_v < -0.9:
            self._emit(events, "jump", t)
        left_sh_x = min(lm[L_SH][0], lm[R_SH][0])
        right_sh_x = max(lm[L_SH][0], lm[R_SH][0])
        for w in (lm[L_WR], lm[R_WR]):
            level = abs(w[1] - sh[1]) < 0.12
            if level and w[0] < left_sh_x - 0.12:
                self._emit(events, "arm_out", t, side="A")      # pointing toward the camera's left robot
            elif level and w[0] > right_sh_x + 0.12:
                self._emit(events, "arm_out", t, side="B")

        state = {"seen": True, "x": x, "depth": depth, "energy": self._energy, "facing": facing,
                 "arms_up": arms_up, "hands_face": hands_face}
        return state, events

    def _update_upper(self, lm, t: float) -> tuple[dict, list[dict]]:
        """Close-up framing: hips are out of frame and outstretched hands may be too, so everything is
        measured from the shoulders and scaled by shoulder width (the body's size in the image)."""
        sh = _mid(lm, L_SH, R_SH)
        shoulders = max(1e-3, abs(lm[L_SH][0] - lm[R_SH][0]))
        if self.baseline_shoulders is None:
            self.calibrate(lm)
        s = self.baseline_shoulders or shoulders

        x = (sh[0] - 0.5) * self.stage_px_per_frame + self.center_offset_px
        depth = max(0.0, min(1.0, (1 - shoulders / s) / 0.3))     # leaning away reads as moving upstage

        pts = [lm[i] for i in (L_WR, R_WR, L_EL, R_EL, NOSE)]
        jump_v = 0.0
        if self._prev is not None:
            dt = max(1e-3, t - self._prev["t"])
            speed = sum(((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5 for a, b in zip(pts, self._prev["pts"])) / (len(pts) * dt)
            self._energy += (min(1.0, speed / s / 10) - self._energy) * min(1.0, dt * 4)
            jump_v = (sh[1] - self._prev["hip_y"]) / dt / s
        self._prev = {"t": t, "pts": pts, "hip_y": sh[1]}

        nose = lm[NOSE]
        up = lambda w, e: w[1] < nose[1] or e[1] < sh[1] - 0.35 * s
        arms_up = up(lm[L_WR], lm[L_EL]) and up(lm[R_WR], lm[R_EL])
        near = lambda w: ((w[0] - nose[0]) ** 2 + (w[1] - nose[1]) ** 2) ** 0.5 < 0.45 * s
        hands_face = near(lm[L_WR]) and near(lm[R_WR])

        events = []
        if arms_up:
            self._emit(events, "arms_up", t)
        if hands_face:
            if self._face_since is None:
                self._face_since = t
        else:
            if self._face_since is not None and t - self._face_since > 0.25:
                self._emit(events, "hands_open", t)
            self._face_since = None
        if hands_face:
            self._emit(events, "hands_face", t)
        if jump_v < -7.0:
            self._emit(events, "jump", t)
        left_sh_x = min(lm[L_SH][0], lm[R_SH][0])
        right_sh_x = max(lm[L_SH][0], lm[R_SH][0])
        for w, e in ((lm[L_WR], lm[L_EL]), (lm[R_WR], lm[R_EL])):
            # an arm held out sideways: wrist (or, if the hand is out of frame, the elbow) level and outside
            level_w, level_e = abs(w[1] - sh[1]) < 0.8 * s, abs(e[1] - sh[1]) < 0.5 * s
            if (level_w and w[0] < left_sh_x - 0.5 * s) or (level_e and e[0] < left_sh_x - 0.45 * s):
                self._emit(events, "arm_out", t, side="A")      # toward the camera's left robot
            elif (level_w and w[0] > right_sh_x + 0.5 * s) or (level_e and e[0] > right_sh_x + 0.45 * s):
                self._emit(events, "arm_out", t, side="B")

        state = {"seen": True, "x": x, "depth": depth, "energy": self._energy, "facing": 1.0,
                 "arms_up": arms_up, "hands_face": hands_face}
        return state, events

    def _emit(self, events, kind, t, side=None):
        key = (kind, side)
        if t - self._last_event.get(key, -1e9) < self.debounce_s:
            return
        self._last_event[key] = t
        ev = {"type": kind, "t": t}
        if side:
            ev["side"] = side
        events.append(ev)


def _mid(lm, a, b):
    return ((lm[a][0] + lm[b][0]) / 2, (lm[a][1] + lm[b][1]) / 2)
