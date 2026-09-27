"""Configuration file management for Joltio CLI.

Reads and writes API keys to ~/.config/joltio/config.toml.
"""

from __future__ import annotations

import os
from pathlib import Path

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "joltio"
CONFIG_FILE = CONFIG_DIR / "config.toml"


def _parse_toml(text: str) -> dict[str, dict[str, str]]:
    """Minimal TOML parser — handles [section] and key = "value" pairs."""
    result: dict[str, dict[str, str]] = {}
    current_section: str | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            current_section = stripped[1:-1].strip()
            result.setdefault(current_section, {})
        elif "=" in stripped and current_section is not None:
            key, _, value = stripped.partition("=")
            value = value.strip().strip('"').strip("'")
            result[current_section][key.strip()] = value
    return result


def _write_toml(data: dict[str, dict[str, str]]) -> str:
    """Serialize a dict of sections to minimal TOML."""
    lines: list[str] = []
    for section, entries in data.items():
        lines.append(f"[{section}]")
        for key, value in entries.items():
            lines.append(f'{key} = "{value}"')
        lines.append("")
    return "\n".join(lines)


def read_api_key() -> str | None:
    """Read the API key from the config file, or None if not set."""
    if not CONFIG_FILE.exists():
        return None
    try:
        text = CONFIG_FILE.read_text(encoding="utf-8")
    except OSError:
        return None
    data = _parse_toml(text)
    return data.get("auth", {}).get("api_key") or None


def write_api_key(api_key: str) -> None:
    """Write the API key to the config file, preserving other sections."""
    data: dict[str, dict[str, str]] = {}
    if CONFIG_FILE.exists():
        try:
            text = CONFIG_FILE.read_text(encoding="utf-8")
            data = _parse_toml(text)
        except OSError:
            pass
    data.setdefault("auth", {})
    data["auth"]["api_key"] = api_key

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(_write_toml(data), encoding="utf-8")
    CONFIG_FILE.chmod(0o600)


def remove_api_key() -> bool:
    """Remove the API key from the config file. Returns True if it existed."""
    if not CONFIG_FILE.exists():
        return False
    try:
        text = CONFIG_FILE.read_text(encoding="utf-8")
    except OSError:
        return False
    data = _parse_toml(text)
    if "auth" not in data or "api_key" not in data["auth"]:
        return False
    del data["auth"]["api_key"]
    if not data["auth"]:
        del data["auth"]
    if data:
        CONFIG_FILE.write_text(_write_toml(data), encoding="utf-8")
    else:
        CONFIG_FILE.unlink(missing_ok=True)
    return True
