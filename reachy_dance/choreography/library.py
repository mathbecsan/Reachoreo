"""Choreographies made from a song: the move library, the generator, and a score the robots can play.

A generated choreography is a list of 8-count phrases at the song's tempo. Each phrase reuses one of
Encendido's 19 phrases as a "move" (every one already written for both robots together and tested
against the preview), played at the song's count speed and optionally mirrored left-to-right.
So everything the agents, the reactor and the dashboard know about Encendido keeps working.

    library/<slug>/choreo.json     what generate() returns, possibly edited on the Create page
    library/<slug>/song.<ext>      the uploaded track (played by the browser, in sync with the show clock)
"""
from __future__ import annotations

import bisect
import json
import math
import random
import re
import time
from pathlib import Path

from ..pose import RobotPose, mix
from ..util import clamp, ease
from . import encendido as E

ROOT = Path(__file__).resolve().parent.parent.parent
LIBRARY = ROOT / "library"
MAX_PHRASES = 60
AUDIO_EXT = {".mp3", ".m4a", ".aac", ".wav", ".ogg", ".oga", ".flac", ".webm", ".opus"}

# One entry per Encendido phrase (index = its 0-based number). energy: how intense it reads, 0..1.
# Texts say "Reachy 1" (camera's left) and "Reachy 2" (camera's right); mirroring swaps them.
MOVES = [
    dict(name="Powered off", energy=0.0, kind="intro",
         you="Stand frozen like a switched-off robot: knees soft, arms dead, head hanging.",
         A="Asleep: head down, antennas drooped, breathing slowly.", B="Asleep."),
    dict(name="A flicker", energy=0.1, kind="intro",
         you="Stay frozen. One glitch on 6: your head twitches sideways and drops again.",
         A="Wakes on 3 to 5, scans the room with a big body turn, finds you on 7.", B="Still asleep, dreaming: an antenna twitches."),
    dict(name="Anyone there?", energy=0.15, kind="intro",
         you="Failed boot: head jerks halfway up on 5, collapses on 7.",
         A="Leans toward you, tilting; taps the air twice toward Reachy 2.", B="Wakes on 6, stretches its antennas, looks at you."),
    dict(name="Lonely", energy=0.15, kind="calm",
         you="Hold still, head low. Small breath on 5.",
         A="Droops toward you, looks at Reachy 2 on 5, two small nods on 7 and 8.", B="Droops, then looks back and nods."),
    dict(name="Charging", energy=0.3, kind="calm",
         you="A small jolt on every beat: shoulders twitch. On 5 to 8, head rises in ticks.",
         A="Points its antenna at you and pulses it on every beat.", B="Same, from the other side."),
    dict(name="Reboot", energy=0.4, kind="mid",
         you="Head up on 1, right arm out on 3, forearm up on 4, left arm out on 5, forearm down on 6, head ticks to Reachy 1 on 7 and Reachy 2 on 8.",
         A="Watches, then cheers each tick: antennas pop on 3, 5 and 7.", B="Same, one beat later."),
    dict(name="Robot walk", energy=0.4, kind="calm",
         you="Stiff robot steps toward Reachy 1 on 1 to 4 (look up at it on 4), then across to Reachy 2 on 5 to 8.",
         A="Greets you with an antenna pop when you reach it on 4, then watches you cross.", B="Tracks you, then greets you on 8."),
    dict(name="Peekaboo", energy=0.5, kind="mid",
         you="Lean back surprised at Reachy 1 on 3 and Reachy 2 on 4. Hands over your face on 5 and 6, open on 7. Laugh on 8.",
         A="Hides on 1 and 2, pops up on 3, pops again on 7, laughs on 8.", B="Pops up on 4, a beat after Reachy 1; pops on 7, laughs on 8."),
    dict(name="Surprise and nod", energy=0.55, kind="mid",
         you="Hands to your head on 1, throw them back on 2. Shake out on 3 and 4. Step-touch toward Reachy 1 on 5 and 6, toward Reachy 2 on 7 and 8.",
         A="Recoils in surprise on 2, then nods on every beat; leans in when you step its way.", B="Same, leaning in on 7."),
    dict(name="Chicken peck", energy=0.7, kind="high",
         you="Funky chicken: elbows flap on every beat, head pecks forward; knee pops on 5 to 8.",
         A="Pecks on odd counts, then in unison on 5 to 8.", B="Pecks on even counts, then in unison."),
    dict(name="Circle", energy=0.5, kind="mid",
         you="Skip a full circle in 8 counts: toward Reachy 1, upstage, past Reachy 2, back to center.",
         A="Turns head and body to follow you all the way around.", B="Same, from the other side."),
    dict(name="Spin", energy=0.65, kind="mid",
         you="Spin with arms out on 1 and 2, land in a V on 3. Watch the robots spin on 5 to 8.",
         A="Dizzy head circles on 1 to 4; turns its back on 5 and 6, whips around on 7, ta-da on 8.", B="Same, turning the other way."),
    dict(name="Running man", energy=0.9, kind="high",
         you="Running man, full energy.",
         A="Head-bangs on every beat; antennas run like arms; body swings.", B="Same, swinging the other way."),
    dict(name="Running man turn", energy=0.85, kind="high",
         you="Running man while turning a full circle over 8 counts.",
         A="Spiral head moves while turning to keep facing you.", B="Same, mirrored."),
    dict(name="Electro arms", energy=0.8, kind="high",
         you="Windmill arms on 1 and 2, hand roll on 3 and 4, sweep toward Reachy 1 on 5 and Reachy 2 on 6, arms in a halo on 7 and 8.",
         A="Antennas circle like arms; pops when you sweep its way on 5; halo on 7 and 8.", B="Opposite phase; pops on 6; halo on 7 and 8."),
    dict(name="Robot square", energy=0.75, kind="high",
         you="Counts 1 to 4: your head ticks to whichever robot just moved. 5 to 8: robot arm hits with both.",
         A="Ping-pong: snaps to a new corner on 1 and 3, then unison on 5 to 8.", B="Answers on 2 and 4, then unison."),
    dict(name="The wave", energy=0.7, kind="high",
         you="A wave crosses your arms toward Reachy 2 on 2 and 3, then back toward Reachy 1 on 6 and 7.",
         A="Starts the wave on 1, catches it back on 8.", B="Catches it on 4, sends it back on 5."),
    dict(name="Everybody", energy=0.95, kind="high",
         you="Running man on 1 to 4, robot arm hits on 5 to 8.",
         A="Head-bangs on 1 to 4, then robot hits on 5 to 8, in unison with you.", B="Same."),
    dict(name="Full power", energy=1.0, kind="finale",
         you="Jump with arms up on 1 and 3. On 5, snap into a power pose: one arm up, other hand on hip. Hold.",
         A="Celebrates on 1 to 4, then leans in toward you, antennas high.", B="Same."),
]
assert len(MOVES) == E.N_PHRASES

