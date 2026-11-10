"""The Create page's beat finder (static/music.mjs), run in node on synthetic songs with a known beat."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
MOD = ROOT / "reachy_dance" / "dashboard" / "static" / "music.mjs"
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")

# A drum-machine track: kick on bar 1 (and 3), hats on every beat, a quiet intro, then louder.
SYNTH = """
function song(bpm, seconds, startS, sr = 22050, quietPhrases = 2) {
  const x = new Float32Array(Math.floor(seconds * sr)), beat = 60 / bpm;
  let seed = 1; const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647 - 0.5;
  for (let k = 0; startS + k * beat < seconds; k++) {
    const t0 = startS + k * beat, i0 = Math.floor(t0 * sr), loud = k < quietPhrases * 8 ? 0.25 : 1;
    const kick = k % 4 === 0 || k % 4 === 2;
    for (let i = 0; i < sr * 0.12 && i0 + i < x.length; i++) {
      const t = i / sr;
      if (kick) x[i0 + i] += loud * 0.9 * Math.sin(2 * Math.PI * (55 + 90 * Math.exp(-t * 30)) * t) * Math.exp(-t * 18) * (k % 4 === 0 ? 1 : 0.6);
      x[i0 + i] += loud * 0.25 * rnd() * Math.exp(-t * 60);
    }
  }
  return { x, sr };
}
"""


def run(js: str):
    script = f"const M = await import({json.dumps(str(MOD))});\n{SYNTH}\n{js}"
    out = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


@pytest.mark.parametrize("bpm,start", [(128, 0.5), (100, 1.3), (95, 0.0), (140, 2.1)])
def test_finds_tempo_and_bar_one(bpm, start):
    r = run(f"""const s = song({bpm}, 40, {start}); const a = M.analyze(s.x, s.sr);
      console.log(JSON.stringify(a));""")
    assert abs(r["bpm"] - bpm) < 0.4, r["bpm"]
    beat = 60 / bpm
    # bar 1 on a phrase line of the true grid: a whole number of 8-count phrases after the first kick
    k = (r["first_downbeat_s"] - start) / (8 * beat)
    assert abs(k - round(k)) * 8 * beat < 0.04, (r["first_downbeat_s"], start)
    assert len(r["phrase_energy"]) >= 2
    assert r["phrase_energy"][0] < r["phrase_energy"][-1]          # the quiet intro reads quieter


def test_fast_songs_count_in_half_time():
    r = run("""const s = song(170, 30, 0.3); const a = M.analyze(s.x, s.sr); console.log(JSON.stringify(a));""")
    assert abs(r["bpm"] - 170) < 0.6 or abs(r["bpm"] - 85) < 0.3, r["bpm"]
    assert 70 <= r["bpm"] / r["beats_per_count"] <= 145


def test_corrected_tempo_rebuilds_the_grid():
    r = run("""const s = song(120, 30, 0.25); const F = M.features(s.x, s.sr); const a = M.withTempo(F, 120);
      console.log(JSON.stringify(a));""")
    assert abs(r["bpm"] - 120) < 0.3 and abs((r["first_downbeat_s"] - 0.25) / 4 - round((r["first_downbeat_s"] - 0.25) / 4)) * 4 < 0.04


def test_follows_a_drifting_tempo():
    # A band that speeds up from 120 to 127 BPM over a minute: a fixed grid would end ~0.4 beat off.
    r = run("""
      const sr = 22050, secs = 60, x = new Float32Array(sr * secs), truth = [];
      let t = 0.5, k = 0; let seed = 3; const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647 - 0.5;
      while (t < secs - 0.2) {
        truth.push(t); const i0 = Math.floor(t * sr);
        for (let i = 0; i < sr * 0.1 && i0 + i < x.length; i++) { const u = i / sr;
          if (k % 2 === 0) x[i0 + i] += 0.9 * Math.sin(2 * Math.PI * (55 + 90 * Math.exp(-u * 30)) * u) * Math.exp(-u * 18);
          x[i0 + i] += 0.25 * rnd() * Math.exp(-u * 60); }
        const bpm = 120 + 7 * t / secs; t += 60 / bpm; k++;
      }
      const a = M.analyze(x, sr);
      const err = truth.filter(v => v > 2 && v < secs - 2).map(v => Math.min(...a.beats.map(b => Math.abs(b - v))));
      err.sort((p, q) => p - q);
      console.log(JSON.stringify({ median: err[err.length >> 1], p90: err[Math.floor(err.length * 0.9)], range: a.tempo_range }));""")
    assert r["median"] < 0.02 and r["p90"] < 0.04, r
    assert r["range"][1] - r["range"][0] > 3


def test_finds_the_song_parts():
    # verse (dark, quiet hats) / chorus (bright, loud) / verse / chorus: the letters should repeat
    r = run("""
      const sr = 22050, bpm = 120, beat = 0.5, ph = 16, x = new Float32Array(sr * ph * 4 + sr);
      let seed = 5; const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647 - 0.5;
      for (let k = 0; k * beat < ph * 4; k++) {
        const t0 = k * beat, part = Math.floor(t0 / ph) % 2, i0 = Math.floor(t0 * sr);
        for (let i = 0; i < sr * beat && i0 + i < x.length; i++) { const u = i / sr;
          if (k % 2 === 0) x[i0 + i] += 0.8 * Math.sin(2 * Math.PI * (55 + 90 * Math.exp(-u * 30)) * u) * Math.exp(-u * 18);
          x[i0 + i] += part ? 0.35 * Math.sin(2 * Math.PI * 1760 * u) * Math.exp(-u * 4) + 0.3 * rnd() * Math.exp(-u * 20) : 0.06 * Math.sin(2 * Math.PI * 220 * u); }
      }
      const F = M.features(x, sr), a = M.withTempo(F, 120, 0.0, null, 1);
      console.log(JSON.stringify(a.phrase_labels));""")
    assert len(r) >= 15                      # each part lasts 16 s = 4 phrases of 8 counts
    verse, chorus = r[0], r[4]
    assert verse != chorus and r[:15] == [verse] * 4 + [chorus] * 4 + [verse] * 4 + [chorus] * 3, r
