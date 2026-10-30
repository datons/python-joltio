"""The download boundary resumes completed windows and follows server truncation."""

import re
from datetime import datetime, timezone

import pytest

from joltio.data.download import _query, _subtract_months, download
from joltio.exceptions import QueryError, RateLimitError


class FakeClient:
    def __init__(self):
        self.queries = []

    def get(self, path, params=None):
        if path == "/data/coverage":
            return [{"table_name": "omie.prices", "min_datetime": "2026-10-01T00:00:00Z", "max_actual_datetime": "2026-10-03T00:00:00Z", "row_count": 0}]
        if path == "/v1/data/plan":
            return {"tier": "professional", "history_months": None}
        if path == "/v1/plans/public":
            return [{"key": "professional", "definition": {"query_limits": {"rows_per_query_raw": 1}}}]
        if path == "/data/describe" and params is None:
            return {"domains": [{"domain": "prices", "table": "omie.prices"}]}
        if path == "/data/describe":
            return {"columns": [{"name": "datetime"}, {"name": "price"}]}
        raise AssertionError(path)

    def post(self, path, json):
        assert path == "/data/query"
        self.queries.append(json["sql"])
        bounds = re.findall(r"datetime [<>]=? toDateTime64\('([^']+)'", json["sql"])
        begin, end = (datetime.strptime(value, "%Y-%m-%d %H:%M:%S.%f").replace(tzinfo=timezone.utc) for value in bounds)
        observations = [(datetime(2026, 10, 1, 12, tzinfo=timezone.utc), 50), (datetime(2026, 10, 2, 12, tzinfo=timezone.utc), 60)]
        rows = [[moment.isoformat(), price] for moment, price in observations if begin <= moment < end]
        return {"columns": [{"name": "datetime", "type": "DateTime"}, {"name": "price", "type": "Float64"}], "rows": rows[:1], "truncated": len(rows) > 1}


def test_history_window_preserves_day_with_month_end_clamping():
    assert _subtract_months(datetime(2026, 3, 31, tzinfo=timezone.utc), 1) == datetime(2026, 2, 28, tzinfo=timezone.utc)


def test_download_splits_and_resumes_without_repeating_queries(tmp_path):
    parquet = pytest.importorskip("pyarrow.parquet")
    client = FakeClient()
    paths = download(client, "omie.prices", "2026-10-01", "2026-10-03", path=tmp_path)
    assert len(paths) == 2
    assert len(client.queries) == 3
    assert all(path.parent.name == "month=2026-10" for path in paths)
    assert sum(parquet.read_table(path).num_rows for path in paths) == 2
    count = len(client.queries)
    assert download(client, "omie.prices", "2026-10-01", "2026-10-03", path=tmp_path) == []
    assert len(client.queries) == count


def test_downloaded_folder_reads_as_one_dataset(tmp_path):
    parquet = pytest.importorskip("pyarrow.parquet")
    download(FakeClient(), "omie.prices", "2026-10-01", "2026-10-03", path=tmp_path)
    assert parquet.read_table(tmp_path).num_rows == 2


def test_download_splits_a_422_interval(tmp_path):
    pytest.importorskip("pyarrow.parquet")

    class Costly(FakeClient):
        def post(self, path, json):
            if len(self.queries) == 0:
                self.queries.append(json["sql"])
                raise QueryError(422, "query_too_expensive")
            return super().post(path, json)

    client = Costly()
    assert len(download(client, "omie.prices", "2026-10-01", "2026-10-03", path=tmp_path)) == 2


def test_revision_refresh_reuses_existing_partition_file(tmp_path):
    parquet = pytest.importorskip("pyarrow.parquet")
    client = FakeClient()
    download(client, "omie.prices", "2026-10-01", "2026-10-03", path=tmp_path)
    original_files = sorted(tmp_path.glob("month=*/*.parquet"))
    assert len(download(client, "omie.prices", end="2026-10-03", path=tmp_path, since="last", revise_days=1)) == 1
    assert sorted(tmp_path.glob("month=*/*.parquet")) == original_files
    assert sum(parquet.read_table(path).num_rows for path in original_files) == 2


def test_private_plan_uses_its_authenticated_row_limit(tmp_path):
    pytest.importorskip("pyarrow.parquet")

    class Private(FakeClient):
        def get(self, path, params=None):
            if path == "/v1/data/plan":
                return {"tier": "internal", "history_months": None, "query_limits": {"rows_per_query_raw": 1}}
            if path == "/v1/plans/public":
                raise AssertionError("The public catalog must not be needed for an internal plan")
            return super().get(path, params)

    assert len(download(Private(), "omie.prices", "2026-10-01", "2026-10-03", path=tmp_path)) == 2


def test_quota_waits_only_once(monkeypatch, caplog):
    sleeps = []
    monkeypatch.setattr("joltio.data.download.time.sleep", sleeps.append)

    class Limited:
        calls = 0

        def post(self, *_args, **_kwargs):
            self.calls += 1
            raise RateLimitError(2)

    client = Limited()
    with pytest.raises(RateLimitError):
        _query(client, "SELECT 1")
    assert client.calls == 2
    assert sleeps == [2]
    assert "waiting 2 seconds" in caplog.text


def test_quota_without_retry_after_waits_at_most_until_next_hour(monkeypatch, caplog):
    sleeps = []
    monkeypatch.setattr("joltio.data.download.time.sleep", sleeps.append)

    class Limited:
        calls = 0

        def post(self, *_args, **_kwargs):
            self.calls += 1
            raise RateLimitError(detail={"error": "quota_exhausted"})

    client = Limited()
    with pytest.raises(RateLimitError):
        _query(client, "SELECT 1", max_wait=3600)
    assert client.calls == 2
    assert len(sleeps) == 1 and 0 < sleeps[0] <= 3600
    assert f"waiting {sleeps[0]} seconds" in caplog.text


def test_max_wait_rejects_long_retry_after_without_sleep(monkeypatch):
    monkeypatch.setattr("joltio.data.download.time.sleep", lambda _seconds: pytest.fail("must not sleep"))

    class Limited:
        calls = 0

        def post(self, *_args, **_kwargs):
            self.calls += 1
            raise RateLimitError(90)

    client = Limited()
    with pytest.raises(RateLimitError):
        _query(client, "SELECT 1", max_wait=30)
    assert client.calls == 1
