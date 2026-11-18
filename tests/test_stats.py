"""Tests for the online statistics helpers."""

import math

from csvprof.stats import Reservoir, RunningStats, TopValues, iqr_bounds


def test_running_stats_matches_hand_computed():
    stats = RunningStats()
    for value in [2, 4, 4, 4, 5, 5, 7, 9]:
        stats.add(value)
    assert stats.count == 8
    assert stats.mean == 5.0
    assert stats.minimum == 2
    assert stats.maximum == 9
    # Sample variance of this classic example is 32/7.
    assert math.isclose(stats.variance, 32 / 7)
    assert math.isclose(stats.stddev, math.sqrt(32 / 7))


def test_running_stats_single_value_has_no_variance():
    stats = RunningStats()
    stats.add(3.0)
    assert stats.variance is None
    assert stats.stddev is None


def test_reservoir_exact_for_small_streams():
    sample = Reservoir(size=10)
    for value in range(1, 11):
        sample.add(float(value))
    assert sample.exact
    quantiles = sample.quantiles()
    assert quantiles[0.5] == 5.5
    assert quantiles[0.25] == 3.25
    assert quantiles[0.75] == 7.75


def test_reservoir_caps_memory_on_large_streams():
    sample = Reservoir(size=50, seed=1)
    for value in range(100_000):
        sample.add(float(value))
    assert not sample.exact
    assert len(sample._sample) == 50
    quantiles = sample.quantiles()
    # Median of 0..99999 is ~50000; a uniform sample should be close.
    assert 40_000 < quantiles[0.5] < 60_000


def test_reservoir_deterministic_with_seed():
    first = Reservoir(size=20, seed=7)
    second = Reservoir(size=20, seed=7)
    for value in range(500):
        first.add(float(value))
        second.add(float(value))
    assert first._sample == second._sample


def test_iqr_bounds():
    low, high = iqr_bounds(10, 20)
    assert (low, high) == (-5.0, 35.0)


def test_top_values_counts_and_cap():
    top = TopValues()
    for _ in range(3):
        top.add("a")
    top.add("b")
    assert top.most_common(1) == [("a", 3)]
    assert top.distinct == 2
    assert not top.truncated


def test_top_values_truncates_high_cardinality(monkeypatch):
    monkeypatch.setattr("csvprof.stats.MAX_DISTINCT_TRACKED", 3)
    top = TopValues()
    for value in ["a", "b", "c", "d", "e"]:
        top.add(value)
    assert top.truncated
    assert top.distinct == 3
    # Values already tracked still count.
    top.add("a")
    assert top.most_common(1) == [("a", 2)]
