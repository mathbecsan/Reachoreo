from reachy_dance.clock import now
from reachy_dance.config import load_choreography
from reachy_dance.reactive import Reactor

score, sheet = load_choreography("encendido")


def t_at(phrase, count):
    """Show time of a page count (1-based) in a page phrase number (1-based)."""
    return (phrase - 1) * score.PH + (count - 1) * score.BEAT


def make(side="A"):
    return Reactor(side, score, sheet)


def test_no_dancer_means_pure_score():
    r = make()
    t = t_at(13, 3)
    base = score.robot_pose("A", t)
    assert r.apply(base, t) == base


def test_hands_open_in_window_triggers_pop_for_both():
    for side in "AB":
        r = make(side)
        t = t_at(8, 7)
        r.on_dancer({"seen": True, "x": 0, "events": [{"type": "hands_open", "show_t": t, "id": "e1"}]}, t)
        base = score.robot_pose(side, t + 0.05)
        assert r.apply(base, t + 0.05).pitch > base.pitch + 0.2


def test_event_outside_window_is_ignored():
    r = make()
    t = t_at(8, 2)
    r.on_dancer({"seen": True, "x": 0, "events": [{"type": "hands_open", "show_t": t, "id": "e2"}]}, t)
    assert r.impulses == []


def test_arm_out_only_wakes_the_robot_it_points_at():
    a, b = make("A"), make("B")
    t = t_at(15, 5)
    ev = {"seen": True, "x": 0, "events": [{"type": "arm_out", "side": "A", "show_t": t, "id": "e3"}]}
    a.on_dancer(ev, t); b.on_dancer(ev, t)
    assert len(a.impulses) == 1 and b.impulses == []


def test_echo_answers_one_beat_later():
    a, b = make("A"), make("B")
    t = t_at(15, 5)
    a.on_dancer({"seen": True, "x": 0, "events": [{"type": "arm_out", "side": "A", "show_t": t, "id": "e4"}]}, t)
    b.on_peer({"reactions": list(a.fired)}, t)
    assert len(b.impulses) == 1
    assert abs(b.impulses[0].start - (t + score.BEAT)) < 1e-9 and b.impulses[0].amp == 0.5


def test_tracking_follows_live_dancer_and_falls_back_when_lost():
    r = make()
    t = t_at(11, 3)
    r.on_dancer({"seen": True, "x": 200, "depth": 0.2, "events": []}, t, rx=now())
    x, _ = r.score_inputs(t)
    assert abs(x - 200) < 1
    r.on_dancer({"seen": True, "x": 200, "depth": 0.2, "events": []}, t, rx=now() - 5)
    assert r.score_inputs(t) == (None, None)


def test_no_echo_when_both_robots_already_reacted():
    a, b = make("A"), make("B")
    t = t_at(8, 7)
    ev = {"seen": True, "x": 0, "events": [{"type": "hands_open", "show_t": t, "id": "e5"}]}
    a.on_dancer(ev, t); b.on_dancer(ev, t)
    b.on_peer({"reactions": list(a.fired)}, t)
    assert len(b.impulses) == 1


def test_own_reaction_replaces_a_coinciding_echo():
    a, b = make("A"), make("B")
    t = t_at(15, 5)
    a.on_dancer({"seen": True, "x": 0, "events": [{"type": "arm_out", "side": "A", "show_t": t, "id": "e6"}]}, t)
    b.on_peer({"reactions": list(a.fired)}, t)
    t2 = t + score.BEAT
    b.on_dancer({"seen": True, "x": 0, "events": [{"type": "arm_out", "side": "B", "show_t": t2, "id": "e7"}]}, t2)
    assert [i.source for i in b.impulses] == ["dancer"]


def test_rehearsing_a_section_again_reacts_again():
    r = make("A")
    t = t_at(6, 3)
    r.on_dancer({"seen": True, "x": 0, "events": [{"type": "arm_out", "side": "A", "show_t": t + 0.2, "id": "run1"}]}, t)
    assert len(r.impulses) == 1
    r.reset()                                   # the conductor restarted the same section
    r.on_dancer({"seen": True, "x": 0, "events": [{"type": "arm_out", "side": "A", "show_t": t + 0.05, "id": "run2"}]}, t)
    assert len(r.impulses) == 1 and r.impulses[0].id == "A-run2"


def test_slightly_early_cue_still_counts_but_not_a_whole_beat_early():
    r = make("A")
    t = t_at(6, 3)
    r.on_dancer({"seen": True, "x": 0, "events": [{"type": "arm_out", "side": "A", "show_t": t - 0.05, "id": "early"}]}, t)
    assert len(r.impulses) == 1
    r2 = make("A")
    r2.on_dancer({"seen": True, "x": 0, "events": [{"type": "arm_out", "side": "A", "show_t": t - 0.4, "id": "tooearly"}]}, t)
    assert r2.impulses == []


def test_early_cue_counts_for_the_next_phrase_first_count():
    r = make("A")
    t = t_at(9, 1) - 0.02                      # arms up 20 ms before phrase 9 starts
    r.on_dancer({"seen": True, "x": 0, "events": [{"type": "arms_up", "show_t": t, "id": "edge"}]}, t)
    assert [i.action for i in r.impulses] == ["recoil"]
