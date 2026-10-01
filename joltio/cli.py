"""Entrada pública de la CLI unificada; conserva joltio.cli.main de 0.1.0."""

import sys

from joltio_toolkit.__main__ import app


def _compat_args(args: list[str]) -> list[str]:
    if len(args) >= 2 and args[0] == "data" and args[1] in {"search", "coverage", "metadata"}:
        if args[1] == "search" and len(args) > 2 and args[2] in {"facets", "--help"}:
            return args
        if args[1] == "coverage" and len(args) > 2 and args[2] in {"list", "--help"}:
            return args
        old = args[1]
        print(f"Aviso: `joltio data {old}` es un alias de compatibilidad.", file=sys.stderr)
        return ["data", f"legacy-{old}", *args[2:]]
    return args


def main(argv: list[str] | None = None) -> None:
    original = sys.argv
    sys.argv = [original[0], *_compat_args(list(argv) if argv is not None else original[1:])]
    try:
        app()
    finally:
        sys.argv = original
