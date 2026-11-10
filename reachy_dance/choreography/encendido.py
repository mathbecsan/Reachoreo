"""Encendido: the robot score, ported line by line from the animated preview.

Both robots live in one score because their parts are written against each other
(call and response, ping-pong, mirrored turns). Each robot agent evaluates the
score and takes its own side: "A" = Reachy on the camera's left, "B" = camera's right.

tests/test_choreography.py checks this file against motion exported from the preview.
"""
from __future__ import annotations

import math

from ..pose import RobotPose, mix
from ..util import bump, ease, lerp, pulse, seq, clamp

BPM = 120.0
BEAT = 60.0 / BPM
PHRASE_BEATS = 8
PH = BEAT * PHRASE_BEATS
N_PHRASES = 19
DURATION = N_PHRASES * PH
BLEND_S = 0.3

# Stage coordinates (preview pixels). Dancer x is an offset from center.
POS = {"A": 360.0, "C": 800.0, "B": 1240.0}


def toward(from_x: float, to_x: float) -> float:
    return clamp((to_x - from_x) / 600.0, -1, 1)


def count_of(t: float) -> float:
    """Count position at show time t (0 = count 1 of phrase 1). Song dances follow the song's real beats instead."""
    return t / BEAT


def time_of(count: float) -> float:
    return count * BEAT


def phrase_at(t: float) -> int:
    return int(clamp(math.floor(t / PH), 0, N_PHRASES - 1))


def scripted_dancer(t: float) -> tuple[float, float]:
    """Where the dancer is supposed to be: (x offset from center in stage px, depth 0 front to 1 upstage)."""
    t = min(max(t, 0.0), DURATION - 1e-4)
    i = phrase_at(t)
    bl = (t - i * PH) / BEAT
    c = math.floor(bl)
    if i == 6:
        return (-150 * ease(bl / 3.4) if c < 4 else lerp(-150, 150, ease((bl - 4) / 3.4))), 0.0
    if i == 7:
        return (lerp(150, 0, ease(bl)) if c < 1 else 0.0), 0.0
    if i == 8:
        return seq([0, 0, 0, 0, -45, -45, 45, 45], bl), 0.0
    if i == 10:
        th = 2 * math.pi * bl / 8
        return -230 * math.sin(th), (1 - math.cos(th)) / 2
    if i == 14:
        return 28 * math.sin(math.pi * bl), 0.0
    return 0.0, 0.0


def _asleep(r: RobotPose, u: float):
    r.pitch = -1
    r.antL = r.antR = 1.4
    r.bob = 2 * math.sin(2 * math.pi * u / 4)


def _groove(r: RobotPose, bl: float, amt: float):
    p, sw = pulse(bl), math.sin(math.pi * bl / 2)
    r.bob += -5 * p * amt
    r.body += 0.22 * sw * amt
    r.roll += 0.08 * sw * amt
    r.antL += 0.3 * p * amt
    r.antR += 0.3 * p * amt
    r.pitch += 0.08 * p * amt


EL = [1.57, -1.57, 1.57, -1.57, 1.57, -1.57, 1.57, 1.57]
ER = [-1.57, 1.57, -1.57, 1.57, 1.57, -1.57, -1.57, 1.57]
YA = [.45, .45, -.45, -.45, .45, -.45, -.45, .45]
PA = [.35, .35, -.25, -.25, .35, .35, -.25, -.25]
YB = [0, -.45, -.45, .45, .45, -.45, -.45, .45]
PB = [0, .35, .35, -.25, .35, .35, -.25, -.25]


