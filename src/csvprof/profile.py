"""Single-pass CSV profiling.

Reads a file row by row with :mod:`csv`, inferring each column's type and
accumulating statistics as it goes. Memory stays flat regardless of file
size: numeric stats use Welford + a bounded reservoir, string frequencies
are capped, and duplicate detection keeps only 64-bit hashes.

A second pass over the file (same reader, no extra memory) counts exact
outliers for numeric columns once the IQR fences are known.
"""

from __future__ import annotations

import csv
import hashlib
import os
from dataclasses import dataclass, field

from .inference import (
    DEFAULT_NULL_TOKENS,
    coerce_numeric,
    infer_column_type,
    infer_value,
    is_null,
)
from .stats import Reservoir, RunningStats, TopValues, iqr_bounds

#: Duplicate hashes tracked before detection saturates.
MAX_DUPLICATE_HASHES = 500_000

#: Bytes sniffed to detect the delimiter.
SNIFF_BYTES = 8192


@dataclass
class ColumnProfile:
    """Everything learned about one column."""

    name: str
    total_rows: int = 0
    null_count: int = 0
    kind_counts: dict[str, int] = field(default_factory=dict)
    numeric: RunningStats = field(default_factory=RunningStats)
    numeric_sample: Reservoir = field(default_factory=Reservoir)
    lengths: RunningStats = field(default_factory=RunningStats)
    dates: list = field(default_factory=list)  # min/max only, kept as 2 items
    top_values: TopValues = field(default_factory=TopValues)
    outliers: int | None = None

    @property
    def non_null(self) -> int:
        return self.total_rows - self.null_count

    @property
    def null_ratio(self) -> float:
        return self.null_count / self.total_rows if self.total_rows else 0.0

    @property
    def type(self) -> str:
        kind, _ = infer_column_type(self.kind_counts, self.non_null)
        return kind

    @property
    def mixed(self) -> bool:
        _, mixed = infer_column_type(self.kind_counts, self.non_null)
        return mixed

    def add(self, raw: str | None, null_tokens: frozenset[str]) -> None:
        self.total_rows += 1
        if is_null(raw, null_tokens):
            self.null_count += 1
            return

        value = raw.strip()  # type: ignore[union-attr]
        kind, parsed = infer_value(value)
        self.kind_counts[kind] = self.kind_counts.get(kind, 0) + 1

        self.lengths.add(len(value))
        self.top_values.add(value)

        number = coerce_numeric(value) if kind in ("integer", "float") else None
        if number is not None:
            self.numeric.add(number)
            self.numeric_sample.add(number)

        if kind in ("date", "datetime"):
            if not self.dates:
                self.dates = [parsed, parsed]
            else:
                self.dates[0] = min(self.dates[0], parsed)
                self.dates[1] = max(self.dates[1], parsed)

    def to_dict(self, top_n: int = 5) -> dict:
        quantiles = self.numeric_sample.quantiles()
        result: dict = {
            "name": self.name,
            "type": self.type,
            "mixed_types": self.mixed,
            "rows": self.total_rows,
            "null_count": self.null_count,
            "null_ratio": round(self.null_ratio, 4),
            "distinct": self.top_values.distinct,
            "distinct_truncated": self.top_values.truncated,
            "top_values": [
                {"value": v, "count": c}
                for v, c in self.top_values.most_common(top_n)
            ],
        }
        if self.lengths.count:
            result["length"] = {
                "min": int(self.lengths.minimum),
                "max": int(self.lengths.maximum),
                "mean": round(self.lengths.mean, 2),
            }
        if self.numeric.count:
            result["numeric"] = {
                "count": self.numeric.count,
                "min": self.numeric.minimum,
                "max": self.numeric.maximum,
                "mean": round(self.numeric.mean, 4),
                "stddev": (
                    round(self.numeric.stddev, 4)
                    if self.numeric.stddev is not None
                    else None
                ),
                "median": quantiles.get(0.5),
                "q1": quantiles.get(0.25),
                "q3": quantiles.get(0.75),
                "quantiles_exact": self.numeric_sample.exact,
                "outliers_iqr": self.outliers,
            }
        if self.dates:
            result["date_range"] = [str(self.dates[0]), str(self.dates[1])]
        return result


@dataclass
class Profile:
    """Whole-file profiling result."""

    path: str
    rows: int
    columns: list[ColumnProfile]
    delimiter: str
    encoding: str
    duplicate_rows: int
    duplicate_tracking_truncated: bool = False
    malformed_rows: int = 0
    top_n: int = 5

    def to_dict(self) -> dict:
        return {
            "file": os.path.basename(self.path),
            "rows": self.rows,
            "columns_count": len(self.columns),
            "delimiter": self.delimiter,
            "encoding": self.encoding,
            "duplicate_rows": self.duplicate_rows,
            "duplicate_tracking_truncated": self.duplicate_tracking_truncated,
            "malformed_rows": self.malformed_rows,
            "columns": [c.to_dict(self.top_n) for c in self.columns],
        }


