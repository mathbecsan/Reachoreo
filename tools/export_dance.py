"""Export a dance from the app as a self-contained Reachoreo dance file, for the VR game and other players.

    .venv/bin/python tools/export_dance.py <slug> <out_dir> [--style salsa] [--tags a,b] [--difficulty 2]
                                              [--license-name "CC BY 4.0" --license-url URL --credit "..."]

Writes <out_dir>/<slug>/dance.json (schema "reachoreo.dance/1", see docs/reachoreo-architecture.md) and copies the
song file next to it. Dances made from your own songs stay personal: they have no license, so the game treats them
as "My songs" and they must never be committed or shipped.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from reachy_dance.choreography import library  # noqa: E402
from reachy_dance.config import load_choreography  # noqa: E402
from reachy_dance.dashboard.server import timeline  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slug")
    ap.add_argument("out_dir")
    ap.add_argument("--fps", type=int, default=20)
    ap.add_argument("--title")
    ap.add_argument("--artist")
    ap.add_argument("--style", default=None)
    ap.add_argument("--tags", default="")
    ap.add_argument("--difficulty", type=int, default=2)
    ap.add_argument("--license-name")
    ap.add_argument("--license-url")
    ap.add_argument("--credit")
    a = ap.parse_args()

    score, sheet = load_choreography(a.slug)
    tl = timeline(score, sheet)
    out = Path(a.out_dir) / a.slug
    out.mkdir(parents=True, exist_ok=True)

    song = library.song_file(a.slug) if a.slug != "encendido" else None
    meta = {
        "title": a.title, "artist": a.artist,
        "style": a.style or ("robot-electro" if a.slug == "encendido" else "unknown"),
        "tags": [t for t in a.tags.split(",") if t], "difficulty": a.difficulty,
        "license": {"name": a.license_name, "url": a.license_url, "credit": a.credit} if a.license_name else None,
        "songFile": "song.ogg" if song else None,   # OGG Vorbis: every Unity platform decodes it at run time
        "choreo": f"library/{a.slug}/choreo.json" if a.slug != "encendido" else "builtin:encendido",
    }
    if a.slug == "encendido" and not a.title:
        meta.update(title="Encendido", artist="Reachoreo original")

    with tempfile.TemporaryDirectory() as td:
        tl_path = Path(td) / "timeline.json"
        tl_path.write_text(json.dumps(tl))
        (Path(td) / "timeline.meta.json").write_text(json.dumps(meta))
        subprocess.run(["node", "--experimental-strip-types", "--no-warnings", str(ROOT / "tools/bake_dance.mjs"),
                        str(tl_path), str(out / "dance.json"), "--fps", str(a.fps)], check=True, cwd=ROOT)
    if song:
        # Same length as the original, so the dance's count times still land on the beats.
        if shutil.which("ffmpeg"):
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(song), "-vn", "-c:a", "vorbis",
                            "-strict", "-2", "-ac", "2", "-q:a", "5", "-ar", "44100", str(out / "song.ogg")], check=True)
            print(f"converted {Path(song).name} -> {out / 'song.ogg'}")
        else:
            raise SystemExit("ffmpeg is needed to convert the song to OGG (brew install ffmpeg)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
