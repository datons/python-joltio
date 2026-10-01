"""Carga del esquema OpenAPI del que se autogenera el árbol de comandos.

Orden de resolución:
1. Copia refrescada en `~/.config/joltio/openapi.json` (la escribe `joltio self sync-spec`), si existe.
2. Copia empaquetada con la CLI (`data/openapi.json`), generada por `backend/scripts/dump_openapi.py`.

Así el instalable trae comandos listos y buen `--help`/autocompletado sin red, y `self sync-spec` permite alinearlo con el backend concreto del workspace cuando difieran.
"""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
from typing import Any

from joltio_toolkit.config import config_dir

CACHED_SPEC = "openapi.json"
DATA_SPEC = "data-api-openapi.json"


def cached_spec_path() -> Path:
    return config_dir() / CACHED_SPEC


def bundled_spec() -> dict[str, Any]:
    with resources.files("joltio_toolkit.data").joinpath(CACHED_SPEC).open(encoding="utf-8") as handle:
        return json.load(handle)


def bundled_data_spec() -> dict[str, Any]:
    with resources.files("joltio_toolkit.data").joinpath(DATA_SPEC).open(encoding="utf-8") as handle:
        return json.load(handle)


def load_data_spec() -> dict[str, Any]:
    cached = config_dir() / DATA_SPEC
    if cached.exists():
        try:
            return json.loads(cached.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return bundled_data_spec()


def load_spec() -> dict[str, Any]:
    cached = cached_spec_path()
    if cached.exists():
        try:
            return json.loads(cached.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return bundled_spec()


def store_cached_spec(spec: dict[str, Any]) -> Path:
    path = cached_spec_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(spec, indent=2, ensure_ascii=False), encoding="utf-8")
    return path
