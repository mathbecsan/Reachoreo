from reachy_dance.perception.features import FeatureTracker, L_SH, R_SH, L_WR, R_WR, L_HIP, R_HIP, NOSE


def body(over=None):
    lm = [(0.5, 0.5)] * 33
    pts = {NOSE: (0.5, 0.2), L_SH: (0.56, 0.32), R_SH: (0.44, 0.32), L_HIP: (0.54, 0.55), R_HIP: (0.46, 0.55),
           L_WR: (0.58, 0.6), R_WR: (0.42, 0.6)}
    pts.update(over or {})
    lm = list(lm)
    for k, v in pts.items():
        lm[k] = v
    return lm


def test_center_and_arm_out_toward_camera_left():
    f = FeatureTracker()
    s, ev = f.update(body(), 0.0)
    assert abs(s["x"]) < 1e-6 and ev == []
    s, ev = f.update(body({R_WR: (0.25, 0.33)}), 0.1)
    assert any(e["type"] == "arm_out" and e["side"] == "A" for e in ev)


def test_hands_open_after_covering_face():
    f = FeatureTracker()
    face = {L_WR: (0.52, 0.22), R_WR: (0.48, 0.22)}
    f.update(body(face), 0.0)
    f.update(body(face), 0.4)
    _, ev = f.update(body(), 0.5)
    assert any(e["type"] == "hands_open" for e in ev)


# ---- close-up (upper body) framing: shoulders fill ~40% of the frame, hips are off-frame ----
from reachy_dance.perception.features import L_EL, R_EL


def closeup(over=None):
    lm = [(0.5, 1.4)] * 33                       # unseen points guessed below the frame
    pts = {NOSE: (0.5, 0.35), L_SH: (0.7, 0.75), R_SH: (0.3, 0.75), L_EL: (0.78, 1.05), R_EL: (0.22, 1.05),
           L_WR: (0.72, 1.3), R_WR: (0.28, 1.3)}
    pts.update(over or {})
    lm = list(lm)
    for k, v in pts.items():
        lm[k] = v
    return lm


def test_closeup_position_from_shoulders():
    f = FeatureTracker(framing="upper")
    s, _ = f.update(closeup(), 0.0)
    assert abs(s["x"]) < 1e-6
    moved = {k: (v[0] + 0.1, v[1]) for k, v in [(i, closeup()[i]) for i in (NOSE, L_SH, R_SH, L_EL, R_EL, L_WR, R_WR)]}
    s, _ = f.update(closeup(moved), 0.5)
    assert s["x"] > 80                           # moved toward the camera's right (robot B)


def test_closeup_arm_out_with_hand_out_of_frame():
    f = FeatureTracker(framing="upper")
    f.update(closeup(), 0.0)
    # right arm (camera's left side of the image) straight out: elbow level, wrist past the frame edge
    _, ev = f.update(closeup({R_EL: (0.08, 0.76), R_WR: (-0.12, 0.76)}), 0.1)
    assert any(e["type"] == "arm_out" and e["side"] == "A" for e in ev)


def test_closeup_arms_up_and_hands_open():
    f = FeatureTracker(framing="upper")
    f.update(closeup(), 0.0)
    _, ev = f.update(closeup({L_EL: (0.75, 0.45), R_EL: (0.25, 0.45), L_WR: (0.7, 0.1), R_WR: (0.3, 0.1)}), 0.1)
    assert any(e["type"] == "arms_up" for e in ev)
    face = {L_WR: (0.56, 0.36), R_WR: (0.44, 0.36), L_EL: (0.7, 0.8), R_EL: (0.3, 0.8)}
    f.update(closeup(face), 1.0)
    f.update(closeup(face), 1.4)
    _, ev = f.update(closeup(), 1.5)
    assert any(e["type"] == "hands_open" for e in ev)


def test_closeup_resting_arms_fire_nothing():
    f = FeatureTracker(framing="upper")
    evs = [f.update(closeup(), t / 30)[1] for t in range(30)]
    assert not any(evs)
