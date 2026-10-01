import httpx

from joltio import Client


def test_member_credentials_and_api_paths(monkeypatch):
    monkeypatch.setenv('JOLTIO_API_KEY', 'jol_live_test')
    calls = []
    def respond(request):
        calls.append(request)
        return httpx.Response(200, json={'columns': [{'name': 'count', 'type': 'UInt64'}], 'rows': [[2]], 'row_count': 1, 'query_type': 'aggregated', 'max_rows_applied': 50, 'truncated': False})
    with Client() as client:
        client._http.close()
        client._http = httpx.Client(base_url=client.base_url, transport=httpx.MockTransport(respond), headers={'X-API-Key': client.token, 'User-Agent': 'python-joltio/0.1.0'})
        assert client.data.query('SELECT count()').to_dicts() == [{'count': 2}]
        assert calls[0].url == 'https://api.joltio.app/data/query'
        assert calls[0].headers['X-API-Key'] == 'jol_live_test'
        assert calls[0].headers['User-Agent'] == 'python-joltio/0.1.0'

def test_legacy_environment(monkeypatch):
    monkeypatch.delenv('JOLTIO_API_KEY', raising=False)
    monkeypatch.setenv('DATONS_API_KEY', 'legacy')
    with Client() as client:
        assert client.token == 'legacy'
