"""Per-value type inference for CSV columns.

A raw cell is classified into exactly one of ``boolean``, ``integer``,
``float``, ``date``, ``datetime`` or ``string``. Classification is strict:
``"0012"`` is an integer only if it parses as one, and a value is a date
only if it matches one of the known formats exactly. Nothing is guessed —
anything that does not match a known shape is a string.
"""

from __future__ import annotations

from datetime import date, datetime

#: Formats tried in order. ISO first: ``01/02/2024`` is ambiguous, so the
#: day-first form wins and the month-first form is only used when the
#: day-first parse fails (e.g. ``02/30/2024`` can only be month-first).
DATE_FORMATS = (
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%m/%d/%Y",
    "%Y/%m/%d",
    "%d-%m-%Y",
    "%d %b %Y",
    "%d %B %Y",
)

DATETIME_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%dT%H:%M",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
)

#: Lower-cased spellings that count as booleans. ``1``/``0`` are integers,
#: not booleans — treating them as booleans would misclassify every
#: 0/1-coded column in the wild.
BOOLEAN_WORDS = frozenset(
    {"true", "false", "yes", "no", "y", "n", "t", "f"}
)

#: Cell spellings that count as missing. Configurable per run through
#: :func:`csvprof.profile.profile_csv`.
DEFAULT_NULL_TOKENS = frozenset(
    {"", "null", "none", "na", "n/a", "nil", "-", "~", "nan"}
)


def is_null(value: str | None, null_tokens: frozenset[str]) -> bool:
    """True if *value* should be treated as missing data."""
    if value is None:
        return True
    stripped = value.strip()
    return stripped == "" or stripped.lower() in null_tokens


def infer_value(value: str) -> tuple[str, object]:
    """Classify one non-null cell.

    Returns ``(kind, parsed)`` where ``kind`` is one of ``"boolean"``,
    ``"integer"``, ``"float"``, ``"date"``, ``"datetime"`` or ``"string"``
    and ``parsed`` is the typed value (or the original string for
    ``"string"``).
    """
    text = value.strip()

    lowered = text.lower()
    if lowered in BOOLEAN_WORDS:
        return "boolean", lowered in {"true", "yes", "y", "t"}

    try:
        return "integer", int(text)
    except ValueError:
        pass

    try:
        # int() already rejected this, so a successful float() means a
        # genuine decimal / exponent form such as "3.5" or "1e3".
        return "float", float(text)
    except ValueError:
        pass

    for fmt in DATETIME_FORMATS:
        try:
            return "datetime", datetime.strptime(text, fmt)
        except ValueError:
            continue

    for fmt in DATE_FORMATS:
        try:
            return "date", datetime.strptime(text, fmt).date()
        except ValueError:
            continue

    return "string", text


def infer_column_type(kind_counts: dict[str, int], non_null: int) -> tuple[str, bool]:
    """Pick a column type from per-kind counts of its non-null values.

    The most common kind wins when it explains at least 90% of the values;
    anything less is reported as a mixed ``string`` column so the report
    never pretends a messy column is clean. Returns ``(type, mixed)``.
    """
    if non_null == 0:
        return "unknown", False
    kind, count = max(kind_counts.items(), key=lambda item: item[1])
    if count / non_null >= 0.9:
        return kind, count != non_null
    return "string", True


def coerce_numeric(value: str) -> float | None:
    """Parse *value* as a float, or return None if it is not numeric."""
    try:
        return float(value.strip())
    except (ValueError, AttributeError):
        return None


def coerce_date(value: str) -> date | datetime | None:
    """Parse *value* as a date/datetime, or return None."""
    kind, parsed = infer_value(value)
    if kind in ("date", "datetime"):
        return parsed  # type: ignore[return-value]
    return None
