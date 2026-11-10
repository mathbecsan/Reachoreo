"""Robot pose in "score units", plus conversion to Reachy Mini SDK commands with safety limits.

Score units come from the animated preview so the two always match:
  yaw, body   : -1..1, positive = toward the CAMERA'S RIGHT
  pitch       : -1..1, positive = head up
  roll        : radians, positive = head top toward the camera's right
  turn        : radians of extra whole-body rotation (the "spin")
  antL, antR  : radians outward from vertical; antL is the antenna on the camera's LEFT
  bob         : preview pixels, positive = head lower
"""
from __future__ import annotations

import math
from dataclasses import dataclass, fields, replace

from .util import lerp


@dataclass
class RobotPose:
    yaw: float = 0.0
    pitch: float = 0.0
    roll: float = 0.0
    body: float = 0.0
    turn: float = 0.0
    antL: float = 0.3
    antR: float = 0.3
    bob: float = 0.0

    def copy(self) -> "RobotPose":
        return replace(self)

    def as_list(self):
        return [getattr(self, f.name) for f in fields(self)]


POSE_KEYS = [f.name for f in fields(RobotPose)]


def mix(a: RobotPose, b: RobotPose, k: float) -> RobotPose:
    return RobotPose(**{n: lerp(getattr(a, n), getattr(b, n), k) for n in POSE_KEYS})


@dataclass
class Calibration:
    """Unit scales and sign flips. Verify each sign once in simulation (see README)."""
    yaw_deg: float = 40.0        # head yaw for yaw = 1
    body_deg: float = 30.0       # body yaw for body = 1
    pitch_deg: float = 25.0      # head pitch for pitch = 1
    z_mm_per_px: float = 0.5     # head height per preview pixel of bob
    yaw_left_sign: int = +1      # SDK +yaw turns toward the robot's own left (= camera's right)
    roll_sign: int = +1
    pitch_down_sign: int = +1    # SDK +pitch looks down
    ant_right_out_sign: int = +1
    ant_left_out_sign: int = -1
    ant_swap: bool = False             # true if the antenna on the camera's left is the robot's LEFT one (wired the other way)
    max_pitch_roll_deg: float = 35.0   # SDK limit is 40
    max_body_deg: float = 155.0        # SDK limit is 160
    max_head_body_delta_deg: float = 60.0  # SDK limit is 65
    max_antenna_rad: float = 1.45
    max_z_mm: float = 12.0

    @classmethod
    def from_dict(cls, d: dict | None) -> "Calibration":
        d = d or {}
        return cls(**{k: v for k, v in d.items() if k in {f.name for f in fields(cls)}})


@dataclass
class SdkCommand:
    """Values ready for create_head_pose / set_target (degrees, mm, radians)."""
    head_roll_deg: float
    head_pitch_deg: float
    head_yaw_deg: float       # world frame: includes body rotation
    head_z_mm: float
    body_yaw_rad: float
    antennas_rad: tuple       # (right, left) as the SDK expects


def _clip(x, lim):
    return max(-lim, min(lim, x))


def to_sdk(p: RobotPose, cal: Calibration) -> SdkCommand:
    body_deg = _clip(p.body * cal.body_deg + math.degrees(p.turn), cal.max_body_deg)
    rel_yaw = _clip(p.yaw * cal.yaw_deg, cal.max_head_body_delta_deg)
    # Camera's right is the robot's own left, so preview +yaw maps to SDK +yaw (robot left).
    head_yaw = cal.yaw_left_sign * (body_deg + rel_yaw)
    body_yaw = cal.yaw_left_sign * body_deg
    roll = cal.roll_sign * _clip(math.degrees(p.roll), cal.max_pitch_roll_deg)
    pitch = cal.pitch_down_sign * _clip(-p.pitch * cal.pitch_deg, cal.max_pitch_roll_deg)
    z = _clip(-p.bob * cal.z_mm_per_px, cal.max_z_mm)
    # antL is on the camera's left = the robot's RIGHT antenna.
    cam_l, cam_r = (p.antR, p.antL) if cal.ant_swap else (p.antL, p.antR)
    right = cal.ant_right_out_sign * max(-0.3, min(cal.max_antenna_rad, cam_l))
    left = cal.ant_left_out_sign * max(-0.3, min(cal.max_antenna_rad, cam_r))
    return SdkCommand(roll, pitch, head_yaw, z, math.radians(body_yaw), (right, left))


class SlewLimiter:
    """Caps how far each channel may move per control tick, to protect the motors."""

    def __init__(self, dt: float, deg_per_s=300.0, body_deg_per_s=250.0, ant_rad_per_s=12.0, mm_per_s=150.0):
        self.lim = {
            "head_roll_deg": deg_per_s * dt, "head_pitch_deg": deg_per_s * dt, "head_yaw_deg": deg_per_s * dt,
            "head_z_mm": mm_per_s * dt, "body_yaw_rad": math.radians(body_deg_per_s) * dt,
        }
        self.ant = ant_rad_per_s * dt
        self.last: SdkCommand | None = None

    def __call__(self, cmd: SdkCommand) -> SdkCommand:
        if self.last is None:
            self.last = cmd
            return cmd
        out = {}
        for k, lim in self.lim.items():
            prev, new = getattr(self.last, k), getattr(cmd, k)
            out[k] = prev + max(-lim, min(lim, new - prev))
        ants = tuple(pv + max(-self.ant, min(self.ant, nv - pv)) for pv, nv in zip(self.last.antennas_rad, cmd.antennas_rad))
        self.last = SdkCommand(antennas_rad=ants, **out)
        return self.last
