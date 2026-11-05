"""Lee un campo de Vault (KV v2) con el AppRole del job y lo escribe en stdout.

Es el equivalente en Python de `ci/vault-kv.ts` (vive en toolkit/ porque es el único sitio del repo con Python) para los jobs que corren en la imagen de uv, sin Bun: misma dirección por defecto, mismo login por AppRole y mismas referencias `vault:<ruta>#<campo>`.
Uso: `export TWINE_PASSWORD="$(python3 toolkit/scripts/vault_field.py joltio/prod PYPI_TOKEN)"`. Nunca se imprime fuera de una sustitución de comando.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

ADDRESS = os.environ.get("VAULT_ADDR", "https://vault.datons.com").rstrip("/")


def call(path: str, token: str = "", payload: dict[str, str] | None = None) -> dict:
    request = urllib.request.Request(
        f"{ADDRESS}/v1/{path}",
        data=json.dumps(payload).encode() if payload else None,
        headers={"content-type": "application/json", **({"x-vault-token": token} if token else {})},
        method="POST" if payload else "GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        raise SystemExit(f"Vault {path}: HTTP {error.code}") from None


def login() -> str:
    role_id, secret_id = os.environ.get("VAULT_ROLE_ID"), os.environ.get("VAULT_SECRET_ID")
    if not role_id or not secret_id:
        raise SystemExit("VAULT_ROLE_ID and VAULT_SECRET_ID are required")
    token = (call("auth/approle/login", payload={"role_id": role_id, "secret_id": secret_id}).get("auth") or {}).get("client_token")
    if not token:
        raise SystemExit("Vault auth/approle/login: missing client token")
    return token


def field(token: str, path: str, key: str, depth: int = 0) -> str:
    if depth >= 3:
        raise SystemExit(f"Vault reference depth exceeded: {path}#{key}")
    values = (call(f"secret/data/{path}", token).get("data") or {}).get("data")
    if not values:
        raise SystemExit(f"Vault secret/data/{path}: missing data")
    value = values.get(key)
    if isinstance(value, str) and value.startswith("vault:"):
        parts = value[len("vault:"):].split("#")
        if len(parts) != 2 or not all(parts):
            raise SystemExit(f"Invalid Vault reference: {path}#{key}")
        return field(token, parts[0], parts[1], depth + 1)
    if not isinstance(value, str) or not value:
        raise SystemExit(f"Missing Vault field: {path}#{key}")
    return value


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: vault_field.py <path> <field>")
    sys.stdout.write(field(login(), sys.argv[1], sys.argv[2]))
