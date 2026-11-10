import random

from reachy_dance import clock as C


def test_follower_ignores_network_delay():
    rng = random.Random(0)
    f = C.ClockFollower()
    true_offset = 123.456          # conductor show time minus our monotonic time
    for k in range(200):
        rx = 1000.0 + k * 0.01
        delay = rng.uniform(0.001, 0.04)
        f.on_message({"state": C.PLAYING, "show_t": (rx - delay) + true_offset, "bpm": 120}, rx_time=rx)
    estimate = f.show_time(at=1002.0) - 1002.0
    assert abs(estimate - true_offset) < 0.005


def test_pause_holds_time():
    f = C.ClockFollower()
    f.on_message({"state": C.PAUSED, "show_t": 12.5, "bpm": 120}, rx_time=5.0)
    assert f.show_time(at=50.0) == 12.5


def test_show_clock_countdown_becomes_playing():
    c = C.ShowClock()
    c.start(-0.001)
    import time
    time.sleep(0.01)
    assert c.show_time() > 0 and c.state == C.PLAYING
