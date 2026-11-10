"""Talking to a Reachy Mini, or pretending to (dry run)."""
from __future__ import annotations

import math
import time
from contextlib import ExitStack

from .pose import SdkCommand


class ReachyIO:
    def __init__(self, host: str, port: int, wake: bool = True):
        from reachy_mini import ReachyMini  # imported here so dry runs need no SDK
        from reachy_mini.utils import create_head_pose
        self._create_head_pose = create_head_pose
        mode = "localhost_only" if host in ("localhost", "127.0.0.1") else "network"
        self._stack = ExitStack()
        self.mini = self._stack.enter_context(
            ReachyMini(host=host, port=port, connection_mode=mode, media_backend="no_media"))
        if wake:
            self.mini.wake_up()   # the robot starts asleep

    def _head(self, c: SdkCommand):
        return self._create_head_pose(z=c.head_z_mm, roll=c.head_roll_deg, pitch=c.head_pitch_deg,
                                      yaw=c.head_yaw_deg, mm=True, degrees=True)

    def goto(self, c: SdkCommand, duration: float):
        """Smooth, blocking move (used to get into position, and to rest)."""
        self.mini.goto_target(head=self._head(c), antennas=list(c.antennas_rad), duration=duration,
                              body_yaw=c.body_yaw_rad)

    def send(self, c: SdkCommand):
        """Non-blocking streamed target (used every control tick)."""
        self.mini.set_target(head=self._head(c), antennas=list(c.antennas_rad), body_yaw=c.body_yaw_rad)

    def sleep(self):
        self.mini.goto_sleep()

    def measured(self) -> list | None:
        """Where the robot actually is, from the daemon's latest report (cached, no round trip):
        [head_yaw_deg, head_pitch_deg, head_roll_deg, head_z_mm, body_yaw_deg, ant_right_rad, ant_left_rad]."""
        try:
            h = self.mini.get_current_head_pose()
            joints, ants = self.mini.get_current_joint_positions()
        except (AssertionError, Exception):
            return None
        return pose_matrix_to_list(h) + [math.degrees(joints[0]), float(ants[0]), float(ants[1])]

    def close(self):
        self._stack.close()


def pose_matrix_to_list(h) -> list:
    """Inverse of create_head_pose (extrinsic xyz): [yaw_deg, pitch_deg, roll_deg, z_mm]."""
    yaw = math.atan2(h[1][0], h[0][0])
    pitch = math.asin(max(-1.0, min(1.0, -h[2][0])))
    roll = math.atan2(h[2][1], h[2][2])
    return [math.degrees(yaw), math.degrees(pitch), math.degrees(roll), 1000.0 * float(h[2][3])]


class DryRunIO:
    """Prints a compact line twice a second instead of moving a robot."""

    def __init__(self, side: str):
        self.side = side
        self.last_print = 0.0
        self.count = 0

    def goto(self, c: SdkCommand, duration: float):
        print(f"[{self.side}] goto ({duration:.1f}s) {fmt(c)}")

    def send(self, c: SdkCommand):
        self.count += 1
        t = time.monotonic()
        if t - self.last_print > 0.5:
            self.last_print = t
            print(f"[{self.side}] {fmt(c)}")

    def sleep(self):
        print(f"[{self.side}] goto_sleep")

    def measured(self) -> list | None:
        return None

    def close(self):
        pass


def fmt(c: SdkCommand) -> str:
    return (f"yaw {c.head_yaw_deg:6.1f} pitch {c.head_pitch_deg:6.1f} roll {c.head_roll_deg:6.1f} "
            f"z {c.head_z_mm:5.1f} body {c.body_yaw_rad:5.2f} ant {c.antennas_rad[0]:5.2f},{c.antennas_rad[1]:5.2f}")
