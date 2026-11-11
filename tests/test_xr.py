"""The 3D rehearsal page (xr/): its robots move exactly like the real ones, and its build is wired up."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from reachy_dance.choreography import encendido as E
from reachy_dance.config import load_config
from reachy_dance.pose import Calibration, to_sdk

ROOT = Path(__file__).resolve().parent.parent
SDK_TS = ROOT / "xr" / "src" / "sdk.ts"
STAGE = ROOT / "reachy_dance" / "dashboard" / "static" / "encendido-stage.mjs"
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")


def test_typescript_sdk_conversion_matches_pose_py():
    """xr/src/sdk.ts toSdk() == pose.to_sdk() for the whole score, with the real robots' calibration."""
    cal_d = load_config()["calibration"]
    cal = Calibration.from_dict(cal_d)
    ts = [k * 0.25 for k in range(int(E.DURATION / 0.25))]
    js = f"""
      const S = await import({json.dumps(str(SDK_TS))}); const C = await import({json.dumps(str(STAGE))});
      const cal = {{ ...S.DEFAULT_CAL, ...{json.dumps(cal_d)} }};
      console.log(JSON.stringify({json.dumps(ts)}.map(t => {{ const p = C.poseAt(t); return [S.toSdk(p.L, cal), S.toSdk(p.R, cal)]; }})));"""
    out = subprocess.run(["node", "--experimental-strip-types", "--no-warnings", "--input-type=module", "-e", js],
                         capture_output=True, text=True, check=True)
    res = json.loads(out.stdout)
    keys = ["head_roll_deg", "head_pitch_deg", "head_yaw_deg", "head_z_mm", "body_yaw_rad"]
    for t, (ja, jb) in zip(ts, res):
        for side, j in (("A", ja), ("B", jb)):
            c = to_sdk(E.robot_pose(side, t), cal)
            for k in keys:
                assert j[k] == pytest.approx(getattr(c, k), abs=1e-4), (t, side, k)
            assert j["antennas_rad"] == pytest.approx(list(c.antennas_rad), abs=1e-4), (t, side)


