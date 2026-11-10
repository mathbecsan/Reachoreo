"""The rehearsal page's pose math (static/rehearsal.mjs), run in node against the preview's own dancer."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from reachy_dance.pose import Calibration, RobotPose, to_sdk

ROOT = Path(__file__).resolve().parent.parent
MOD = ROOT / "reachy_dance" / "dashboard" / "static" / "rehearsal.mjs"
STAGE = ROOT / "reachy_dance" / "dashboard" / "static" / "encendido-stage.mjs"
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")


def run(js: str):
    script = f"const R = await import({json.dumps(str(MOD))}); const C = await import({json.dumps(str(STAGE))});\n{js}"
    out = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def test_performing_the_choreography_exactly_scores_near_100():
    res = run("""
      const out = [];
      for (const t of [21.2, 23.6, 29.1, 31.2, 32.6, 57.1, 58.6, 61.3, 62.5]) {
        const H = C.poseAt(t).H, me = R.myPose(R.landmarksFor(H), 1280, 720);
        out.push([t, R.matchAt(me, t), R.wrap(me.aL - H.aL), R.wrap(me.eR - H.eR)]);
      }
      console.log(JSON.stringify(out));""")
    for t, match, da, de in res:
        assert match > 0.95, (t, match)
        assert abs(da) < 1e-6 and abs(de) < 1e-6, (t, da, de)


def test_wrong_arms_score_low():
    res = run("""
      const t = 58.6, H = C.poseAt(t).H;          // electro arms: sweep toward B
      const wrong = { ...H, aL: H.aL + 2.2, aR: H.aR - 2.0, eL: -H.eL, eR: -H.eR };
      console.log(JSON.stringify(R.matchAt(R.myPose(R.landmarksFor(wrong), 1280, 720), t)));""")
    assert res < 0.5


def test_timing_offset_recovers_a_late_dancer():
    res = run("""
      const hist = [];
      for (let t = 56.0; t < 60.0; t += 1 / 30) hist.push({ t, me: R.myPose(R.landmarksFor(C.poseAt(t - 0.2).H), 1280, 720) });
      const late = R.estimateOffset(hist, 60.0);
      const hist2 = hist.map(h => ({ t: h.t, me: R.myPose(R.landmarksFor(C.poseAt(h.t + 0.1).H), 1280, 720) }));
      console.log(JSON.stringify([late, R.estimateOffset(hist2, 60.0)]));""")
    late, early = res
    assert abs(late - 200) <= 20 and abs(early + 100) <= 20


def test_no_timing_while_the_choreography_holds_still():
    res = run("""
      const hist = [];
      for (let t = 0.1; t < 4.0; t += 1 / 30) hist.push({ t, me: R.myPose(R.landmarksFor(C.poseAt(t).H), 1280, 720) });
      console.log(JSON.stringify(R.estimateOffset(hist, 4.0)));""")
    assert res is None


def test_measured_pose_conversion_inverts_to_sdk():
    cal = Calibration()
    p = RobotPose(yaw=0.4, pitch=-0.3, roll=0.15, body=0.5, turn=0.0, antL=0.9, antR=0.4, bob=-8)
    c = to_sdk(p, cal)
    import math
    m = [c.head_yaw_deg, c.head_pitch_deg, c.head_roll_deg, c.head_z_mm, math.degrees(c.body_yaw_rad), *c.antennas_rad]
    res = run(f"console.log(JSON.stringify(R.measuredToScore({json.dumps(m)}, {{}}, {{}})));")
    for k in ("yaw", "pitch", "roll", "body", "antL", "antR", "bob"):
        assert abs(res[k] - getattr(p, k)) < 1e-6, k