def raw(i: int, t: float, dancer_x: float | None = None, dancer_depth: float | None = None):
    """Poses of both robots inside phrase i at show time t (no cross-phrase blending)."""
    A, B = RobotPose(), RobotPose()
    u = t - i * PH
    bl = u / BEAT
    p = pulse(bl)
    c = math.floor(bl)
    f = bl - c
    sx, sdepth = scripted_dancer(min(max(t, i * PH), (i + 1) * PH - 1e-4))
    hx = POS["C"] + (sx if dancer_x is None else dancer_x)
    depth = sdepth if dancer_depth is None else dancer_depth

    if i == 0:
        _asleep(A, u); _asleep(B, u)
    elif i == 1:
        _asleep(B, u)
        B.antR += -0.5 * bump(bl, 2.5, 0.4); B.roll = 0.12 * bump(bl, 6.4, 0.7); B.bob += -4 * bump(bl, 6.4, 0.7)
        A.pitch = -0.55 if c >= 6 else lerp(-1, -0.3, ease((bl - 3) / 2))
        A.yaw = seq([0, 0, 0, 0, 0, -.6, .5, .73], bl); A.body = seq([0, 0, 0, 0, 0, -.9, .8, .3], bl)
        A.antL = A.antR = lerp(1.4, 0.5, ease((bl - 3) / 3))
    elif i == 2:
        A.yaw = seq([.73, .73, .73, 1, 1, 1, .73, .73], bl); A.pitch = seq([-.55, -.6, -.6, -.2, -.2, -.2, -.55, -.55], bl)
        A.roll = seq([.2, .2, .2, 0, 0, 0, .15, .15], bl)
        A.antL = 0.5
        A.antR = seq([.5, .9, .9, .4, .4, .4, .5, .5], bl) + (0.9 * math.exp(-f * 5) if c in (4, 5) else 0)
        B.pitch = -1 if c < 5 else lerp(-1, -0.55, ease((bl - 5) / 2)); B.yaw = -0.73 if c >= 7 else 0
        B.antL = B.antR = 1.4 if c < 5 else (0.45 + 0.4 * math.sin(4 * math.pi * bl) if c == 6 else 0.6)
    elif i == 3:
        for r, s in ((A, 1), (B, -1)):
            r.yaw = s * seq([.73, .73, .73, .73, 1, 1, 1, 1], bl)
            r.pitch = seq([-.6, -.7, -.8, -.8, -.4, -.4, -.4, -.4], bl) + (0.3 * p if c >= 6 else 0)
            r.antL = r.antR = seq([.8, 1, 1.2, 1.2, 1.1, 1.1, .5, .4], bl)
            r.roll = s * seq([0, 0, 0, 0, .12, .12, 0, 0], bl)
    elif i == 4:
        for r, sd in ((A, 1), (B, -1)):
            r.yaw = sd * 0.73; r.pitch = -0.15 + 0.15 * p; r.roll = sd * 0.15
            r.body = sd * 0.25 + 0.1 * math.sin(math.pi * bl / 2); r.bob = -4 * p
            if sd > 0:
                r.antR, r.antL = 1.35 - 0.25 * p, 0.3
            else:
                r.antL, r.antR = 1.35 - 0.25 * p, 0.3
    elif i == 5:
        for r, sd, lag in ((A, 1, 0), (B, -1, 1)):
            r.yaw = sd * 0.73
            b2 = bl - lag
            cheer = pulse(b2) if (2 <= b2 < 3 or 4 <= b2 < 5 or 6 <= b2 < 7) else 0
            r.pitch = 0.35 * cheer; r.bob = -9 * cheer
            r.antL = r.antR = 0.3 + 0.9 * cheer; r.roll = sd * 0.15 * cheer
    elif i == 6:
        ga = pulse(bl) if c == 3 else 0
        gb = pulse(bl) if c == 7 else 0
        for r, side, g in ((A, "A", ga), (B, "B", gb)):
            r.yaw = toward(POS[side], hx); r.body = r.yaw * 0.4; r.pitch = 0.4 * g
            r.antL = r.antR = 0.3 + 1.0 * g; r.bob = -12 * g
    elif i == 7:
        for r, sd, pop_at in ((A, 1, 2), (B, -1, 3)):
            hidden = (1 if c < pop_at else 0.6) if (c < pop_at or c in (4, 5)) else 0
            r.pitch = lerp(0.25, -0.9, hidden); r.bob = lerp(-4, 18, hidden); r.antL = r.antR = lerp(0.15, 1.3, hidden)
            r.roll = sd * 0.35 if c == pop_at else 0
            r.yaw = sd * 0.73
            if c == 6:
                r.pitch, r.bob, r.roll = 0.4, -10, sd * 0.2; r.antL = r.antR = 1.0
            if c == 7:
                w = math.sin(6 * math.pi * bl)
                r.roll = 0.22 * w; r.bob = -6 * abs(w); r.antL = r.antR = 0.5 + 0.4 * w; r.pitch = 0.2
    elif i == 8:
        for r, side in ((A, "A"), (B, "B")):
            r.yaw = toward(POS[side], hx)
            if c == 1:
                r.pitch, r.bob = 0.5, -8; r.antL = r.antR = 1.3
            elif c >= 2:
                r.pitch = 0.05 + 0.35 * p; r.antL = r.antR = 0.2 + 0.6 * p; r.bob = -3 * p
                mine = (side == "A" and c in (4, 5)) or (side == "B" and c in (6, 7))
                if mine:
                    r.roll = 0.2 if side == "A" else -0.2
                    r.antL = r.antR = 0.2 + 0.9 * p
    elif i == 9:
        for r, s, ofs in ((A, 1, 0), (B, -1, 1)):
            pp = p if (c >= 4 or c % 2 == ofs) else 0
            r.pitch = -0.45 * pp; r.bob = 6 * pp; r.yaw = s * 0.5
            r.antL = 0.2 + 0.9 * pp * (1 if c % 2 else 0.3)
            r.antR = 0.2 + 0.9 * pp * (0.3 if c % 2 else 1)
    elif i == 10:
        for r, side in ((A, "A"), (B, "B")):
            r.yaw = toward(POS[side], hx); r.body = 0.7 * r.yaw
            r.antL = r.antR = 0.25 + 0.5 * p; r.pitch = 0.1 * p - 0.1 * depth
    elif i == 11:
        for r, s in ((A, 1), (B, -1)):
            if c < 4:
                r.roll = 0.3 * math.sin(math.pi * bl); r.pitch = 0.3 * math.cos(math.pi * bl); r.yaw = s * 0.2
            else:
                out, back = ease((bl - 4) / 2), ease((bl - 6) / 0.6)
                r.turn = s * 2.8 * out * (1 - back)
                r.antL = r.antR = 1.2 if c == 7 else 0.4
                r.pitch = 0.3 if c == 7 else 0
    elif i in (12, 13) or (i == 17 and c < 4):
        cl = math.cos(math.pi * bl)
        lift_l, lift_r = max(0.0, cl) ** 1.5, max(0.0, -cl) ** 1.5
        for r, s in ((A, 1), (B, -1)):
            r.pitch = 0.5 * p - 0.1; r.bob = -9 * p
            r.antL = 0.1 + 1.15 * lift_l; r.antR = 0.1 + 1.15 * lift_r; r.yaw = s * 0.35
            if i == 12:
                r.turn = s * 0.7 * math.sin(math.pi * bl / 4)
            if i == 13:
                r.yaw = s * 0.3 + 0.5 * math.sin(math.pi * bl / 2)
                r.pitch = 0.3 * math.sin(math.pi * bl) + 0.3 * p
                r.roll = 0.22 * math.sin(3 * math.pi * bl / 4)
                r.body = 0.5 * math.sin(2 * math.pi * bl / 8) * s
    elif i == 14:
        for r, sd, pop_at in ((A, 1, 4), (B, -1, 5)):
            w = 2 * math.pi * bl / 2 + (0 if sd > 0 else math.pi)
            r.antL = 0.7 + 0.6 * math.sin(w); r.antR = 0.7 + 0.6 * math.sin(w + math.pi); r.yaw = sd * 0.35
            if 2 <= c < 4:
                r.roll = 0.18 * math.sin(4 * math.pi * bl)
            if c == pop_at:
                pp = pulse(bl)
                r.pitch = 0.45 * pp + 0.1; r.bob = -12 * pp; r.antL = r.antR = 0.2 + 1.1 * pp; r.yaw = sd * 0.73
            if c >= 6:
                r.antL = r.antR = 0.05; r.roll = 0.18 if c == 6 else -0.18; r.pitch = 0.25; r.yaw = sd * 0.4
    elif i in (15, 17):
        for r, s, yy, pp in ((A, 1, YA, PA), (B, -1, YB if i == 15 else YA, PB if i == 15 else PA)):
            r.yaw = s * 0.25 + seq(yy, bl); r.pitch = seq(pp, bl); r.body = 0.35 * seq(yy, bl)
            r.antL = seq([.1 if v > 0 else 1.25 for v in EL], bl)
            r.antR = seq([.1 if v > 0 else 1.25 for v in ER], bl)
            r.bob = -4 * p
    elif i == 16:
        w = bl / 4 if c < 4 else 1 - (bl - 4) / 4

        def g(c0, s=0.07):
            return math.exp(-((w - c0) / s) ** 2)
        A.antL = 0.25 + 1.1 * g(.04); A.antR = 0.25 + 1.1 * g(.14); A.roll = 0.3 * g(.09); A.pitch = 0.35 * g(.09); A.bob = -10 * g(.09)
        B.antL = 0.25 + 1.1 * g(.86); B.antR = 0.25 + 1.1 * g(.96); B.roll = -0.3 * g(.91); B.pitch = 0.35 * g(.91); B.bob = -10 * g(.91)
        xw = lerp(250, 1350, w)
        A.yaw = toward(POS["A"], xw); B.yaw = toward(POS["B"], xw); A.body = A.yaw * 0.4; B.body = B.yaw * 0.4
    else:
        for r, s in ((A, 1), (B, -1)):
            if c < 4:
                w = math.sin(4 * math.pi * bl)
                r.antL = 0.6 + 0.5 * w; r.antR = 0.6 - 0.5 * w; r.bob = -10 * p; r.pitch = 0.1 + 0.35 * p
                r.yaw = s * 0.3; r.turn = s * 0.5 * math.sin(math.pi * bl)
            else:
                k = ease((bl - 4) / 1)
                r.yaw = s * lerp(0.3, 0.73, k); r.pitch = lerp(0.1, 0.35, k); r.roll = s * 0.22 * k
                r.antL = r.antR = lerp(0.6, 0.05, k)

    amt = 0.45 if 4 <= i <= 7 else (1.0 if i >= 8 else 0.0)
    still = (i == 11 and c >= 4) or (i == 18 and c >= 4) or i == 16 or (i == 7 and c == 7)
    if amt > 0 and not still:
        _groove(A, bl, amt); _groove(B, bl, amt)
    return {"A": A, "B": B}


def robot_poses(t: float, dancer_x: float | None = None, dancer_depth: float | None = None):
    """Both robots' poses at show time t, blending smoothly into each new phrase."""
    if t < 0:
        return raw(0, 0.0)
    t = min(t, DURATION - 1e-4)
    i = phrase_at(t)
    cur = raw(i, t, dancer_x, dancer_depth)
    d = t - i * PH
    if i > 0 and d < BLEND_S:
        prev = raw(i - 1, i * PH - 1e-4, dancer_x, dancer_depth)
        k = ease(d / BLEND_S)
        return {s: mix(prev[s], cur[s], k) for s in ("A", "B")}
    return cur


def robot_pose(side: str, t: float, dancer_x: float | None = None, dancer_depth: float | None = None) -> RobotPose:
    return robot_poses(t, dancer_x, dancer_depth)[side]
