"""The dashboard's stage module is generated from the preview; it must reproduce the preview's robot motion."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
MODULE = ROOT / "reachy_dance" / "dashboard" / "static" / "encendido-stage.mjs"
GOLDEN = ROOT / "tests" / "golden" / "encendido_robots.json"

CHECK = """
const m = await import(process.argv[1]);
const g = JSON.parse(require('fs').readFileSync(process.argv[2], 'utf8'));
let worst = 0;
for (let i = 0; i < g.A.length; i += 5) {
  const S = m.poseAt(i * g.step);
  for (const [side, key] of [["A", "L"], ["B", "R"]]) g.keys.forEach((k, j) => { worst = Math.max(worst, Math.abs(S[key][k] - g[side][i][j])); });
}
console.log(worst);
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_stage_module_matches_golden_robot_motion():
    script = "const require = (await import('module')).createRequire(import.meta.url);" + CHECK
    out = subprocess.run(["node", "--input-type=module", "-e", script, str(MODULE), str(GOLDEN)],
                         capture_output=True, text=True, check=True)
    assert float(out.stdout.strip()) < 1e-4


def test_stage_module_is_up_to_date_with_the_preview():
    preview = (ROOT / "preview" / "encendido-preview.html").read_text()
    body = MODULE.read_text()
    assert "function raw(i, t)" in body and preview[preview.index("function raw(i, t)"):preview.index("function mix(a, b, k)")] in body