# What the dancer does in each 4-count half of every move ({1}..{4} = the piece's own counts, renumbered where it
# lands in the phrase), so dances stitched from halves still read as clear instructions.
YOU_HALVES = [
    ["Frozen: knees soft, arms dead, head hanging.", "Stay frozen, breathing."],
    ["Stay frozen.", "Head glitch on {2}: twitch sideways and drop again."],
    ["Frozen, head down.", "Failed boot: head jerks halfway up on {1}, collapses on {3}."],
    ["Hold still, head low.", "Small breath on {1}, then hold."],
    ["A small shoulder jolt on every count.", "Keep jolting; your head rises in ticks on {1} to {4}."],
    ["Head up on {1}, right arm out on {3}, forearm up on {4}.", "Left arm out on {1}, forearm down on {2}, head ticks to Reachy 1 on {3} and Reachy 2 on {4}."],
    ["Stiff robot steps toward Reachy 1; look up at it on {4}.", "Robot steps across toward Reachy 2; look up at it on {4}."],
    ["Lean back surprised at Reachy 1 on {3} and at Reachy 2 on {4}.", "Hands over your face on {1} and {2}, open them on {3}, laugh on {4}."],
    ["Hands to your head on {1}, throw them back on {2}, shake out on {3} and {4}.", "Step-touch toward Reachy 1 on {1} and {2}, toward Reachy 2 on {3} and {4}."],
    ["Funky chicken: elbows flap on every count, head pecks forward.", "Funky chicken with knee pops on every count."],
    ["Skip toward Reachy 1, then upstage.", "Skip past Reachy 2 and back to center."],
    ["Spin with arms out on {1} and {2}, land in a V on {3}, hold on {4}.", "Hold the V and watch the robots spin; ta-da on {4}."],
    ["Running man.", "Running man."],
    ["Running man, turning a half circle.", "Running man, finishing the full circle."],
    ["Windmill arms on {1} and {2}, hand roll on {3} and {4}.", "Sweep toward Reachy 1 on {1} and Reachy 2 on {2}, arms in a halo on {3} and {4}."],
    ["Your head ticks to whichever robot just moved, on every count.", "Robot arm hits on every count, with both robots."],
    ["A wave travels through your arms toward Reachy 2 on {2} and {3}.", "The wave comes back toward Reachy 1 on {2} and {3}."],
    ["Running man.", "Robot arm hits on every count."],
    ["Jump with arms up on {1} and {3}.", "Snap into a power pose on {1}: one arm up, other hand on hip. Hold."],
]
for _m, _h in zip(MOVES, YOU_HALVES):
    _m["you_halves"] = _h
_PROFILES = None


def profiles() -> dict:
    """move_profiles.json (tools/build_move_profiles.mjs): hits, energy, start/end pose of every 4-count piece."""
    global _PROFILES
    if _PROFILES is None:
        d = json.loads((Path(__file__).with_name("move_profiles.json")).read_text())
        _PROFILES = {(p["src"], p["half"]): p for p in d["pieces"]}
    return _PROFILES


def pieces_of(p: dict) -> list[dict]:
    """The two 4-count pieces of a phrase: its own halves, two halves stitched from other moves, or learned from a video."""
    if p.get("learned"):
        i = p["n"] - 1
        return [{"src": p["src"], "half": h, "mirror": False, "learned": i} for h in (0, 1)]
    h = p.get("halves")
    if h:
        return [{"src": int(x["src"]), "half": int(x["half"]), "mirror": bool(x.get("mirror"))} for x in h[:2]]
    return [{"src": p["src"], "half": 0, "mirror": bool(p.get("mirror"))}, {"src": p["src"], "half": 1, "mirror": bool(p.get("mirror"))}]


def joint(a: dict, b: dict) -> str:
    """How piece a hands over to piece b: the same move carrying on, Encendido's own next phrase, or a crossfade."""
    la, lb = a.get("learned"), b.get("learned")
    if la is not None or lb is not None:          # a video dance carries on smoothly into its own next piece
        if la is not None and lb is not None and ((la == lb and a["half"] == 0 and b["half"] == 1) or (lb == la + 1 and a["half"] == 1 and b["half"] == 0)):
            return "inside"
        return "cross"
    if a["src"] == b["src"] and a["mirror"] == b["mirror"] and a["half"] == 0 and b["half"] == 1:
        return "inside"
    if not a["mirror"] and not b["mirror"] and a["half"] == 1 and b["half"] == 0 and b["src"] == a["src"] + 1:
        return "encendido"
    return "cross"


LEARNED_LIMITS = [(-1, 1), (-0.6, 0.6), (-0.4, 0.4), (-0.8, 0.8), (0, 0), (0.05, 1.35), (0.05, 1.35), (-10, 12)]   # POSE_KEYS order
XF_BEFORE, XF_AFTER = 0.5, 0.25         # crossfade between unrelated pieces: from half a count before the join to a quarter after

