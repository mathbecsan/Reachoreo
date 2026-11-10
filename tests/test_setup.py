"""The setup wizard's back end: editing show.yaml safely, swapping robots, fixing directions, readiness."""
import shutil
from pathlib import Path

import pytest
import yaml

from reachy_dance.dashboard import setup as S
from reachy_dance.pose import Calibration, RobotPose, to_sdk

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def cfgfile(tmp_path):
    p = tmp_path / "show.yaml"
    shutil.copy(ROOT / "config" / "show.yaml", p)
    return p


def test_write_key_changes_only_the_value(cfgfile):
    before = cfgfile.read_text()
    S.write_key(cfgfile, "robots", "B", "latency_s", 0.25)
    after = cfgfile.read_text()
    changed = [(a, b) for a, b in zip(before.splitlines(), after.splitlines()) if a != b]
    assert len(changed) == 1 and "latency_s: 0.25" in changed[0][1] and "#" in changed[0][1]   # comment kept
    assert yaml.safe_load(after)["robots"]["B"]["latency_s"] == 0.25
    assert yaml.safe_load(after)["robots"]["A"]["latency_s"] == yaml.safe_load(before)["robots"]["A"]["latency_s"]


def test_write_key_adds_a_missing_key(cfgfile):
    S.write_key(cfgfile, "calibration", None, "ant_swap", True)
    assert yaml.safe_load(cfgfile.read_text())["calibration"]["ant_swap"] is True


def test_swap_moves_everything_that_belongs_to_the_robot(cfgfile):
    cfg = yaml.safe_load(cfgfile.read_text())
    a0, b0 = dict(cfg["robots"]["A"]), dict(cfg["robots"]["B"])
    S.swap(cfg, cfgfile)
    new = yaml.safe_load(cfgfile.read_text())["robots"]
    for k in ("port", "serial", "latency_s"):
        assert new["A"][k] == b0[k] and new["B"][k] == a0[k]


def test_flips_fix_each_wrong_answer(cfgfile):
    cfg = yaml.safe_load(cfgfile.read_text())
    y0 = cfg["calibration"]["yaw_left_sign"]
    assert S.flip(cfg, cfgfile, "turn") == {"yaw_left_sign": -y0}
    assert S.flip(cfg, cfgfile, "antenna_side") == {"ant_swap": True}
    saved = yaml.safe_load(cfgfile.read_text())["calibration"]
    assert saved["yaw_left_sign"] == -y0 and saved["ant_swap"] is True


def test_antenna_swap_sends_the_left_antenna_to_the_other_motor():
    p = RobotPose(antL=1.2, antR=0.1)
    normal, swapped = to_sdk(p, Calibration()), to_sdk(p, Calibration(ant_swap=True))
    assert normal.antennas_rad[0] == pytest.approx(1.2) and abs(swapped.antennas_rad[1]) == pytest.approx(1.2)


def test_readiness_lists_what_is_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "SETUP_FILE", tmp_path / "setup.json")
    cfg = yaml.safe_load((ROOT / "config" / "show.yaml").read_text())
    r = S.readiness(cfg, lambda k: True, [])
    assert not r["ready"] and {c["key"] for c in r["checks"] if not c["ok"]} == {"paired", "directions", "timing", "cameras"}
    for step in ("paired", "directions", "timing", "cameras"):
        S.mark(step)
    assert S.readiness(cfg, lambda k: True, [])["ready"]
    assert not S.readiness(cfg, lambda k: k != "B", [])["ready"]          # a robot went offline
