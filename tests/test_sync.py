"""Perform-view scoring: physical lag, run grading, and the camera bridge's use of the feature tracker."""
import math

from reachy_dance.config import load_choreography
from reachy_dance.dashboard.monitor import Monitor
from reachy_dance.dashboard.sync import Run, Trace, aim_error_deg, estimate_lag

score, sheet = load_choreography("encendido")


def t_at(phrase, count):
    return (phrase - 1) * score.PH + (count - 1) * score.BEAT


def test_lag_is_recovered_from_a_delayed_follower():
    tr = Trace()
    f = lambda t: [20 * math.sin(2 * math.pi * 0.8 * t), 8 * math.sin(2 * math.pi * 1.3 * t), 0, 0, 0, 0, 0]
    for i in range(100):                       # 25 Hz for 4 s, robot 120 ms behind its commands
        t = i * 0.04
        tr.add(t, f(t), f(t - 0.12))
    out = estimate_lag(tr)
    assert out["moving"] and abs(out["lag_ms"] - 120) <= 10 and out["err_deg"] < 0.5


def test_lag_is_unknown_when_still():
    tr = Trace()
    for i in range(100):
        tr.add(i * 0.04, [1, 0, 0, 0, 0, 0, 0], [1, 0, 0, 0, 0, 0, 0])
    assert estimate_lag(tr)["lag_ms"] is None


def test_aim_error_zero_when_looking_at_dancer():
    # robot A at stage x 360 looking at a dancer 150 px right of center (x 950): toward = (950-360)/600
    target = score.toward(score.POS["A"], score.POS["C"] + 150) * 40
    assert aim_error_deg(score, "A", [target, 0, 0, 0, 0, 0, 0], 150) == 0


def test_run_grades_cues_and_robot_answers():
    run = Run(score, sheet, start_t=t_at(6, 1), end_t=t_at(10, 1), started_rx=0.0)
    assert [(e["phrase"], e["count"], e["type"]) for e in run.expected()] == \
        [(6, 3, "arm_out"), (6, 5, "arm_out"), (8, 7, "hands_open"), (9, 1, "arms_up")]
    # dancer: arm toward A 80 ms late, misses the arm toward B, hands open 300 ms early
    run.cues += [{"id": "c1", "type": "arm_out", "side": "A", "show_t": t_at(6, 3) + 0.08, "rx": 10.0},
                 {"id": "c2", "type": "hands_open", "show_t": t_at(8, 7) - 0.3, "rx": 20.0}]
    reactions = {"A": {"A-c1": {"rx": 10.05}, "A-c2": {"rx": 20.04}}, "B": {"B-c2": {"rx": 20.06}}}
    rows = run.grade(t_at(9, 1) + 1.0, reactions)
    r = {(x["phrase"], x["count"]): x for x in rows}
    assert r[6, 3]["status"] == "on beat" and r[6, 3]["offset_ms"] == 80
    assert r[6, 3]["robots"] == {"A": 50}                 # "mine": only the robot pointed at should answer
    assert r[6, 5]["status"] == "missed"
    assert r[8, 7]["status"] == "early" and r[8, 7]["robots"] == {"A": 40, "B": 60}
    assert r[9, 1]["status"] == "missed"
    sm = run.summary(t_at(9, 1) + 1.0, reactions)
    assert (sm["cues_hit"], sm["cues_total"], sm["answers_given"], sm["answers_expected"]) == (2, 4, 3, 3)


def test_echo_counts_as_an_answer():
    run = Run(score, sheet, start_t=t_at(15, 1), end_t=t_at(16, 1), started_rx=0.0)
    run.cues.append({"id": "c9", "type": "arm_out", "side": "A", "show_t": t_at(15, 5), "rx": 5.0})
    reactions = {"A": {"A-c9": {"rx": 5.03}}, "B": {"B-echo-A-c9": {"rx": 5.55}}}
    row = run.grade(t_at(16, 1), reactions)[0]
    assert row["robots"] == {"A": 30, "B": 550}            # phrase 15 echoes: B answers a beat later


def test_monitor_starts_and_summarizes_runs():
    m = Monitor(score, sheet)
    m.ingest("clock", {"state": "idle", "show_t": 0.0}, 1.0)
    m.ingest("clock", {"state": "countdown", "show_t": t_at(6, 1) - 4, "start_t": t_at(6, 1), "end_t": t_at(10, 1)}, 2.0)
    assert m.run and m.run.start_t == t_at(6, 1)
    m.ingest("dancer", {"seen": True, "x": 0, "events": [{"type": "arms_up", "show_t": t_at(9, 1), "id": "u1"}]}, 3.0)
    assert m.run.cues[0]["id"] == "u1"
    m.ingest("clock", {"state": "ended", "show_t": t_at(10, 1)}, 30.0)
    assert m.run.finished and m.runs[-1]["cues_hit"] == 1
    assert any(e["kind"] == "summary" for e in m.log)


def test_beat_offset_from_show_and_clock_times():
    from reachy_dance.dashboard.sync import estimate_beat_offset
    tr = Trace()
    f = lambda t: [20 * math.sin(2 * math.pi * 0.8 * t), 8 * math.sin(2 * math.pi * 1.3 * t), 0, 0, 0, 0, 0]
    for i in range(100):
        clock = 10 + i * 0.04
        # the agent sends the pose for 60 ms ahead (latency_s); the head lands 170 ms after sending: 110 ms late
        tr.add(clock, f(clock + 0.06), f(clock - 0.11), show_t=clock + 0.06, clock_t=clock)
    assert abs(estimate_beat_offset(tr) - 110) <= 10


def test_dancer_metrics_feed_the_run():
    m = Monitor(score, sheet)
    m.ingest("clock", {"state": "idle", "show_t": 0.0}, 1.0)
    m.ingest("clock", {"state": "playing", "show_t": t_at(6, 1), "start_t": t_at(6, 1), "end_t": t_at(10, 1)}, 2.0)
    m.on_me({"match": 0.8, "offset_ms": 120, "fresh": True}, 2.1)
    m.on_me({"match": 0.6, "offset_ms": 80, "fresh": True}, 2.2)
    m.run.beats["A"] = [100]
    sm = m.run.summary(t_at(10, 1), m.reactions)
    assert sm["me_match"] == 0.7 and sm["me_offset_ms"] == 120 and sm["robots_vs_me_ms"]["A"] == 20
