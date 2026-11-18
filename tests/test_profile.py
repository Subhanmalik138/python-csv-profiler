"""End-to-end tests for profile_csv on real files."""

import csv

import pytest

from csvprof.profile import profile_csv


def write_csv(tmp_path, rows, header=None, delimiter=","):
    path = tmp_path / "data.csv"
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, delimiter=delimiter)
        if header is not None:
            writer.writerow(header)
        writer.writerows(rows)
    return str(path)


def test_basic_numeric_and_string_columns(tmp_path):
    path = write_csv(
        tmp_path,
        [["1", "alice", "10.5"], ["2", "bob", "20.5"], ["3", "alice", "30.5"]],
        header=["id", "name", "score"],
    )
    profile = profile_csv(path)
    assert profile.rows == 3
    assert profile.delimiter == ","
    assert profile.encoding == "utf-8"

    by_name = {c.name: c for c in profile.columns}
    assert by_name["id"].type == "integer"
    assert by_name["id"].numeric.mean == 2.0
    assert by_name["id"].numeric.minimum == 1
    assert by_name["score"].type == "float"
    assert by_name["score"].numeric.mean == pytest.approx(20.5)
    assert by_name["name"].type == "string"
    assert by_name["name"].top_values.most_common(1) == [("alice", 2)]
    assert by_name["name"].top_values.distinct == 2


def test_missing_values_and_null_ratios(tmp_path):
    path = write_csv(
        tmp_path,
        [["1", "NA"], ["2", ""], ["3", "x"], ["4", "null"]],
        header=["id", "note"],
    )
    profile = profile_csv(path)
    note = {c.name: c for c in profile.columns}["note"]
    assert note.null_count == 3
    assert note.null_ratio == pytest.approx(0.75)
    assert note.non_null == 1


def test_custom_null_tokens(tmp_path):
    path = write_csv(
        tmp_path,
        [["1", "missing"], ["2", "x"]],
        header=["id", "note"],
    )
    profile = profile_csv(path, null_tokens=frozenset({"missing"}))
    note = {c.name: c for c in profile.columns}["note"]
    assert note.null_count == 1


def test_duplicate_rows_detected(tmp_path):
    path = write_csv(
        tmp_path,
        [["1", "a"], ["2", "b"], ["1", "a"], ["1", "a"]],
        header=["id", "val"],
    )
    profile = profile_csv(path)
    assert profile.duplicate_rows == 2


def test_iqr_outliers_counted(tmp_path):
    rows = [[str(v)] for v in [10, 11, 12, 13, 14, 15, 16, 100]]
    path = write_csv(tmp_path, rows, header=["v"])
    profile = profile_csv(path)
    col = profile.columns[0]
    assert col.numeric.count == 8
    # 100 sits far outside the Q1/Q3 fences for this data.
    assert col.outliers == 1


def test_outliers_can_be_skipped(tmp_path):
    path = write_csv(tmp_path, [[str(v)] for v in [1, 2, 3, 100]], header=["v"])
    profile = profile_csv(path, count_outliers=False)
    assert profile.columns[0].outliers is None


def test_date_column_range(tmp_path):
    path = write_csv(
        tmp_path,
        [["2024-01-05"], ["2023-12-31"], ["2024-06-01"]],
        header=["d"],
    )
    profile = profile_csv(path)
    col = profile.columns[0]
    assert col.type == "date"
    assert str(col.dates[0]) == "2023-12-31"
    assert str(col.dates[1]) == "2024-06-01"


def test_mixed_column_reported_as_string(tmp_path):
    path = write_csv(
        tmp_path,
        [["1"], ["two"], ["3"], ["four"], ["5"], ["six"]],
        header=["v"],
    )
    profile = profile_csv(path)
    col = profile.columns[0]
    assert col.type == "string"
    assert col.mixed


def test_semicolon_delimiter_sniffed(tmp_path):
    path = write_csv(
        tmp_path,
        [["1", "a"], ["2", "b"]],
        header=["id", "val"],
        delimiter=";",
    )
    profile = profile_csv(path)
    assert profile.delimiter == ";"
    assert [c.name for c in profile.columns] == ["id", "val"]


def test_duplicate_header_names_disambiguated(tmp_path):
    path = write_csv(tmp_path, [["1", "2"]], header=["id", "id"])
    profile = profile_csv(path)
    assert [c.name for c in profile.columns] == ["id", "id_2"]


def test_header_only_file(tmp_path):
    path = write_csv(tmp_path, [], header=["a", "b"])
    profile = profile_csv(path)
    assert profile.rows == 0
    assert profile.columns[0].type == "unknown"


def test_empty_file_raises(tmp_path):
    path = tmp_path / "empty.csv"
    path.write_text("")
    with pytest.raises(ValueError, match="empty file"):
        profile_csv(str(path))


def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        profile_csv(str(tmp_path / "nope.csv"))


def test_max_rows_limits_work(tmp_path):
    rows = [[str(i)] for i in range(100)]
    path = write_csv(tmp_path, rows, header=["n"])
    profile = profile_csv(path, max_rows=10)
    assert profile.rows == 10
    assert profile.columns[0].numeric.count == 10


def test_to_dict_shape(tmp_path):
    path = write_csv(tmp_path, [["1", "x"], ["2", "y"]], header=["n", "s"])
    data = profile_csv(path).to_dict()
    assert data["rows"] == 2
    assert data["columns_count"] == 2
    assert data["duplicate_rows"] == 0
    numeric = data["columns"][0]["numeric"]
    assert numeric["count"] == 2
    assert numeric["median"] == 1.5
    assert numeric["quantiles_exact"] is True
    assert numeric["outliers_iqr"] == 0
