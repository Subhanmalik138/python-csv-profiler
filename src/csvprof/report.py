"""Render a :class:`~csvprof.profile.Profile` as text or JSON."""

from __future__ import annotations

import json

from .profile import ColumnProfile, Profile


def _fmt_number(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:,.4g}"
    return f"{value:,}"


def _column_block(col: ColumnProfile, top_n: int) -> list[str]:
    lines = [f"  {col.name}  [{col.type}{' (mixed)' if col.mixed else ''}]"]
    lines.append(f"    rows: {col.total_rows:,}  null: {col.null_count:,} "
                 f"({col.null_ratio:.1%})  distinct: {col.top_values.distinct:,}"
                 + ("+" if col.top_values.truncated else ""))
    if col.lengths.count:
        lines.append(
            f"    length: min {int(col.lengths.minimum)}  "
            f"max {int(col.lengths.maximum)}  mean {col.lengths.mean:.1f}"
        )
    if col.numeric.count:
        num = col.numeric
        quantiles = col.numeric_sample.quantiles()
        lines.append(
            f"    numeric: min {_fmt_number(num.minimum)}  "
            f"max {_fmt_number(num.maximum)}  mean {_fmt_number(num.mean)}  "
            f"stddev {_fmt_number(num.stddev)}"
        )
        lines.append(
            f"    quartiles: Q1 {_fmt_number(quantiles.get(0.25))}  "
            f"median {_fmt_number(quantiles.get(0.5))}  "
            f"Q3 {_fmt_number(quantiles.get(0.75))}"
            + ("" if col.numeric_sample.exact else "  (approx.)")
        )
        if col.outliers is not None:
            lines.append(f"    outliers (IQR): {col.outliers:,}")
    if col.dates:
        lines.append(f"    range: {col.dates[0]} .. {col.dates[1]}")
    top = col.top_values.most_common(top_n)
    if top:
        joined = ", ".join(f"{v!r} ({c})" for v, c in top)
        lines.append(f"    top values: {joined}")
    return lines


def render_text(profile: Profile) -> str:
    """Human-readable report."""
    lines = [
        f"File: {profile.path}",
        f"Rows: {profile.rows:,}  Columns: {len(profile.columns)}  "
        f"Delimiter: {profile.delimiter!r}  Encoding: {profile.encoding}",
    ]
    if profile.duplicate_rows:
        lines.append(f"Duplicate rows: {profile.duplicate_rows:,}")
    if profile.duplicate_tracking_truncated:
        lines.append("Note: duplicate tracking saturated; duplicate count is a lower bound.")
    if profile.malformed_rows:
        lines.append(f"Malformed rows (wrong field count): {profile.malformed_rows:,}")
    lines.append("")
    for col in profile.columns:
        lines.extend(_column_block(col, profile.top_n))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_json(profile: Profile) -> str:
    """Machine-readable report (``json.dumps`` of :meth:`Profile.to_dict`)."""
    return json.dumps(profile.to_dict(), indent=2, default=str) + "\n"
