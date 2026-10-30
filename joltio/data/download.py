"""Resumable, quota-aware Data export to monthly Parquet partitions."""

from __future__ import annotations

import json
import logging
import math
import re
import time
from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from joltio.exceptions import QueryError, RateLimitError

if TYPE_CHECKING:
    from joltio.client import Client

# Readers (pyarrow, pandas, Spark) skip files starting with "_", so progress state never breaks reading the dataset.
MANIFEST = "_manifest.json"
TABLE = re.compile(r"^[a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*$")
logger = logging.getLogger(__name__)


def _instant(value: str | date | datetime) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    return _instant(datetime.fromisoformat(value.replace("Z", "+00:00")))


def _next_month(value: datetime) -> datetime:
    return datetime(value.year + (value.month == 12), value.month % 12 + 1, 1, tzinfo=timezone.utc)


def _subtract_months(value: datetime, months: int) -> datetime:
    month = value.year * 12 + value.month - 1 - months
    year, month_index = divmod(month, 12)
    target_month = month_index + 1
    return value.replace(year=year, month=target_month, day=min(value.day, monthrange(year, target_month)[1]))


def _stamp(value: datetime) -> str:
    return value.strftime("%Y%m%dT%H%M%S%f")


def _sql_time(value: datetime) -> str:
    return f"toDateTime64('{value:%Y-%m-%d %H:%M:%S.%f}', 6, 'UTC')"


def _state(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def _save_state(path: Path, state: dict[str, str]) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, sort_keys=True, indent=2) + "\n")
    temporary.replace(path)


def _query(client: Client, sql: str, max_wait: float = 3600) -> dict:
    for attempt in range(2):
        try:
            return client.post("/data/query", json={"sql": sql, "format": "json"})
        except RateLimitError as error:
            quota = isinstance(error.detail, dict) and error.detail.get("error") == "quota_exhausted"
            now = datetime.now(timezone.utc)
            next_hour = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
            delay = error.retry_after if error.retry_after is not None else math.ceil((next_hour - now).total_seconds()) if quota else None
            if attempt or delay is None or delay < 0 or delay > max_wait:
                raise
            logger.warning("Joltio Data rate limit reached; waiting %s seconds before one retry", delay)
            time.sleep(delay)
    raise AssertionError("Unreachable")


