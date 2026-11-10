"""The Python score must reproduce the animated preview, and stay inside the robot's limits."""
import json
import math
from pathlib import Path

import pytest

from reachy_dance.choreography import encendido as E
from reachy_dance.config import load_choreography
from reachy_dance.pose import Calibration, to_sdk

GOLDEN = json.loads((Path(__file__).parent / "golden" / "encendido_robots.json").read_text())


def test_matches_preview_motion():
    worst = 0.0
    for k, (ra, rb) in enumerate(zip(GOLDEN["A"], GOLDEN["B"])):
        poses = E.robot_poses(k * GOLDEN["step"])
        for side, row in (("A", ra), ("B", rb)):
            for key, expected in zip(GOLDEN["keys"], row):
                worst = max(worst, abs(getattr(poses[side], key) - expected))
    assert worst < 1e-4, f"score drifted from the preview by {worst}"


@pytest.mark.parametrize("side", ["A", "B"])
def test_commands_stay_within_sdk_limits(side):
    cal = Calibration()
    t = -2.0
    while t < E.DURATION + 1:
        c = to_sdk(E.robot_pose(side, t), cal)
        assert abs(c.head_pitch_deg) <= 40 and abs(c.head_roll_deg) <= 40
        assert abs(math.degrees(c.body_yaw_rad)) <= 160
        assert abs(c.head_yaw_deg - math.degrees(c.body_yaw_rad)) <= 65 + 1e-6
        assert all(math.isfinite(v) for v in (c.head_yaw_deg, c.head_z_mm, *c.antennas_rad))
        t += 0.02


def test_phrase_sheet_matches_score():
    score, sheet = load_choreography("encendido")
    assert [p["n"] for p in sheet["phrases"]] == list(range(1, score.N_PHRASES + 1))


def test_no_jumps_between_phrases():
    """Blending should keep every channel continuous across phrase boundaries."""
    for i in range(1, E.N_PHRASES):
        t = i * E.PH
        before, after = E.robot_poses(t - 1e-3), E.robot_poses(t + 1e-3)
        for side in "AB":
            for key in ("yaw", "pitch", "body", "turn"):
                assert abs(getattr(before[side], key) - getattr(after[side], key)) < 0.05, (i, side, key)