def test_rig_model_is_inside_the_quest_budget():
    glb = ROOT / "xr" / "public" / "models" / "reachy_mini.glb"
    b = glb.read_bytes()
    n = int.from_bytes(b[12:16], "little")
    g = json.loads(b[20:20 + n])
    tris = sum(g["accessors"][p["indices"]]["count"] // 3 for m in g["meshes"] for p in m["primitives"])
    draws = sum(len(g["meshes"][nd["mesh"]]["primitives"]) for nd in g["nodes"] if "mesh" in nd)
    names = {nd.get("name") for nd in g["nodes"]}
    assert tris <= 60000 and draws <= 8                       # two robots stay well under 300k triangles / 100 draws
    assert {"Core", "Core.001", "Head.001", "Antenna.L.002", "Antenna.R.002"} <= names


def test_coach_mirror_matches_the_pages_mirror():
    """The coach's mirror (xr/src/coach.ts) is the same left-right swap the 2D pages use (static/choreo.mjs)."""
    coach = ROOT / "xr" / "src" / "coach.ts"
    choreo = ROOT / "reachy_dance" / "dashboard" / "static" / "choreo.mjs"
    js = f"""
      const K = await import({json.dumps(str(coach))}); const CH = await import({json.dumps(str(choreo))}); const C = await import({json.dumps(str(STAGE))});
      const bad = [];
      for (let t = 0; t < C.DUR; t += 0.37) {{
        const S = C.poseAt(t), a = K.mirrorHuman(S.H), b = CH.mirrorStage(S).H;
        for (const k of Object.keys(b)) if (Math.abs(a[k] - b[k]) > 1e-9) bad.push([t, k]);
      }}
      console.log(JSON.stringify(bad.slice(0, 5)));"""
    out = subprocess.run(["node", "--experimental-strip-types", "--no-warnings", "--input-type=module", "-e", js],
                         capture_output=True, text=True, check=True, cwd=ROOT / "xr")
    assert json.loads(out.stdout) == []


def test_gold_moves_are_real_counts():
    lane = (ROOT / "xr" / "src" / "lane.ts").read_text()
    import re
    golds = [(int(p), int(c)) for p, c in re.findall(r"phrase: (\d+), count: (\d+)", lane)]
    assert golds == [(8, 7), (9, 2), (12, 3), (15, 7), (19, 5)]              # the five from the brief
    assert all(1 <= p <= E.N_PHRASES and 1 <= c <= 8 for p, c in golds)


SCORE_SIM = """
const S = await import(%(score)s); const C = await import(%(stage)s); const R = await import(%(reh)s);
const PX = 2.5 / 880, W = 1280, Hh = 720, SW = 260, PXM = SW / 0.38;       // shoulders 260 px apart = 0.38 m
const gold = new Set([[8,7],[9,2],[12,3],[15,7],[19,5]].map(([p,c]) => (p-1)*8+c-1));
const moves = S.scoredMoves(t => C.poseAt(t).H, C.BEAT, C.N * 8, PX, k => gold.has(k));
let seed = 7; const rnd = () => (seed = (seed * 16807) %% 2147483647) / 2147483647;
const gauss = () => Math.sqrt(-2 * Math.log(rnd() + 1e-12)) * Math.cos(2 * Math.PI * rnd());
// a camera's view of a dancer in pose H: shoulders, elbows, wrists, hips, nose and ears, in image pixels
function landmarks(H, noisePx) {
  const L = Array.from({ length: 33 }, () => ({ x: 0.5, y: 1.3, visibility: 0.1 }));
  const cx = 640 + H.x * PX * PXM, sy = 380, ua = 150, fa = 140, put = (i, x, y) => { L[i] = { x: (x + noisePx * gauss()) / W, y: (y + noisePx * gauss()) / Hh, visibility: 0.99 }; };
  const lx = Math.sin(H.lean) * 230, ly = Math.cos(H.lean) * 230;                // hips 230 px below the shoulders, leaned
  for (const [sx, a, e, si, ei, wi] of [[-1, H.aL, H.eL, 12, 14, 16], [1, H.aR, H.eR, 11, 13, 15]]) {
    const s = [cx + sx * SW / 2, sy], el = [s[0] + sx * Math.sin(a) * ua, s[1] + Math.cos(a) * ua];
    put(si, ...s); put(ei, ...el); put(wi, el[0] + sx * Math.sin(a + e) * fa, el[1] + Math.cos(a + e) * fa);
  }
  put(23, cx - lx + 70, sy + ly); put(24, cx - lx - 70, sy + ly);
  put(0, cx + (H.look || 0) * 0.35 * SW, sy - 0.75 * SW); put(7, cx + 40, sy - 0.75 * SW); put(8, cx - 40, sy - 0.75 * SW);
  return L;
}
function run(poseOf, lag, gap = null) {   // gap: "stall" (no frames 20-30 s) or "away" (frames, nobody in them)
  const sc = new S.Scorer(moves, C.BEAT);
  R.calibrate(R.myPose(landmarks({ ...C.poseAt(0).H, aL: 0.1, aR: 0.1, x: 0, lean: 0, look: 0 }, 0), W, Hh));
  const centre = { x: 640, sw: SW };
  for (let t = 0; t < C.DUR + 1; t += 1 / 30) {
    const inGap = gap && t >= 20 && t < 30;
    if (inGap && gap === "away") sc.push(S.nobody(t));
    else if (!inGap) { const lm = landmarks(poseOf(t - lag), 3), me = R.myPose(lm, W, Hh); sc.push(S.featuresFromLandmarks(lm, W, Hh, t, me, centre)); }
    sc.judge(t);
  }
  const seen = sc.judged.filter(j => !j.skipped), ps = seen.filter(j => j.rating === "PERFECT" || j.rating === "SUPER").length;
  return { moves: seen.length, skipped: sc.judged.length - seen.length, ps: ps / seen.length, points: sc.fraction, stars: sc.stars };
}
const at = t => C.poseAt(Math.max(0, Math.min(C.DUR - 1e-3, t))).H;
const still = { ...C.poseAt(0).H, aL: 0.12, eL: 0.1, aR: 0.12, eR: 0.1, x: 0, lean: 0, look: 0, depth: 0 };
console.log(JSON.stringify({ copy: run(at, 0.12), still: run(() => still, 0), late: run(at, 0.6),
  stall: run(at, 0.12, "stall"), away: run(at, 0.12, "away") }));
"""


def test_scoring_rewards_copying_the_coach_and_not_standing_still():
    """Through the real tracker path (landmarks -> myPose -> features -> scorer), with 120 ms of camera lag."""
    js = SCORE_SIM % {"score": json.dumps(str(ROOT / "xr" / "src" / "score.ts")), "stage": json.dumps(str(STAGE)),
                      "reh": json.dumps(str(ROOT / "reachy_dance" / "dashboard" / "static" / "rehearsal.mjs"))}
    out = subprocess.run(["node", "--experimental-strip-types", "--no-warnings", "--input-type=module", "-e", js],
                         capture_output=True, text=True, check=True)
    r = json.loads(out.stdout)
    assert r["copy"]["moves"] >= 60
    assert r["copy"]["ps"] >= 0.9, r["copy"]           # the brief: a clean copy is >= 90 % PERFECT or SUPER
    assert r["still"]["points"] < 0.1, r["still"]       # standing still scores under 10 %
    assert r["late"]["points"] < r["copy"]["points"] - 0.2, r["late"]   # more than a beat late costs a lot
    # the page freezing for 10 s isn't your fault: those moves drop out instead of scoring X
    assert r["stall"]["skipped"] >= 8 and r["stall"]["points"] >= r["copy"]["points"] - 0.02, r["stall"]
    # but walking out of the camera's view is: the camera saw nobody, so those moves are X
    assert r["away"]["skipped"] == 0 and r["away"]["points"] < r["copy"]["points"] - 0.08, r["away"]


def test_headset_scoring_rewards_copying_and_not_standing_still():
    """VR/AR scoring (head + both hands, body-relative, arm-span scaled, mirrored) with a simulated Quest dancer."""
    out = subprocess.run(["node", "--experimental-strip-types", "--no-warnings", str(ROOT / "tests" / "xr_score_sim.mjs"), str(ROOT)],
                         capture_output=True, text=True, check=True)
    r = json.loads(out.stdout)
    assert r["copy"]["moves"] >= 60
    assert r["copy"]["ps"] >= 0.9, r["copy"]
    assert r["still"]["points"] < 0.1, r["still"]
    assert r["late"]["points"] < r["copy"]["points"] - 0.3, r["late"]
    assert r["wrongSide"]["points"] < 0.7, r["wrongSide"]       # copying the un-mirrored dance (wrong hands) is caught
    assert 0.6 < r["sloppy"]["points"] < r["copy"]["points"], r["sloppy"]


def test_https_certificate_covers_localhost(tmp_path):
    """--https makes a self-signed certificate once (for the Quest over Wi-Fi) and reuses it."""
    import shutil
    if not shutil.which("openssl"):
        import pytest
        pytest.skip("openssl not installed")
    from reachy_dance.dashboard.server import ensure_certificate
    cert, key = ensure_certificate(tmp_path)
    out = subprocess.run(["openssl", "x509", "-in", str(cert), "-noout", "-ext", "subjectAltName"], capture_output=True, text=True, check=True).stdout
    assert "DNS:localhost" in out and "127.0.0.1" in out
    before = cert.read_bytes()
    assert ensure_certificate(tmp_path)[0].read_bytes() == before      # not remade every start
