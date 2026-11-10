"""Learning a dance from a video (static/learn.mjs), with a synthetic 'video': Encendido's own dancer as landmarks."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from reachy_dance.choreography import library as L

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "reachy_dance" / "dashboard" / "static"
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")


def run(js: str):
    pre = "".join(f"const {n} = await import({json.dumps(str(STATIC / f))});\n" for n, f in
                  (("LV", "learn.mjs"), ("R", "rehearsal.mjs"), ("C", "encendido-stage.mjs"), ("CH", "choreo.mjs")))
    out = subprocess.run(["node", "--input-type=module", "-e", pre + js], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


# A 30 fps video of phrases 15-16 (electro arms, robot square) that starts 1.7 s into the song.
VIDEO = """
  const OFS = 54.3, fps = 30, frames = [];
  for (let t = 0; t < 10; t += 1 / fps) frames.push({ t, lm: R.landmarksFor(C.poseAt(t + OFS).H) });
  const counts = Array.from({ length: 19 * 8 + 1 }, (_, k) => k * 0.5);
  const poses = LV.framesToPoses(frames, 1280, 720, false);
  const tracks = LV.trackOnCounts(poses, OFS, counts);
"""


def test_learns_the_dancers_arms_on_the_counts():
    r = run(VIDEO + """
      const i = 14, tr = tracks[i], err = [];
      tr.forEach((h, s) => { const H = C.poseAt(28 * 2 + s / LV.STEPS * 0.5).H; err.push(Math.abs(h.aL - H.aL), Math.abs(h.aR - H.aR)); });
      err.sort((a, b) => a - b);
      console.log(JSON.stringify({ covered: tracks.map((t, k) => t ? k : -1).filter(k => k >= 0), median: err[err.length >> 1], p90: err[Math.floor(err.length * 0.9)] }));""")
    assert r["covered"] == [14, 15]                 # only phrases the video fully covers
    assert r["median"] < 0.05 and r["p90"] < 0.4     # radians; the 3-frame averaging softens the snaps a little


def test_robots_copy_the_arms_with_their_antennas():
    r = run(VIDEO + """
      const lp = LV.learnedPhrase(tracks[14]), aL = LV.HUMAN_KEYS.indexOf("aL"), antL = LV.ROBOT_KEYS.indexOf("antL");
      const xs = lp.H.map(h => h[aL]), ys = lp.A.map(a => a[antL]), zs = lp.B.map(b => b[antL]);
      const corr = (x, y) => { const mx = x.reduce((a, b) => a + b) / x.length, my = y.reduce((a, b) => a + b) / y.length;
        let s = 0, vx = 0, vy = 0; x.forEach((v, k) => { s += (v - mx) * (y[k] - my); vx += (v - mx) ** 2; vy += (y[k] - my) ** 2; }); return s / Math.sqrt(vx * vy); };
      console.log(JSON.stringify({ a: corr(xs, ys), b: corr(xs, zs), n: lp.A.length, range: [Math.min(...ys), Math.max(...ys)] }));""")
    assert r["a"] > 0.9 and r["b"] > 0.9 and r["n"] == 8 * 8 + 1
    assert 0.05 <= r["range"][0] and r["range"][1] <= 1.35


def test_finds_where_the_video_sits_in_the_song():
    r = run("""
      let seed = 7; const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
      const fps = 86, song = new Float32Array(fps * 120); for (let i = 0; i < song.length; i++) song[i] = rnd() < 0.08 ? rnd() : 0;
      const start = Math.round(37.4 * fps), video = new Float32Array(fps * 20);
      for (let i = 0; i < video.length; i++) video[i] = song[start + i] * 0.6 + (rnd() < 0.02 ? 0.3 * rnd() : 0);   // quieter, with room noise
      console.log(JSON.stringify(LV.findOffset(song, video, fps)));""")
    assert abs(r["offset_s"] - 37.4) < 0.02 and r["confidence"] > 0.5


def test_robots_play_learned_phrases_like_the_page_draws_them():
    data = run(VIDEO + """console.log(JSON.stringify({ 14: LV.learnedPhrase(tracks[14]), 15: LV.learnedPhrase(tracks[15]) }));""")
    ch = L.validate({"title": "x", "count_bpm": 120, "learned": {"steps": 8, "phrases": {"1": data["14"], "2": data["15"]}},
                     "phrases": [{"src": 12}, {"src": 12, "learned": True}, {"src": 12, "learned": True}, {"src": 13}]})
    g = L.GeneratedScore(ch)
    assert g.joints[1:] == ["inside", "cross", "inside", "inside", "inside", "cross", "inside"]   # video phrases flow into each other
    sheet = L.build_sheet(ch, {"phrases": [{"react": {}, "cues": []}] * 19})
    assert sheet["phrases"][1]["name"] == "From your video" and sheet["phrases"][1]["cues"] == []
    ts = [4.1, 5.0, 6.6, 7.9, 8.2, 9.7, 11.9, 12.2]
    tl = {"name": "x", "beat": g.BEAT, "phrase_s": g.PH, "duration": g.DURATION, "learned": ch["learned"],
          "phrases": [{"n": i + 1, "src": p["src"], "mirror": False, "learned": bool(p.get("learned")), "name": "", "dancer": "", "act": ""} for i, p in enumerate(ch["phrases"])]}
    js = run(f"""const S = CH.makeShow({json.dumps(tl)}); console.log(JSON.stringify({json.dumps(ts)}.map(t => {{ const p = S.poseAt(t); return [p.L, p.R, p.H.aL]; }})));""")
    keys = ["yaw", "pitch", "roll", "body", "turn", "antL", "antR", "bob"]
    for t, (jl, jr, _) in zip(ts, js):
        for side, jp in (("A", jl), ("B", jr)):
            py = g.robot_pose(side, t)
            for k in keys:
                assert jp[k] == pytest.approx(getattr(py, k), abs=1e-6), (t, side, k)


def test_learned_robot_moves_are_kept_safe():
    row = [5, 2, 2, 3, 1, 3, -1, 40]                 # way out of range
    tr = {"H": [[0] * 15] * 65, "A": [row] * 65, "B": [row] * 65}
    ch = L.validate({"title": "x", "count_bpm": 120, "learned": {"steps": 8, "phrases": {"0": tr}}, "phrases": [{"src": 12, "learned": True}, {"src": 18}]})
    a = ch["learned"]["phrases"]["0"]["A"][0]
    assert a == [1, 0.6, 0.4, 0.8, 0, 1.35, 0.05, 12]
    with pytest.raises(ValueError):
        L.validate({"title": "x", "count_bpm": 120, "phrases": [{"src": 12, "learned": True}, {"src": 18}]})
