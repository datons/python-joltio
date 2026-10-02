from __future__ import annotations

import base64
import hashlib
import io
import json
import time
import zipfile
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from joltio import Client, config
from joltio.client import user_agent
from joltio_toolkit.custom import artifacts, data
from joltio_toolkit.http import CliError


def _jwt(exp: float) -> str:
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).rstrip(b"=").decode()
    return f"header.{payload}.signature"


def test_credential_order_and_toml_compatibility(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("JOLTIO_API_KEY", raising=False)
    monkeypatch.delenv("JOLTIO_TOKEN", raising=False)
    monkeypatch.delenv("DATONS_API_KEY", raising=False)
    config.write_api_key("jol_saved")
    config.store_session(token=_jwt(time.time() + 600), refresh_token="refresh", base_url="https://joltio.app", api_url="https://joltio.app")
    assert config.credential_headers() == {"X-API-Key": "jol_saved"}
    monkeypatch.setenv("JOLTIO_TOKEN", "jwt_env")
    assert config.credential_headers() == {"Authorization": "Bearer jwt_env"}
    monkeypatch.setenv("JOLTIO_API_KEY", "jol_env")
    assert config.credential_headers() == {"X-API-Key": "jol_env"}
    with Client(api_key="jol_explicit") as client:
        assert client._http.headers["X-API-Key"] == "jol_explicit"
    monkeypatch.delenv("JOLTIO_API_KEY")
    monkeypatch.delenv("JOLTIO_TOKEN")
    config.remove_api_key()
    with Client() as client:
        assert client._http.headers["Authorization"].startswith("Bearer header.")


def test_expired_session_rotates_and_preserves_workspace(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("JOLTIO_API_KEY", raising=False)
    monkeypatch.delenv("JOLTIO_TOKEN", raising=False)
    old = _jwt(time.time() - 1)
    fresh = _jwt(time.time() + 3600)
    config.store_session(token=old, refresh_token="old-refresh", base_url="https://joltio.app", api_url="https://joltio.app")
    config.store_workspace("my-workspace")
    calls = []

    def refresh(url, **kwargs):
        calls.append((url, kwargs["json"]))
        return httpx.Response(200, json={"token": fresh, "refreshToken": "new-refresh"}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", refresh)
    assert config.credential_headers() == {"Authorization": f"Bearer {fresh}"}
    assert calls == [("https://joltio.app/api/cli/refresh", {"refreshToken": "old-refresh"})]
    assert config.load_session().refresh_token == "new-refresh"
    assert config.load_session().workspace == "my-workspace"


def test_engine_download_checks_digest_before_execution(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.delenv("JOLTIO_APP_ENGINE", raising=False)
    monkeypatch.delenv("JOLTIO_ARTIFACT_CLI", raising=False)
    monkeypatch.setattr(artifacts, "_dev_source", lambda: None)
    monkeypatch.setattr(artifacts, "version", lambda name: "0.2.0")
    monkeypatch.setattr(artifacts.platform, "system", lambda: "Linux")
    monkeypatch.setattr(artifacts.platform, "machine", lambda: "x86_64")
    binary = b"verified engine"
    name = "joltio-app-engine-linux-amd64"
    checksum = hashlib.sha256(binary).hexdigest()

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.close()

    agents = []

    def download(request, **kwargs):
        # Cloudflare responde 403 (error 1010) al User-Agent de urllib: cada descarga debe identificarse como joltio.
        agents.append(request.get_header("User-agent"))
        return Response(f"{checksum}  {name}\n".encode() if request.full_url.endswith("SHA256SUMS") else binary)

    monkeypatch.setattr(artifacts.urllib.request, "urlopen", download)
    target = Path(artifacts.resolve_engine()[0])
    assert target.read_bytes() == binary
    assert agents == [user_agent(), user_agent()] and user_agent().startswith("python-joltio/")
    launched = []
    monkeypatch.setattr(artifacts.subprocess, "run", lambda argv, **kwargs: launched.append(argv) or SimpleNamespace(returncode=0))
    artifacts._delegate("init", [])
    assert launched == [[str(target), "init"]]
    target.write_bytes(b"tampered")
    with pytest.raises(CliError, match="checksum"):
        artifacts.resolve_engine()


def test_quickstart_extracts_public_bundle_unchanged(monkeypatch, tmp_path):
    buffer = io.BytesIO()
    files = {"joltio-quickstart.ipynb": b'{"nbformat":4}', ".env": b"JOLTIO_API_KEY=\n", ".env.example": b"JOLTIO_API_KEY=\n", "README.md": b"# Joltio Data\n"}
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(f"joltio-quickstart/{name}", content)
    monkeypatch.setattr(data.httpx, "get", lambda url, **kwargs: httpx.Response(200, content=buffer.getvalue(), request=httpx.Request("GET", url)))
    target = tmp_path / "q"
    data.quickstart(target)
    assert {name: (target / name).read_bytes() for name in files} == files
