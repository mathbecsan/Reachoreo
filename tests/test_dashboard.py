"""Dashboard checks: fed synthetic bus messages with explicit receive times, no sockets."""
from reachy_dance.config import load_choreography
from reachy_dance.dashboard.monitor import Monitor
from reachy_dance.dashboard.server import timeline

score, sheet = load_choreography("encendido")


def t_at(phrase, count):
    return (phrase - 1) * score.PH + (count - 1) * score.BEAT


def clock(t, state="playing"):
    return {"state": state, "show_t": t, "bpm": 120, "sent": 0}


def robot(side, t, state="playing", reactions=(), **kw):
    return {"side": side, "state": state, "show_t": t, "clock_t": t, "clock_age": 0.01,
            "phrase": score.phrase_at(max(t, 0)) + 1, "reactions": list(reactions), **kw}


def feed(m, now, t, a=None, b=None, state="playing"):
    """Everyone publishes at `now`, at show time `t` (robots may be offset)."""
    m.ingest("clock", clock(t, state), now)
    m.ingest("robot.A", robot("A", t if a is None else a, state), now)
    m.ingest("robot.B", robot("B", t if b is None else b, state), now)
    m.ingest("dancer", {"seen": True, "x": 0, "events": [], "show_t": t}, now)


def keys(m, now):
    return {a["key"] for a in m.check(now)}


def test_in_step_has_no_alerts():
    m = Monitor(score, sheet)
    feed(m, 100.0, t_at(5, 3))
    assert keys(m, 100.05) == set()


def test_silent_robot_is_flagged_and_cleared():
    m = Monitor(score, sheet)
    feed(m, 100.0, t_at(5, 3))
    m.ingest("clock", clock(t_at(5, 3) + 2.0), 102.0)
    m.ingest("robot.A", robot("A", t_at(5, 3) + 2.0), 102.0)
    assert "stale:B" in keys(m, 102.0)
    feed(m, 102.5, t_at(5, 3) + 2.5)
    assert "stale:B" not in keys(m, 102.5)
    assert any(e["kind"] == "alert" and e["text"].startswith("cleared") for e in m.log)


def test_drift_between_robots():
    m = Monitor(score, sheet, drift_warn_ms=40)
    t = t_at(9, 4)
    feed(m, 100.0, t, a=t + 0.03, b=t - 0.03)
    k = keys(m, 100.0)
    assert "drift:AB" in k                      # 60 ms apart
    assert "drift:A" not in k and "drift:B" not in k   # each within 40 ms of the conductor


def test_phrase_mismatch_but_not_at_the_boundary():
    m = Monitor(score, sheet, drift_warn_ms=1e9)
    edge = t_at(6, 1)
    feed(m, 100.0, edge, a=edge - 0.05, b=edge + 0.05)       # straddling the change: tolerated
    assert "phrase:AB" not in keys(m, 100.0)
    mid = t_at(6, 4)
    m.ingest("robot.B", {**robot("B", mid), "phrase": 7}, 100.0)
    m.ingest("robot.A", robot("A", mid), 100.0)
    assert "phrase:AB" in keys(m, 100.0)


def test_state_mismatch_needs_to_persist():
    m = Monitor(score, sheet)
    t = t_at(3, 1)
    m.ingest("clock", clock(t, "paused"), 100.0)
    m.ingest("robot.A", robot("A", t, "paused"), 100.0)
    m.ingest("robot.B", robot("B", t, "playing"), 100.0)
    assert "state:B" not in keys(m, 100.1)
    m.ingest("robot.B", robot("B", t, "playing"), 100.6)
    m.ingest("clock", clock(t, "paused"), 100.6)
    m.ingest("robot.A", robot("A", t, "paused"), 100.6)
    assert "state:B" in keys(m, 100.7)


def test_one_sided_reaction_in_a_both_phrase():
    m = Monitor(score, sheet)
    t = t_at(8, 7)                                            # hands_open -> pop, side any: both should pop
    r = {"id": "A-e1", "action": "pop", "show_t": t, "source": "dancer"}
    m.ingest("clock", clock(t), 100.0)
    m.ingest("robot.A", robot("A", t, reactions=[r]), 100.0)
    m.ingest("robot.B", robot("B", t), 100.0)
    assert not any(k.startswith("one_sided") for k in keys(m, 100.1))   # still within the echo window
    feed(m, 102.0, t + 2.0)
    m.ingest("robot.A", robot("A", t + 2.0, reactions=[r]), 102.0)
    assert "one_sided:A-e1" in keys(m, 102.0)
    assert any(e["kind"] == "check" for e in m.log)


def test_answered_reaction_and_mine_only_reaction_are_fine():
    m = Monitor(score, sheet)
    t = t_at(8, 7)
    ra = {"id": "A-e1", "action": "pop", "show_t": t, "source": "dancer"}
    rb = {"id": "B-e1", "action": "pop", "show_t": t + 0.04, "source": "dancer"}
    t6 = t_at(6, 3)                                           # arm_out -> cheer, side mine, no echo: one side only
    mine = {"id": "A-arm", "action": "cheer", "show_t": t6, "source": "dancer"}
    m.ingest("robot.A", robot("A", t, reactions=[mine, ra]), 100.0)
    m.ingest("robot.B", robot("B", t, reactions=[rb]), 100.0)
    feed(m, 102.0, t + 2.0)
    assert not any(k.startswith("one_sided") for k in keys(m, 102.0))


def test_log_records_phrases_reactions_and_cues():
    m = Monitor(score, sheet)
    t = t_at(8, 7)
    m.ingest("clock", clock(t_at(8, 1)), 99.0)
    m.ingest("dancer", {"seen": True, "x": 0, "show_t": t, "events": [{"type": "hands_open", "show_t": t, "id": "c1"}]}, 100.0)
    m.ingest("dancer", {"seen": True, "x": 0, "show_t": t, "events": [{"type": "hands_open", "show_t": t, "id": "c1"}]}, 100.03)
    kinds = [e["kind"] for e in m.log]
    assert kinds.count("phrase") == 1 and kinds.count("cue") == 1
    cue = next(e for e in m.log if e["kind"] == "cue")
    assert (cue["phrase"], cue["count"]) == (8, 7)


def test_snapshot_and_timeline_shapes():
    m = Monitor(score, sheet)
    feed(m, 100.0, t_at(15, 2))
    s = m.snapshot(100.0)
    assert (s["clock"]["phrase"], s["clock"]["count"]) == (15, 2)
    assert s["robots"]["A"]["connected"] and s["dancer"]["seen"]
    tl = timeline(score, sheet)
    assert len(tl["phrases"]) == 19
    assert tl["phrases"][7]["windows"][0] == {"when": "hands_open", "action": "pop", "side": "any", "from": 6, "to": 8}
