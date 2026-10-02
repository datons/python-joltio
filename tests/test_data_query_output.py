import io

import pytest

from joltio_toolkit.custom.data import _data_without_metadata

CSV = b"# row_count=2 query_type=raw max_rows_applied=100 truncated=False freshness=[]\nprogram,media\nPDBF,149.03\nPHF1,145.91\n"


def _join(chunks: list[bytes], capsys: pytest.CaptureFixture[str]) -> tuple[bytes, str]:
    data = b"".join(_data_without_metadata(chunks))
    return data, capsys.readouterr().err


@pytest.mark.parametrize("size", [1, 3, 7, 40, 10_000])
def test_metadata_line_goes_to_stderr_whatever_the_chunking(size, capsys):
    chunks = [CSV[i : i + size] for i in range(0, len(CSV), size)]
    data, err = _join(chunks, capsys)
    assert data == b"program,media\nPDBF,149.03\nPHF1,145.91\n"
    assert err == "# row_count=2 query_type=raw max_rows_applied=100 truncated=False freshness=[]\n"


def test_header_starting_with_hash_is_kept(capsys):
    data, err = _join([b"#id,valor\n1,2\n"], capsys)
    assert data == b"#id,valor\n1,2\n"
    assert err == ""


def test_csv_without_metadata_is_untouched(capsys):
    data, err = _join([b"x\n", b"1\n"], capsys)
    assert data == b"x\n1\n"
    assert err == ""


def test_parquet_reads_real_columns_not_the_metadata_line(capsys):
    arrow_csv = pytest.importorskip("pyarrow.csv")
    reader = arrow_csv.open_csv(io.BytesIO(b"".join(_data_without_metadata([CSV]))))
    assert reader.schema.names == ["program", "media"]


def test_data_tools_add_only_what_the_backend_does_not_proxy():
    from joltio_toolkit.custom.data import data_api_operations
    from joltio_toolkit.spec import bundled_data_spec, bundled_spec

    names = set(data_api_operations(bundled_data_spec(), bundled_spec()).values())
    # Lo que un agente necesita de Data y el backend no ofrece.
    assert {"data_query", "data_indicators_list", "data_search_facets"} <= names
    # Claves, plan, uso, cobertura… ya existen como proxies del backend en /api/data: no se duplican.
    assert not names & {"data_keys_create", "data_keys_list", "data_plan_list", "data_usage_list", "data_coverage_list", "data_members_move_seat", "data_reingests_create"}
    assert all("-" not in name for name in names)
