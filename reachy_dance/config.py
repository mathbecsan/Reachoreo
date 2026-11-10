"""Loads config/show.yaml and the choreography's phrase sheet."""
from __future__ import annotations

import importlib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def load_config(path: str | Path | None = None) -> dict:
    path = Path(path) if path else ROOT / "config" / "show.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


def load_choreography(name: str):
    """Returns (score, phrase_sheet_dict). `name` is a score module (encendido) or a song in library/."""
    from .choreography import library
    if name != "encendido" and library.exists(name):
        base = load_choreography("encendido")[1]
        ch = library.load(name)
        return library.GeneratedScore(ch), library.build_sheet(ch, base)
    module = importlib.import_module(f"reachy_dance.choreography.{name}")
    sheet_path = Path(module.__file__).with_suffix(".yaml")
    with open(sheet_path) as f:
        sheet = yaml.safe_load(f)
    if len(sheet["phrases"]) != module.N_PHRASES:
        raise ValueError(f"{sheet_path.name} lists {len(sheet['phrases'])} phrases, score has {module.N_PHRASES}")
    for i, ph in enumerate(sheet["phrases"]):          # the same robot descriptions the generated dances show
        ph.setdefault("robots", {"A": library.MOVES[i]["A"], "B": library.MOVES[i]["B"]})
    return module, sheet


def choreography_name(score) -> str:
    return getattr(score, "name", None) or score.__name__.rsplit(".", 1)[-1]


def endpoint(cfg: dict, name: str, bind: bool = False) -> str:
    host = "*" if bind else cfg["bus"]["host"]
    return f"tcp://{host}:{cfg['bus'][name]}"
