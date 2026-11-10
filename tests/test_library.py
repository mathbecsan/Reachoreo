"""Dances made from songs: the generator, the score built from it, and the JS stage matching the robots' score."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from reachy_dance.choreography import encendido as E
from reachy_dance.choreography import library as L
from reachy_dance.config import load_choreography

ROOT = Path(__file__).resolve().parent.parent
ENERGY = [0.1, 0.15, 0.2, 0.45, 0.5, 0.9, 0.95, 0.6, 0.5, 0.9, 1.0, 0.85, 0.3, 0.2]


def gen(bpm=128, energy=ENERGY, seed=3):
    return L.generate({"bpm": bpm, "first_downbeat_s": 0.4, "duration_s": 120, "phrase_energy": energy}, "Test Song", seed)


def test_generated_dance_tells_a_story():
    ch = gen()
    src = [p["src"] for p in ch["phrases"]]
    assert len(src) == len(ENERGY)
    assert src[:3] == [0, 1, 2]                    # quiet opening: the robots wake up
    assert src[-1] == 18                           # ends on Full power
    assert all(a != b for a, b in zip(src, src[1:]))
    loud = [p["src"] for p, e in zip(ch["phrases"], ENERGY) if e >= 0.85]
    assert all(L.MOVES[s]["energy"] >= 0.5 for s in loud)
    assert gen(seed=3) == {**gen(seed=3)} and gen(seed=3)["phrases"] == gen(seed=3)["phrases"]


@pytest.mark.parametrize("bpm,bpc", [(170, 2), (128, 1), (60, 0.5)])
def test_counts_stay_in_a_safe_tempo(bpm, bpc):
    ch = gen(bpm=bpm)
    assert ch["beats_per_count"] == bpc and 70 <= ch["count_bpm"] <= 145


def test_encendido_as_a_generated_dance_is_identical():
    g = L.GeneratedScore({"title": "x", "count_bpm": 120, "phrases": [{"src": i} for i in range(19)]})
    for k in range(0, 760):
        t = k * 0.1
        for s in "AB":
            assert g.robot_pose(s, t).as_list() == E.robot_pose(s, t).as_list()


def test_mirrored_phrase_swaps_the_robots():
    g = L.GeneratedScore({"title": "x", "count_bpm": 120, "phrases": [{"src": 5, "mirror": True}, {"src": 5}]})
    for t in (0.6, 1.3, 2.2, 3.1):
        a, b = g.robot_pose("A", t), E.robot_pose("B", 5 * 4 + t)
        assert a.yaw == pytest.approx(-b.yaw) and a.antL == pytest.approx(b.antR) and a.pitch == pytest.approx(b.pitch)


def test_tempo_scales_the_moves():
    g = L.GeneratedScore({"title": "x", "count_bpm": 96, "phrases": [{"src": 12}, {"src": 13}]})
    assert g.PH == pytest.approx(5.0)
    assert g.robot_pose("A", 2.5).as_list() == pytest.approx(E.robot_pose("A", 12 * 4 + 2.0).as_list())


def test_sheet_borrows_cues_and_swaps_sides_when_mirrored():
    base = load_choreography("encendido")[1]
    sh = L.build_sheet(L.validate({"title": "x", "count_bpm": 120, "phrases": [{"src": 14, "mirror": True}, {"src": 5}]}), base)
    assert [c["side"] for c in sh["phrases"][0]["cues"]] == ["B", "A"]
    assert sh["phrases"][1]["cues"] == base["phrases"][5]["cues"]
    assert "Reachy 2" in sh["phrases"][0]["dancer"].split("sweep toward ")[1][:9]


def test_library_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(L, "LIBRARY", tmp_path)
    L.save_song("my-song", ".mp3", b"ID3fake")
    ch = L.save({**gen(), "slug": "my-song"})
    assert ch["song"]["file"] == "song.mp3" and L.exists("my-song")
    score, sheet = load_choreography("my-song")
    assert score.N_PHRASES == len(ENERGY) and len(sheet["phrases"]) == len(ENERGY)
    assert [i["slug"] for i in L.listing()] == ["encendido", "my-song"]
    with pytest.raises(ValueError):
        L.validate({"count_bpm": 120, "phrases": [{"src": 99}, {"src": 1}]})


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_pages_draw_the_same_dance_the_robots_play():
    ch = L.validate({"title": "x", "count_bpm": 100, "phrases": [{"src": 13}, {"src": 9, "mirror": True},
                                                                 {"src": 16, "halves": [{"src": 5, "half": 1}, {"src": 12, "half": 0, "mirror": True}]}]})
    g = L.GeneratedScore(ch)
    tl = {"name": "x", "beat": g.BEAT, "phrase_s": g.PH, "duration": g.DURATION,
          "phrases": [{"n": i + 1, "src": p["src"], "mirror": p["mirror"], "halves": p.get("halves"), "name": "", "dancer": "", "act": ""} for i, p in enumerate(ch["phrases"])]}
    ts = [0.5, 2.25, 2.35, 3.3, 4.7, 4.85, 5.0, 6.1, 7.7, 9.55, 9.65, 9.9, 11.2, 13.4]
    mod = ROOT / "reachy_dance" / "dashboard" / "static" / "choreo.mjs"
    js = f"""const M = await import({json.dumps(str(mod))}); const S = M.makeShow({json.dumps(tl)});
      console.log(JSON.stringify({json.dumps(ts)}.map(t => {{ const p = S.poseAt(t); return [p.L, p.R]; }})));"""
    out = json.loads(subprocess.run(["node", "--input-type=module", "-e", js], capture_output=True, text=True, check=True).stdout)
    keys = ["yaw", "pitch", "roll", "body", "turn", "antL", "antR", "bob"]
    for t, (jl, jr) in zip(ts, out):
        for side, jp in (("A", jl), ("B", jr)):
            py = g.robot_pose(side, t)
            for k in keys:
                assert jp[k] == pytest.approx(getattr(py, k), abs=1e-6), (t, side, k)


def test_dance_follows_the_songs_real_beats():
    # counts that speed up: count k at 0.5 s per count, shrinking 1% each phrase
    counts, t, step = [], 0.0, 0.5
    for k in range(8 * 4 + 1):
        counts.append(round(t, 4)); t += step
        if k % 8 == 7:
            step *= 0.99
    ch = L.validate({"title": "x", "count_bpm": 120, "counts": counts, "phrases": [{"src": 12}] * 4})
    g = L.GeneratedScore(ch)
    assert g.DURATION == pytest.approx(counts[-1])
    for k in (0, 3, 9.5, 17.25, 31):
        assert g.count_of(g.time_of(k)) == pytest.approx(k)
    assert g.phrase_at(counts[24] + 1e-3) == 3 and g.phrase_at(counts[24] - 1e-3) == 2
    # the move at count 2.5 of phrase 4 is Encendido's at its count 2.5, whatever the tempo
    assert g.robot_pose("A", g.time_of(24 + 2.5)).as_list() == pytest.approx(E.robot_pose("A", 12 * 4 + 1.25).as_list())


def test_song_parts_get_levels_and_repeat():
    labels = list("ABBCCBBCCD")
    energy = [0.5, 0.72, 0.74, 0.8, 0.82, 0.71, 0.73, 0.79, 0.81, 0.3]
    ch = L.generate({"bpm": 120, "phrase_energy": energy, "phrase_labels": labels}, "x", 1)
    ph = ch["phrases"]
    assert [p["level"] for p in ph[3:5]] == ["high", "high"] and ph[1]["level"] == "mid"   # chorus vs verse
    assert [p["src"] for p in ph[7:9]] == [p["src"] for p in ph[3:5]]                       # the chorus comes back the same
    assert ph[-1]["src"] == 18


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_move_profiles_are_up_to_date():
    out = subprocess.run(["node", str(ROOT / "tools" / "build_move_profiles.mjs"), "--check"], capture_output=True, text=True, check=True)
    assert out.stdout == "same", "run: node tools/build_move_profiles.mjs"


def test_rhythm_picks_pieces_whose_hits_match_the_music():
    # music hitting on counts 3 and 4 of each half (half-counts 4 and 6): Reboot's first half hits there
    target = L.profiles()[(5, 0)]["accents"]
    best = max(L.CANDIDATES, key=lambda g: L.rhythm_match(g, target) or -9)
    assert L.rhythm_match(best, target) > 0.95
    assert L.rhythm_match({"src": 12, "half": 0, "mirror": False}, target) < 0.5   # running man hits every count


def test_crossfades_leave_no_jump_at_a_join():
    ch = L.validate({"title": "x", "count_bpm": 110, "phrases": [{"src": 12, "halves": [{"src": 12, "half": 0}, {"src": 7, "half": 1, "mirror": True}]},
                                                                   {"src": 14}, {"src": 18}]})
    g = L.GeneratedScore(ch)
    assert g.joints[1:] == ["cross", "cross", "inside", "cross", "inside"]
    for j, kind in enumerate(g.joints):
        if kind == "cross":
            tb = g.time_of(4 * j)
            for s in "AB":
                a, b = g.robot_pose(s, tb - 1e-6).as_list(), g.robot_pose(s, tb + 1e-6).as_list()
                assert max(abs(x - y) for x, y in zip(a, b)) < 1e-3


def test_stitched_phrase_moves_its_cues_and_words():
    base = load_choreography("encendido")[1]
    p = {"src": 12, "halves": [{"src": 12, "half": 0}, {"src": 14, "half": 1, "mirror": True}]}   # 2nd half of electro arms, mirrored
    sh = L.build_sheet(L.validate({"title": "x", "count_bpm": 120, "phrases": [p, {"src": 18}]}), base)
    ph = sh["phrases"][0]
    assert [(c["count"], c["side"]) for c in ph["cues"]] == [(5, "B"), (6, "A")]       # still on 5 and 6, sides swapped
    assert "5–8: Sweep toward Reachy 2 on 5 and Reachy 1 on 6" in ph["dancer"]
    assert all(4 <= t["counts"][0] and t["counts"][1] <= 7 for t in ph["react"]["triggers"])


def test_generated_dance_scores_rhythm_and_flow():
    acc = [L.profiles()[(9, 0)]["accents"] * 2 for _ in range(6)]       # a song whose every half-phrase hits like the chicken peck
    ch = L.generate({"bpm": 120, "phrase_energy": [0.6] * 6, "phrase_accents": acc}, "x", 2)
    q = ch["quality"]
    assert q["rhythm"] >= 80 and 0 <= q["flow"] <= 100 and len(q["phrases"]) == 6