POOLS = {"low": [4, 10, 6, 3, 4], "mid": [5, 7, 8, 9, 11, 16, 10], "high": [12, 13, 14, 15, 17, 9, 16]}
SECTION_NAMES = {"intro": "Intro", "low": "Calm", "mid": "Groove", "high": "Peak", "finale": "Finale"}
ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII", "XIV", "XV", "XVI"]


def slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40]
    return s or "song"


def count_tempo(bpm: float) -> tuple[float, float]:
    """(beats per count, counts per minute): keep the counts between ~73 and 145 a minute, where the moves look right."""
    if bpm > 145:
        return 2.0, bpm / 2
    if bpm < 73:
        return 0.5, bpm * 2
    return 1.0, bpm


def levels(energy: list[float]) -> list[str]:
    """Each phrase's loudness relative to the rest of the song: low, mid or high."""
    if not energy:
        return []
    lo, hi = min(energy), max(energy)
    span = (hi - lo) or 1.0
    order = sorted(energy)
    out = []
    for e in energy:
        rank = order.index(e) / max(1, len(order) - 1)
        k = 0.5 * (e - lo) / span + 0.5 * rank
        out.append("low" if k < 0.34 else "high" if k >= 0.67 else "mid")
    return out


def generate(analysis: dict, title: str = "My song", seed: int | None = None) -> dict:
    """A choreography from the browser's analysis of a song.

    analysis: {bpm, first_downbeat_s, duration_s, phrase_energy: [one per 8-count phrase from the downbeat],
               count_times?: [song seconds of every count, 8 x phrases + 1; follows a drifting tempo],
               phrase_labels?: [the same letter for phrases that sound alike: verse A, chorus B, ...],
               beats_per_count?: 1 | 2 | 0.5}
    Phrases that sound alike get the same moves (a chorus is danced the same way each time it comes back),
    calm moves go on quiet sections and big ones on loud sections.
    """
    bpm = float(analysis["bpm"])
    if not 40 <= bpm <= 240:
        raise ValueError("tempo must be 40 to 240 BPM")
    bpc, cbpm = count_tempo(bpm)
    if analysis.get("beats_per_count") in (0.5, 1, 2, 1.0, 2.0):
        bpc = float(analysis["beats_per_count"]); cbpm = bpm / bpc
    energy = [float(x) for x in analysis.get("phrase_energy", [])][:MAX_PHRASES]
    if len(energy) < 2:
        raise ValueError("the song is too short: it needs at least two 8-count phrases after the first downbeat")
    n = len(energy)
    labels = list(analysis.get("phrase_labels") or [])[:n]
    if len(labels) < n:
        labels = [chr(65 + i) for i in range(n)]          # no structure given: every phrase is its own
    rng = random.Random(seed if seed is not None else int(time.time()))

    # Each section (a run of phrases with one label) gets a level from its own mean energy, ranked among sections.
    runs = []                                          # [label, first, last]
    for i, lab in enumerate(labels):
        if runs and runs[-1][0] == lab:
            runs[-1][2] = i
        else:
            runs.append([lab, i, i])
    # Each part of the song (a label) gets one level, ranked against the other parts, so a chorus that is only a
    # little louder than its verse still gets the big moves. Evenly loud songs (rock, pop) need the ranking.
    lab_e = {}
    for lab, e in zip(labels, energy):
        lab_e.setdefault(lab, []).append(e)
    lab_mean = {lab: sum(v) / len(v) for lab, v in lab_e.items()}
    lv = [None] * n
    if analysis.get("phrase_labels") and len(lab_mean) >= 2:
        order = sorted(lab_mean, key=lab_mean.get)
        main = [l for l in order if len(lab_e[l]) >= 2] or order    # parts that last; one-phrase intros/outros don't set the scale
        # The chorus: the part that comes back most often (and closes the song), not just the loudest one.
        runs_of = {}
        for i, lab in enumerate(labels):
            if i == 0 or labels[i - 1] != lab:
                runs_of[lab] = runs_of.get(lab, 0) + 1
        closing = next((labels[i] for i in range(n - 1, -1, -1) if labels[i] in main), None)
        top = max(main, key=lambda l: runs_of.get(l, 0) + (0.5 if l == closing else 0) + lab_mean[l])
        spread = lab_mean[top] - lab_mean[main[0]]
        lab_level = {}
        for lab in order:
            if lab == top:
                lab_level[lab] = "high"
            elif lab_mean[lab] < lab_mean[top] - 0.25:
                lab_level[lab] = "low"
            elif spread < 0.12:                                 # evenly loud song: the other parts groove
                lab_level[lab] = "mid"
            else:
                k = (lab_mean[lab] - lab_mean[main[0]]) / spread
                lab_level[lab] = "low" if k < 0.34 else "high" if k >= 0.75 else "mid"
        lv = [lab_level[lab] for lab in labels]
    else:
        lv = levels(energy)
    # Within a section, still lift the louder half of its phrases a level.
    for (lab, a, b) in runs:
        if b > a:
            mid = sorted(energy[a:b + 1])[(b - a + 1) // 2]
            for i in range(a, b + 1):
                if energy[i] > mid + 0.08 and lv[i] != "high":
                    lv[i] = "mid" if lv[i] == "low" else "high"

    # The opening: the robots wake up while the music is quiet (only as long as the first section stays quiet).
    intro = 0
    while intro < min(4, n - 1) and lv[intro] == "low" and (not analysis.get("phrase_labels") or labels[intro] == labels[0]):
        intro += 1
    accents = analysis.get("phrase_accents") if len(analysis.get("phrase_accents") or []) >= n else None
    picks = choose_pieces(n, lv, energy, labels, intro, accents, rng)
    # Section names: the song's own structure when we have it (Part A, B...), else runs of one level.
    names, last, count = {}, None, 0
    for i, p in enumerate(picks):
        key = (labels[i], p["level"] if not analysis.get("phrase_labels") else "")
        if i == n - 1:
            key = ("finale", "")
        if key != last:
            count += 1; last = key
        if analysis.get("phrase_labels") and i < n - 1 and p["level"] != "intro":
            word = {"low": "calm", "mid": "groove", "high": "peak"}[p["level"]]
            p["section"] = f"{ROMAN[min(count, len(ROMAN)) - 1]}. Part {labels[i]} · {word}"
        else:
            p["section"] = f"{ROMAN[min(count, len(ROMAN)) - 1]}. {SECTION_NAMES[p['level']]}"
    phrases = [{"n": i + 1, "src": p["src"], "mirror": p["mirror"], "level": p["level"], "section": p["section"],
                "energy": round(energy[i], 3), "label": labels[i], **({"repeat": True} if p.get("repeat") else {}),
                **({"halves": p["halves"]} if p.get("halves") else {})}
               for i, p in enumerate(picks)]
    down = float(analysis.get("first_downbeat_s", 0.0))
    ct = analysis.get("count_times")
    counts = None
    if ct and len(ct) >= 8 * n + 1:
        counts = [round(float(c) - down, 4) for c in ct[:8 * n + 1]]
    return {
        "format": 2, "title": title.strip() or "My song", "slug": slugify(title),
        "song": {"bpm": round(bpm, 2), "first_downbeat_s": round(down, 3),
                 "duration_s": round(float(analysis.get("duration_s", 0.0)), 2), "file": analysis.get("file"),
                 "tempo_range": analysis.get("tempo_range")},
        "beats_per_count": bpc, "count_bpm": round(cbpm, 3), "phrases": phrases, "counts": counts,
        "accents": accents, "quality": assess(phrases, accents),
        "created": time.strftime("%Y-%m-%d %H:%M"),
    }


# ---------- choosing the pieces: rhythm, flow, energy, variety ----------

LEVEL_ENERGY = {"intro": 0.05, "low": 0.25, "mid": 0.55, "high": 0.85, "finale": 0.9}
W_RHYTHM, W_ENERGY, W_FLOW, W_REPEAT = 3.0, 0.5, 1.4, 0.25     # tuned on Blondie: rhythm 58 -> 65, smooth joins 62% -> 77%
BEAM = 24
CANDIDATES = [{"src": k, "half": h, "mirror": m} for k in range(4, 18) for h in (0, 1) for m in (False, True)]


def _mirror_feat(f: dict) -> dict:
    """move_profiles start/end features seen in a mirror (robot keys yaw..bob, human aL..lean)."""
    fl = lambda r: [-r[0], r[1], -r[2], -r[3], r[5], r[4], r[6]]
    h = f["H"]
    return {"A": fl(f["B"]), "B": fl(f["A"]), "H": [h[2], h[3], h[0], h[1], -h[4], -h[5], h[6], -h[7], h[8], -h[9]]}


def _feat(g: dict, which: str) -> dict:
    f = profiles()[(g["src"], g["half"])][which]
    return _mirror_feat(f) if g["mirror"] else f


def pose_jump(a: dict, b: dict) -> float:
    """How far the dance has to jump (summed degrees, both robots and the dancer) when piece a hands over to b."""
    if joint(a, b) in ("inside", "encendido"):
        return 0.0
    e, s0 = _feat(a, "end"), _feat(b, "start")
    return sum(abs(x - y) for k in ("A", "B", "H") for x, y in zip(e[k], s0[k])) / 3


def _corr(x: list, y: list) -> float | None:
    n = len(x)
    mx, my = sum(x) / n, sum(y) / n
    vx, vy = sum((a - mx) ** 2 for a in x), sum((b - my) ** 2 for b in y)
    if vx < 1e-9 or vy < 1e-9:
        return None
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / math.sqrt(vx * vy)


def _flat(v: list) -> bool:
    m = sum(v) / len(v)
    return m <= 1e-9 or math.sqrt(sum((x - m) ** 2 for x in v) / len(v)) / m < 0.12


def rhythm_match(g: dict, music: list | None) -> float | None:
    """-1..1: do this piece's hits fall where the music accents (8 half-counts)? None when there's nothing to match.
    Half of it is on-count vs between-count timing; the other half is WHICH of the 4 counts carry the hits
    (a move that hits only on 3 and 4 shouldn't count as matching music that hits on every count)."""
    if not music:
        return None
    acc = profiles()[(g["src"], g["half"])]["accents"]
    whole = _corr(acc, music)
    if whole is None:
        return None
    on_a, on_m = acc[0::2], music[0::2]
    fa, fm = _flat(on_a), _flat(on_m)
    which = 1.0 if fa and fm else 0.0 if fa or fm else (_corr(on_a, on_m) or 0.0)
    return 0.5 * whole + 0.5 * which


_ENERGY_RANK = None


def piece_energy(g: dict) -> float:
    """0..1, ranked among the candidate pieces."""
    global _ENERGY_RANK
    if _ENERGY_RANK is None:
        es = sorted(profiles()[(c["src"], c["half"])]["energy"] for c in CANDIDATES[::2])
        _ENERGY_RANK = lambda e: bisect.bisect_left(es, e) / max(1, len(es) - 1)
    return _ENERGY_RANK(profiles()[(g["src"], g["half"])]["energy"])


_JUMP_SCALE = None


def jump_scale() -> float:
    """A typical jump between two unrelated pieces, so flow costs read ~1 for an ordinary join."""
    global _JUMP_SCALE
    if _JUMP_SCALE is None:
        js = sorted(pose_jump(a, b) for a in CANDIDATES[::3] for b in CANDIDATES[1::3] if joint(a, b) == "cross")
        _JUMP_SCALE = js[len(js) // 2] or 1.0
    return _JUMP_SCALE


def choose_pieces(n, lv, energy, labels, intro, accents, rng) -> list[dict]:
    """Picks two 4-count pieces per phrase with a beam search. Each piece costs:
    rhythm (its hits vs the music's accents), energy (vs the part of the song), flow (the pose jump from the
    previous piece; carrying a move on is free and preferred), and repetition. Returning song parts are danced
    the same way; the robots wake up over a quiet intro and the dance ends on Full power."""
    mean_e = sum(energy) / n
    noise = {}                                               # same random tie-breaks for every beam ("another version")

    def cost(j, g, prev, hist):
        i, hh = divmod(j, 2)
        music = accents[i][8 * hh:8 * hh + 8] if accents else None
        r = rhythm_match(g, music)
        c = W_RHYTHM * (0.5 if r is None else (1 - r) / 2)
        target = min(1.0, max(0.0, LEVEL_ENERGY[lv[i]] + 0.6 * (energy[i] - mean_e)))
        c += W_ENERGY * abs(piece_energy(g) - target)
        if prev is not None:
            kind = joint(prev, g)
            c += W_FLOW * min(3.0, pose_jump(prev, g) / jump_scale())
            if kind == "inside":
                c -= 0.35                                    # whole moves read best for the dancer
        recent = [h for h in hist[-6:]]
        if any(h["src"] == g["src"] for h in recent) and not (prev and joint(prev, g) == "inside"):
            c += W_REPEAT
        if any(h == g for h in hist[-14:]):
            c += 0.3
        if lv[i] == "high" and hh == 0 and i > 0 and lv[i - 1] != "high" and g["src"] in (8, 11) and g["half"] == 0:
            c -= 0.3                                         # the drop: a surprise or a spin into the chorus
        key = (j, g["src"], g["half"], g["mirror"])
        if key not in noise:
            noise[key] = rng.uniform(0, 0.15)
        return c + noise[key]

    fixed = {}
    for i, src in enumerate({0: [], 1: [1], 2: [1, 2], 3: [0, 1, 2], 4: [0, 1, 2, 3]}[intro]):
        fixed[2 * i], fixed[2 * i + 1] = {"src": src, "half": 0, "mirror": False}, {"src": src, "half": 1, "mirror": False}
    fixed[2 * n - 2], fixed[2 * n - 1] = {"src": 18, "half": 0, "mirror": False}, {"src": 18, "half": 1, "mirror": False}
    # where each part of the song starts, and which occurrence it is
    start_of, occ_of, seen_runs = [0] * n, [0] * n, {}
    for i in range(n):
        if i == 0 or labels[i] != labels[i - 1]:
            seen_runs[labels[i]] = seen_runs.get(labels[i], -1) + 1
            st = i
        start_of[i], occ_of[i] = st, seen_runs[labels[i]]

    beams = [(0.0, [], {})]                                   # (cost, pieces, first time each (label, slot-in-part) was danced)
    for j in range(2 * n):
        i, hh = divmod(j, 2)
        key = (labels[i], 2 * (i - start_of[i]) + hh)
        nxt = []
        for total, hist, seen in beams:
            prev = hist[-1] if hist else None
            if j in fixed:
                options = [fixed[j]]
            elif occ_of[i] and key in seen:                   # the part came back: same moves (mirrored on its 3rd time)
                f = seen[key]
                options = [{**f, "mirror": f["mirror"] ^ (occ_of[i] >= 2 and occ_of[i] % 2 == 0)}]
            else:
                options = CANDIDATES
                if hh == 1 and prev and prev["half"] == 0 and prev["src"] >= 4:
                    options = CANDIDATES + [{"src": prev["src"], "half": 1, "mirror": prev["mirror"]}]
            for g in options:
                c = cost(j, g, prev, hist)
                s2 = seen if key in seen or j in fixed else {**seen, key: g}
                nxt.append((total + c, hist + [g], s2))
        nxt.sort(key=lambda b: b[0])
        beams, uniq = [], set()
        for b in nxt:                                         # keep different endings, not 24 copies of one
            sig = (b[1][-1]["src"], b[1][-1]["half"], b[1][-1]["mirror"], b[1][-2]["src"] if len(b[1]) > 1 else None)
            if sig in uniq:
                continue
            uniq.add(sig); beams.append(b)
            if len(beams) >= BEAM:
                break
    best = beams[0][1]
    out = []
    for i in range(n):
        a, b = best[2 * i], best[2 * i + 1]
        level = "intro" if i < intro else "finale" if i == n - 1 else lv[i]
        p = {"src": a["src"], "mirror": a["mirror"], "level": level}
        if joint(a, b) != "inside":
            p["halves"] = [a, b]
        if occ_of[i] and (labels[i], 2 * (i - start_of[i])) in {(labels[k], 2 * (k - start_of[k])) for k in range(i) if occ_of[k] == 0}:
            p["repeat"] = True
        out.append(p)
    return out


def assess(phrases: list, accents: list | None) -> dict:
    """How well a dance fits its song: rhythm (do hits land on the accents), flow (smooth joins), variety."""
    segs = [g for p in phrases for g in pieces_of(p)]
    rs = []
    for j, g in enumerate(segs):
        i, hh = divmod(j, 2)
        if g["src"] < 4 or g["src"] == 18 or g.get("learned") is not None or not accents or i >= len(accents):
            continue
        r = rhythm_match(g, accents[i][8 * hh:8 * hh + 8])
        if r is not None:
            rs.append(r)
    jumps = [None if (a.get("learned") is not None or b.get("learned") is not None) and joint(a, b) == "cross"
             else (0.0 if joint(a, b) == "inside" else pose_jump(a, b) / jump_scale()) for a, b in zip(segs, segs[1:])]
    known = [x for x in jumps if x is not None]
    smooth = sum(1 for x in known if x < 0.6) / max(1, len(known))
    per = []
    for i in range(len(phrases)):
        a, b = segs[2 * i], segs[2 * i + 1]
        rr = [rhythm_match(g, accents[i][8 * h:8 * h + 8]) if accents and i < len(accents) and g.get("learned") is None else None for h, g in enumerate((a, b))]
        rr = [x for x in rr if x is not None]
        per.append({"rhythm": round(sum(rr) / len(rr), 2) if rr else None,
                    "flow_in": round(jumps[2 * i - 1], 2) if i and jumps[2 * i - 1] is not None else None})
    return {"rhythm": round(100 * (sum(rs) / len(rs) + 1) / 2) if rs else None,
            "flow": round(100 * smooth), "variety": len({(g["src"], g["half"]) for g in segs}), "phrases": per}


def validate(ch: dict) -> dict:
    """Checks a choreography (generated, or edited on the Create page) before saving or playing it."""
    if not isinstance(ch, dict) or not isinstance(ch.get("phrases"), list):
        raise ValueError("not a choreography")
    if not 2 <= len(ch["phrases"]) <= MAX_PHRASES:
        raise ValueError(f"a choreography has 2 to {MAX_PHRASES} phrases")
    cbpm = float(ch.get("count_bpm", 0))
    if not 60 <= cbpm <= 180:
        raise ValueError("count tempo must be 60 to 180 a minute")
    for i, p in enumerate(ch["phrases"]):
        if not isinstance(p.get("src"), int) or not 0 <= p["src"] < len(MOVES):
            raise ValueError(f"phrase {i + 1}: unknown move")
        p["n"] = i + 1
        p["mirror"] = bool(p.get("mirror"))
        if p.get("halves") is not None:
            h = p["halves"]
            if not isinstance(h, list) or len(h) != 2 or any(not isinstance(x, dict) or not isinstance(x.get("src"), int)
                                                               or not 0 <= x["src"] < len(MOVES) or x.get("half") not in (0, 1) for x in h):
                raise ValueError(f"phrase {i + 1}: bad halves")
            p["halves"] = [{"src": x["src"], "half": x["half"], "mirror": bool(x.get("mirror"))} for x in h]
        p.setdefault("section", "I. Dance")
    learned = (ch.get("learned") or {}).get("phrases") or {}
    steps = int((ch.get("learned") or {}).get("steps", 8))
    for i, p in enumerate(ch["phrases"]):
        if p.get("learned"):
            tr = learned.get(str(i))
            if not tr or any(len(tr.get(k) or []) != 8 * steps + 1 for k in ("H", "A", "B")):
                raise ValueError(f"phrase {i + 1}: its learned moves are missing")
            for k in ("A", "B"):                  # keep video-derived robot moves inside the safe ranges
                tr[k] = [[max(lo, min(hi, float(v))) for v, (lo, hi) in zip(row, LEARNED_LIMITS)] for row in tr[k]]
    c = ch.get("counts")
    if c is not None:
        n = len(ch["phrases"])
        if not isinstance(c, list) or len(c) < 8 * n + 1:
            c = None                                       # phrases were added: fall back to the average tempo
        else:
            c = [float(v) for v in c[:8 * n + 1]]
            if any(b <= a for a, b in zip(c, c[1:])):
                raise ValueError("count times must increase")
        ch["counts"] = c
    ch["slug"] = slugify(ch.get("slug") or ch.get("title", "song"))
    return ch


# ---------- playing it ----------

def mirror_pose(r: RobotPose) -> RobotPose:
    """The same move seen in a mirror: left and right swap."""
    return RobotPose(yaw=-r.yaw, pitch=r.pitch, roll=-r.roll, body=-r.body, turn=-r.turn, antL=r.antR, antR=r.antL, bob=r.bob)


class GeneratedScore:
    """Has the same interface as the encendido score module, so agents, reactor and dashboard use it unchanged."""

    PHRASE_BEATS = 8
    POS = E.POS
    toward = staticmethod(E.toward)

    def __init__(self, choreo: dict):
        self.choreo = validate(choreo)
        self.name = self.choreo["slug"]
        self.phrases = self.choreo["phrases"]
        self.N_PHRASES = len(self.phrases)
        n = 8 * self.N_PHRASES
        # Show time of every count: the song's real beats when the analysis tracked them, else an even grid.
        beat = 60.0 / float(self.choreo["count_bpm"])
        self.counts = self.choreo.get("counts") or [k * beat for k in range(n + 1)]
        self.DURATION = self.counts[-1]
        self.BEAT = self.DURATION / n                      # averages, for countdowns and echo delays
        self.BPM = 60.0 / self.BEAT
        self.PH = self.BEAT * self.PHRASE_BEATS
        self.BLEND_S = min(E.BLEND_S, 0.6 * self.BEAT)
        self.segs = [g for p in self.phrases for g in pieces_of(p)]
        lr = self.choreo.get("learned") or {}
        self.learned, self.learned_steps = lr.get("phrases") or {}, int(lr.get("steps", 8))
        self.joints = ["start"] + [joint(a, b) for a, b in zip(self.segs, self.segs[1:])]
        self._first = self.counts[1] - self.counts[0]
        self._last = self.counts[-1] - self.counts[-2]

    def count_of(self, t: float) -> float:
        """Count position at show time t (0 = count 1 of phrase 1; 8.5 = halfway through phrase 2's count 1)."""
        c = self.counts
        if t <= c[0]:
            return (t - c[0]) / self._first
        if t >= c[-1]:
            return len(c) - 1 + (t - c[-1]) / self._last
        k = bisect.bisect_right(c, t) - 1
        return k + (t - c[k]) / (c[k + 1] - c[k])

    def time_of(self, count: float) -> float:
        """Show time of a count position (the inverse of count_of)."""
        c = self.counts
        if count <= 0:
            return c[0] + count * self._first
        if count >= len(c) - 1:
            return c[-1] + (count - (len(c) - 1)) * self._last
        k = int(count)
        return c[k] + (count - k) * (c[k + 1] - c[k])

    def phrase_at(self, t: float) -> int:
        return int(clamp(math.floor(self.count_of(t) / 8), 0, self.N_PHRASES - 1))

    # The dance plays as 4-count pieces (two per phrase). A piece that carries its move on, or Encendido's own
    # next phrase, plays exactly as written; anything else crossfades over the join so motion never jumps.
    def _seg_index(self, c: float) -> int:
        return int(clamp(math.floor(c / 4), 0, len(self.segs) - 1))

    def _seg_source(self, j: int, t: float):
        g = self.segs[j]
        c = clamp(self.count_of(t) - 4 * j, 0.0, 4 - 1e-4)
        return g["src"], g["src"] * E.PH + (4 * g["half"] + c) * E.BEAT, g["mirror"]

    def _learned_at(self, j: int, t: float, key: str) -> list:
        g = self.segs[j]
        tr = self.learned[str(g["learned"])][key]
        x = (4 * g["half"] + clamp(self.count_of(t) - 4 * j, 0.0, 4.0)) * self.learned_steps
        k = min(int(x), len(tr) - 2)
        f = x - k
        return [a + f * (b - a) for a, b in zip(tr[k], tr[k + 1])]

    def seg_raw(self, j: int, t: float, dancer_x=None, dancer_depth=None):
        if self.segs[j].get("learned") is not None:     # moves learned from a video: play the stored tracks
            return {s: RobotPose(*self._learned_at(j, t, s)) for s in ("A", "B")}
        k, te, m = self._seg_source(j, t)
        if m and dancer_x is not None:
            dancer_x = -dancer_x
        out = E.raw(k, te, dancer_x, dancer_depth)
        return {"A": mirror_pose(out["B"]), "B": mirror_pose(out["A"])} if m else out

    def raw(self, i: int, t: float, dancer_x=None, dancer_depth=None):
        """Phrase i's piece at show time t (no blending)."""
        j = 2 * i + (1 if self.count_of(t) - 8 * i >= 4 else 0)
        return self.seg_raw(j, t, dancer_x, dancer_depth)

    def scripted_dancer(self, t: float) -> tuple[float, float]:
        t = min(max(t, 0.0), self.DURATION - 1e-4)
        j = self._seg_index(self.count_of(t))
        if self.segs[j].get("learned") is not None:
            return self._learned_at(j, t, "H")[0], 0.0              # the video dancer's position
        k, te, m = self._seg_source(j, t)
        x, d = E.scripted_dancer(te)
        return (-x if m else x), d

    def robot_poses(self, t: float, dancer_x=None, dancer_depth=None):
        if t < 0:
            return self.seg_raw(0, self.time_of(0))
        t = min(t, self.DURATION - 1e-4)
        c = self.count_of(t)
        j = self._seg_index(c)
        cur = self.seg_raw(j, t, dancer_x, dancer_depth)
        span = XF_BEFORE + XF_AFTER
        if j > 0:
            kind, tb = self.joints[j], self.time_of(4 * j)
            if kind == "encendido" and t - tb < self.BLEND_S:
                prev = self.seg_raw(j - 1, tb - 1e-4, dancer_x, dancer_depth)
                return self._mix(prev, cur, ease((t - tb) / self.BLEND_S))
            if kind == "cross" and c - 4 * j < XF_AFTER:
                prev = self.seg_raw(j - 1, t, dancer_x, dancer_depth)      # held at its last pose
                return self._mix(prev, cur, ease((c - (4 * j - XF_BEFORE)) / span))
        if j + 1 < len(self.segs) and self.joints[j + 1] == "cross" and c > 4 * j + 4 - XF_BEFORE:
            nxt = self.seg_raw(j + 1, t, dancer_x, dancer_depth)           # held at its first pose
            return self._mix(cur, nxt, ease((c - (4 * j + 4 - XF_BEFORE)) / span))
        return cur

    @staticmethod
    def _mix(a, b, k):
        return {s: mix(a[s], b[s], k) for s in ("A", "B")}

    def robot_pose(self, side: str, t: float, dancer_x=None, dancer_depth=None) -> RobotPose:
        return self.robot_poses(t, dancer_x, dancer_depth)[side]


def _swap_names(text: str) -> str:
    return text.replace("Reachy 1", "\0").replace("Reachy 2", "Reachy 1").replace("\0", "Reachy 2")


def phrase_texts(src: int, mirror: bool) -> dict:
    m = MOVES[src]
    you, a, b = m["you"], m["A"], m["B"]
    if mirror:
        you, a, b = _swap_names(you), _swap_names(b), _swap_names(a)
    return {"name": m["name"] + (" (mirrored)" if mirror else ""), "you": you, "A": a, "B": b}


def piece_text(g: dict, slot: int) -> str:
    """The dancer's instruction for a 4-count piece placed in half `slot` (0 or 1) of its phrase."""
    t = MOVES[g["src"]]["you_halves"][g["half"]]
    for k in range(1, 5):
        t = t.replace("{%d}" % k, str(4 * slot + k))
    return _swap_names(t) if g["mirror"] else t


LEARNED_TEXT = {"name": "From your video", "you": "Do what the dancer in the video does: the gold target arms on the camera show you.",
                "A": "Copies your arms with its antennas, bounces with your knees and keeps facing you.",
                "B": "Copies your arms with its antennas, bounces with your knees and keeps facing you."}


def phrase_texts_for(p: dict) -> dict:
    """Name and instructions for a phrase, whole move or two stitched halves."""
    if p.get("learned"):
        return dict(LEARNED_TEXT)
    a, b = pieces_of(p)
    if joint(a, b) == "inside":
        return phrase_texts(a["src"], a["mirror"])
    nm = lambda g: MOVES[g["src"]]["name"] + (" ⇄" if g["mirror"] else "")
    ra = lambda g: phrase_texts(g["src"], g["mirror"])
    return {"name": f"{nm(a)} → {nm(b)}", "you": f"1–4: {piece_text(a, 0)} 5–8: {piece_text(b, 1)}",
            "A": f"{ra(a)['A']} Then: {ra(b)['A']}", "B": f"{ra(a)['B']} Then: {ra(b)['B']}"}


def _piece_react(src_ph: dict, g: dict, slot: int) -> tuple[dict, list]:
    """A source phrase's reactions and cues, cut to one 4-count piece and moved to where it lands."""
    react = json.loads(json.dumps(src_ph.get("react", {}) or {}))
    lo0, shift = 4 * g["half"], 4 * (slot - g["half"])
    trig = []
    for tr in react.pop("triggers", []) or []:
        lo, hi = tr.get("counts", [0, 7])
        a, b = max(lo, lo0), min(hi, lo0 + 3)
        if a <= b:
            trig.append({**tr, "counts": [a + shift, b + shift]})
    cues = []
    for c in src_ph.get("cues", []) or []:
        if lo0 <= c["count"] - 1 <= lo0 + 3:
            c = {**c, "count": c["count"] + shift}
            if g["mirror"] and c.get("side") in ("A", "B"):
                c["side"] = "B" if c["side"] == "A" else "A"
            cues.append(c)
    return {**react, "triggers": trig}, cues


def build_sheet(choreo: dict, base_sheet: dict) -> dict:
    """The phrase sheet (dancer prompts, reactions, cues) for a generated choreography, borrowed from its moves."""
    phrases = []
    for p in choreo["phrases"]:
        txt = phrase_texts_for(p)
        react, cues = {}, []
        for slot, g in enumerate(pieces_of(p)):
            if g.get("learned") is not None:
                react["gaze"] = max(react.get("gaze", 0), 0.3)
                continue
            r, c = _piece_react(base_sheet["phrases"][g["src"]], g, slot)
            cues += c
            for k, v in r.items():
                if k == "triggers":
                    react.setdefault("triggers", []).extend(v)
                elif isinstance(v, bool):
                    react[k] = react.get(k, False) or v
                elif isinstance(v, (int, float)):
                    react[k] = max(react.get(k, 0), v)
        if not react.get("triggers"):
            react.pop("triggers", None)
        phrases.append({"n": p["n"], "act": p.get("section", ""), "name": txt["name"], "dancer": txt["you"],
                        "react": react, "cues": cues, "robots": {"A": txt["A"], "B": txt["B"]},
                        "src": p["src"], "mirror": p["mirror"], "halves": pieces_of(p), "learned": bool(p.get("learned"))})
    return {"bpm": choreo["count_bpm"], "phrase_beats": 8, "phrases": phrases}


# ---------- the library on disk ----------

def choreo_path(slug: str) -> Path:
    return LIBRARY / slugify(slug) / "choreo.json"


def exists(slug: str) -> bool:
    return bool(slug) and choreo_path(slug).is_file()


def load(slug: str) -> dict:
    return json.loads(choreo_path(slug).read_text())


def song_file(slug: str) -> Path | None:
    d = LIBRARY / slugify(slug)
    for f in sorted(d.glob("song.*")) if d.is_dir() else []:
        if f.suffix.lower() in AUDIO_EXT:
            return f
    return None


def save(choreo: dict) -> dict:
    ch = validate(choreo)
    d = LIBRARY / ch["slug"]
    d.mkdir(parents=True, exist_ok=True)
    f = song_file(ch["slug"])
    ch["song"] = {**ch.get("song", {}), "file": f.name if f else None}
    (d / "choreo.json").write_text(json.dumps(ch, indent=1))
    return ch


VIDEO_EXT = {".mp4", ".mov", ".m4v", ".webm", ".mkv"}


def video_file(slug: str) -> Path | None:
    d = LIBRARY / slugify(slug)
    for f in sorted(d.glob("video.*")) if d.is_dir() else []:
        if f.suffix.lower() in VIDEO_EXT:
            return f
    return None


def video_target(slug: str, ext: str) -> Path:
    """Where an uploaded reference video goes (replacing an older one)."""
    ext = ext.lower() if ext.startswith(".") else "." + ext.lower()
    if ext not in VIDEO_EXT:
        raise ValueError(f"unsupported video type {ext}")
    d = LIBRARY / slugify(slug)
    d.mkdir(parents=True, exist_ok=True)
    for old in d.glob("video.*"):
        old.unlink()
    return d / f"video{ext}"


def save_song(slug: str, ext: str, data: bytes) -> Path:
    ext = ext.lower() if ext.startswith(".") else "." + ext.lower()
    if ext not in AUDIO_EXT:
        raise ValueError(f"unsupported audio type {ext}")
    d = LIBRARY / slugify(slug)
    d.mkdir(parents=True, exist_ok=True)
    for old in d.glob("song.*"):
        old.unlink()
    f = d / f"song{ext}"
    f.write_bytes(data)
    return f


def unique_slug(title: str) -> str:
    base = slugify(title)
    s, k = base, 2
    while (LIBRARY / s).exists():
        s, k = f"{base}-{k}", k + 1
    return s


def listing() -> list[dict]:
    out = [{"slug": "encendido", "title": "Encendido", "builtin": True, "phrases": E.N_PHRASES, "count_bpm": E.BPM,
            "duration_s": E.DURATION, "song": None}]
    if LIBRARY.is_dir():
        for f in sorted(LIBRARY.glob("*/choreo.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                ch = json.loads(f.read_text())
                n = len(ch["phrases"])
                out.append({"slug": ch["slug"], "title": ch.get("title", ch["slug"]), "builtin": False, "phrases": n,
                            "count_bpm": ch["count_bpm"], "duration_s": round(ch["counts"][-1] if ch.get("counts") else n * 8 * 60 / ch["count_bpm"], 1),
                            "song": ch.get("song", {}), "created": ch.get("created")})
            except (OSError, ValueError, KeyError):
                continue
    return out
