"""Export Encendido's move pieces as the first set of Reachoreo's movement database.

    .venv/bin/python tools/export_moveset.py moves/encendido/moveset.json

Writes a "reachoreo.moveset/1" file (see docs/reachoreo-architecture.md). The generator still reads Encendido
directly today; this file is the data form that new styles will share.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from reachy_dance.choreography import library  # noqa: E402


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "moves/encendido/moveset.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    meta = {"moves": library.MOVES, "you_halves": getattr(library, "YOU_HALVES", [])}
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "moves_meta.json"
        p.write_text(json.dumps(meta, default=str))
        subprocess.run(["node", "--no-warnings", str(ROOT / "tools/bake_moveset.mjs"), str(p), str(out)], check=True, cwd=ROOT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