def _detect_encoding(path: str) -> str:
    """UTF-8 if the file decodes as such, otherwise latin-1 (never fails)."""
    try:
        with open(path, encoding="utf-8") as handle:
            handle.read(SNIFF_BYTES)
        return "utf-8"
    except UnicodeDecodeError:
        return "latin-1"


def _detect_delimiter(path: str, encoding: str, override: str | None) -> str:
    if override:
        return override
    try:
        with open(path, newline="", encoding=encoding) as handle:
            sample = handle.read(SNIFF_BYTES)
        return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except (csv.Error, UnicodeDecodeError):
        return ","


def _open_reader(path: str, encoding: str, delimiter: str):
    handle = open(path, newline="", encoding=encoding)
    reader = csv.DictReader(handle, delimiter=delimiter, restkey=None)
    return handle, reader


def _unique_fieldnames(fieldnames: list[str]) -> list[str]:
    """Disambiguate duplicate header names: ``id, id`` -> ``id, id_2``."""
    seen: dict[str, int] = {}
    out: list[str] = []
    for name in fieldnames:
        name = name.strip() or "column"
        if name in seen:
            seen[name] += 1
            out.append(f"{name}_{seen[name]}")
        else:
            seen[name] = 1
            out.append(name)
    return out


def profile_csv(
    path: str,
    *,
    delimiter: str | None = None,
    null_tokens: frozenset[str] | None = None,
    top_n: int = 5,
    max_rows: int | None = None,
    count_outliers: bool = True,
) -> Profile:
    """Profile the CSV file at *path*.

    Raises ``FileNotFoundError`` for a missing file and ``ValueError`` for
    an empty file or one without a header row.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"no such file: {path}")
    if os.path.getsize(path) == 0:
        raise ValueError(f"empty file: {path}")

    nulls = DEFAULT_NULL_TOKENS if null_tokens is None else null_tokens
    encoding = _detect_encoding(path)
    delim = _detect_delimiter(path, encoding, delimiter)

    handle, reader = _open_reader(path, encoding, delim)
    try:
        if reader.fieldnames is None:
            raise ValueError(f"no header row found in {path}")
        fieldnames = _unique_fieldnames(reader.fieldnames)
        reader.fieldnames = fieldnames
        columns = {name: ColumnProfile(name) for name in fieldnames}

        seen_hashes: set[int] = set()
        duplicates = 0
        dup_truncated = False
        malformed = 0
        rows = 0

        for row in reader:
            if max_rows is not None and rows >= max_rows:
                break
            rows += 1
            raw_values = [row.get(name) for name in fieldnames]
            extra = row.get(None)
            if extra:
                malformed += 1
            for name, raw in zip(fieldnames, raw_values):
                columns[name].add(raw, nulls)

            digest = hashlib.blake2b(
                "\x1f".join("" if v is None else v for v in raw_values).encode(
                    "utf-8", "replace"
                ),
                digest_size=8,
            ).digest()
            key = int.from_bytes(digest, "little")
            if key in seen_hashes:
                duplicates += 1
            elif len(seen_hashes) < MAX_DUPLICATE_HASHES:
                seen_hashes.add(key)
            else:
                dup_truncated = True
    finally:
        handle.close()

    profile = Profile(
        path=path,
        rows=rows,
        columns=[columns[name] for name in fieldnames],
        delimiter=delim,
        encoding=encoding,
        duplicate_rows=duplicates,
        duplicate_tracking_truncated=dup_truncated,
        malformed_rows=malformed,
        top_n=top_n,
    )

    if count_outliers and rows:
        _count_outliers(profile, encoding, delim, fieldnames, nulls)

    return profile


def _count_outliers(
    profile: Profile,
    encoding: str,
    delimiter: str,
    fieldnames: list[str],
    null_tokens: frozenset[str],
) -> None:
    """Second pass: count values outside the Tukey fences per numeric column."""
    numeric_cols = [c for c in profile.columns if c.numeric.count]
    if not numeric_cols:
        return
    fences = {}
    for col in numeric_cols:
        quantiles = col.numeric_sample.quantiles()
        if 0.25 in quantiles and 0.75 in quantiles:
            fences[col.name] = iqr_bounds(quantiles[0.25], quantiles[0.75])
    if not fences:
        return

    counts = {name: 0 for name in fences}
    handle, reader = _open_reader(profile.path, encoding, delimiter)
    try:
        reader.fieldnames = fieldnames
        for row in reader:
            for name, (low, high) in fences.items():
                raw = row.get(name)
                if raw is None or is_null(raw, null_tokens):
                    continue
                number = coerce_numeric(raw)
                if number is not None and (number < low or number > high):
                    counts[name] += 1
    finally:
        handle.close()

    for col in numeric_cols:
        col.outliers = counts.get(col.name)
