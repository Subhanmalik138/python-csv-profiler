"""Tests for per-value type inference."""

from csvprof.inference import DEFAULT_NULL_TOKENS, infer_column_type, infer_value, is_null


def test_integers():
    assert infer_value("42") == ("integer", 42)
    assert infer_value("-7") == ("integer", -7)
    assert infer_value("  12  ") == ("integer", 12)


def test_floats():
    assert infer_value("3.5") == ("float", 3.5)
    assert infer_value("-0.25") == ("float", -0.25)
    assert infer_value("1e3") == ("float", 1000.0)


def test_booleans():
    assert infer_value("true") == ("boolean", True)
    assert infer_value("FALSE") == ("boolean", False)
    assert infer_value("yes") == ("boolean", True)
    assert infer_value("No") == ("boolean", False)


def test_one_and_zero_are_integers_not_booleans():
    assert infer_value("1")[0] == "integer"
    assert infer_value("0")[0] == "integer"


def test_dates_iso_first():
    kind, value = infer_value("2024-03-15")
    assert kind == "date"
    assert value.isoformat() == "2024-03-15"


def test_dates_day_first_then_month_first():
    # 01/02/2024 is day-first: 1 Feb 2024.
    kind, value = infer_value("01/02/2024")
    assert kind == "date"
    assert (value.day, value.month) == (1, 2)
    # 02/13/2024 cannot be day-first (month 13), so month-first applies.
    kind, value = infer_value("02/13/2024")
    assert kind == "date"
    assert (value.day, value.month) == (13, 2)


def test_datetimes():
    kind, value = infer_value("2024-03-15 10:30:00")
    assert kind == "datetime"
    assert (value.hour, value.minute) == (10, 30)
    kind, _ = infer_value("2024-03-15T10:30:00")
    assert kind == "datetime"


def test_strings_fall_through():
    assert infer_value("hello")[0] == "string"
    assert infer_value("12a")[0] == "string"
    assert infer_value("2024-13-45")[0] == "string"


def test_null_detection():
    assert is_null(None, DEFAULT_NULL_TOKENS)
    assert is_null("", DEFAULT_NULL_TOKENS)
    assert is_null("  ", DEFAULT_NULL_TOKENS)
    assert is_null("NA", DEFAULT_NULL_TOKENS)
    assert is_null("n/a", DEFAULT_NULL_TOKENS)
    assert is_null("-", DEFAULT_NULL_TOKENS)
    assert not is_null("0", DEFAULT_NULL_TOKENS)
    assert not is_null("false", DEFAULT_NULL_TOKENS)


def test_column_type_majority_rule():
    assert infer_column_type({"integer": 95, "string": 5}, 100) == ("integer", True)
    assert infer_column_type({"integer": 100}, 100) == ("integer", False)
    # Below the 90% bar the column is reported as a mixed string.
    assert infer_column_type({"integer": 80, "string": 20}, 100) == ("string", True)


def test_column_type_empty():
    assert infer_column_type({}, 0) == ("unknown", False)