def download(client: Client, table: str, start: str | date | datetime | None = None, end: str | date | datetime | None = None, *, path: str | Path, since: str | None = None, revise_days: int = 0, max_wait: float = 3600) -> list[Path]:
    """Download [start, end) in series, resume completed chunks, and write month=YYYY-MM/part-*.parquet."""
    if not TABLE.fullmatch(table):
        raise ValueError("table must be a qualified SQL identifier")
    if revise_days < 0:
        raise ValueError("revise_days cannot be negative")
    if not math.isfinite(max_wait) or max_wait < 0:
        raise ValueError("max_wait must be a non-negative, finite number of seconds")
    if since not in (None, "last"):
        raise ValueError("since must be 'last' or None")
    destination = Path(path)
    destination.mkdir(parents=True, exist_ok=True)
    coverage = client.get("/data/coverage", params={"table": table})
    item = next((row for row in coverage if row.get("table_name") == table), None)
    if item is None:
        raise ValueError(f"No coverage for {table} on this plan")
    plan = client.get("/v1/data/plan")
    query_limits = plan.get("query_limits")
    if not isinstance(query_limits, dict) or query_limits.get("rows_per_query_raw") is None:
        plans = client.get("/v1/plans/public")
        published = next((entry for entry in plans if entry["key"] == plan["tier"]), None)
        if published is None:
            raise ValueError(f"The server does not expose a row limit for plan {plan['tier']}")
        query_limits = published["definition"]["query_limits"]
    cap = int(query_limits["rows_per_query_raw"])
    if cap < 1:
        raise ValueError("The plan does not allow raw rows")
    domains = client.get("/data/describe")["domains"]
    domain = next((entry["domain"] for entry in domains if entry.get("table") == table), None)
    if domain is None:
        raise ValueError(f"No schema for {table}")
    description = client.get("/data/describe", params={"domain": domain})
    columns = [column["name"] for column in description["columns"]]
    if "datetime" not in columns or not all(re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", column) for column in columns):
        raise ValueError(f"{table} needs an explicit datetime column and simple column names for bulk download")
    now = datetime.now(timezone.utc)
    earliest = max((_instant(row["min_datetime"]) for row in [item, *item.get("splits", [])] if row.get("min_datetime")), default=now)
    latest = max((_instant(row["max_actual_datetime"]) for row in [item, *item.get("splits", [])] if row.get("max_actual_datetime")), default=now)
    lower = max(earliest, _subtract_months(now, int(plan["history_months"])) if plan.get("history_months") is not None else earliest)
    upper = min(_instant(end) if end is not None else now, latest + timedelta(seconds=1))
    completed: list[tuple[datetime, datetime]] = []
    if since == "last":
        completed = [(datetime.fromisoformat(begin), datetime.fromisoformat(finish)) for file in destination.glob(f"month=*/{MANIFEST}") for value, status in _state(file).items() if status in ("done", "empty") for begin, finish in [value.split("_", 1)]]
        if not completed:
            raise ValueError("since='last' requires an existing completed download")
        lower = max(lower, max(finish for _, finish in completed) - timedelta(days=revise_days))
    elif start is not None:
        lower = max(lower, _instant(start))
    if lower >= upper:
        return []
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as error:
        raise ImportError('Install joltio[parquet] to use data.download()') from error
    written: list[Path] = []

    def chunk(begin: datetime, finish: datetime) -> None:
        folder = destination / f"month={begin:%Y-%m}"
        folder.mkdir(exist_ok=True)
        manifest = folder / MANIFEST
        state = _state(manifest)
        key = f"{begin.isoformat()}_{finish.isoformat()}"
        output = folder / f"part-{_stamp(begin)}-{_stamp(finish)}.parquet"
        if (state.get(key) == "done" and output.exists() or state.get(key) == "empty") and not (since == "last" and finish > lower):
            return
        if state.get(key) == "split":
            midpoint = begin + (finish - begin) / 2
            chunk(begin, midpoint)
            chunk(midpoint, finish)
            return
        sql = f"SELECT {', '.join(columns)} FROM {table} WHERE datetime >= {_sql_time(begin)} AND datetime < {_sql_time(finish)} ORDER BY datetime"
        try:
            result = _query(client, sql, max_wait=max_wait)
        except QueryError as error:
            if error.status_code != 422:
                raise
            result = None
        if result is None or result.get("truncated"):
            if finish - begin <= timedelta(seconds=1):
                raise ValueError(f"One-second interval still exceeds the plan limit: {begin.isoformat()}")
            midpoint = begin + (finish - begin) / 2
            state[key] = "split"
            _save_state(manifest, state)
            chunk(begin, midpoint)
            chunk(midpoint, finish)
            return
        result_columns = [column["name"] for column in result["columns"]]
        records = [dict(zip(result_columns, row)) for row in result["rows"]]
        if records:
            temporary = folder / f"_{output.name}.tmp"
            pq.write_table(pa.Table.from_pylist(records), temporary)
            temporary.replace(output)
            written.append(output)
        elif output.exists():
            temporary = folder / f"_{output.name}.tmp"
            pq.write_table(pa.Table.from_pydict({column: [] for column in result_columns}), temporary)
            temporary.replace(output)
        state[key] = "done" if records else "empty"
        _save_state(manifest, state)

    if since == "last":
        for begin, finish in sorted(completed):
            if finish > lower:
                chunk(begin, finish)
        cursor = max(lower, max(finish for _, finish in completed))
    else:
        cursor = lower
    while cursor < upper:
        month_end = min(upper, _next_month(cursor))
        days = max(1, (month_end - cursor).total_seconds() / 86400)
        estimated_rows = (item.get("row_count") or 0) / max(1, (latest - earliest).total_seconds() / 86400) * days
        step = timedelta(days=1) if estimated_rows > cap else month_end - cursor
        while cursor < month_end:
            finish = min(month_end, cursor + step)
            chunk(cursor, finish)
            cursor = finish
    return written
