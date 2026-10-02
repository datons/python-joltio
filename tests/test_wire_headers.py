import httpx
import pytest

import joltio.client
from joltio_toolkit import config
from joltio_toolkit.http import request


@pytest.fixture
def wire(monkeypatch):
    """Cabeceras tal como saldrían por la red: Cloudflare rechaza con 400 una petición con `Authorization` repetida."""
    sent: list[list[tuple[str, str]]] = []

    def respond(req: httpx.Request) -> httpx.Response:
        sent.append([(name.decode().lower(), value.decode()) for name, value in req.headers.raw])
        return httpx.Response(200, json=[])

    real_client = httpx.Client
    monkeypatch.setattr(joltio.client.httpx, "Client", lambda *args, **kwargs: real_client(*args, transport=httpx.MockTransport(respond), **kwargs))
    return sent


def _count(headers: list[tuple[str, str]], name: str) -> int:
    return sum(1 for key, _ in headers if key == name)


def test_session_sends_a_single_authorization_header(wire, monkeypatch, tmp_path):
    monkeypatch.delenv("JOLTIO_API_KEY", raising=False)
    monkeypatch.delenv("JOLTIO_TOKEN", raising=False)
    monkeypatch.setenv("JOLTIO_SESSION", str(tmp_path / "session.json"))
    config.store_session(token="a.b.c", base_url="https://x", api_url="https://api.x")
    config.store_workspace("beta")
    request("get", "/api/workspaces")
    assert _count(wire[-1], "authorization") == 1
    assert _count(wire[-1], "x-joltio-workspace") == 1


def test_api_key_sends_a_single_credential_header(wire, monkeypatch, tmp_path):
    monkeypatch.setenv("JOLTIO_API_KEY", "jol_live_example")
    monkeypatch.setenv("JOLTIO_SESSION", str(tmp_path / "session.json"))
    request("get", "/api/workspaces")
    assert _count(wire[-1], "authorization") + _count(wire[-1], "x-api-key") == 1
