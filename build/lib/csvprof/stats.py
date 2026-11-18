"""Online statistics that run in constant memory.

* :class:`RunningStats` — mean and (sample) variance via Welford's
  algorithm, so a column is summarised without keeping its values.
* :class:`Reservoir` — uniform random sample of a stream, used for
  quantiles. When the stream is shorter than the reservoir the sample is
  exact, so small files get exact medians and quartiles.
* :class:`TopValues` — most frequent values, with a hard cap on tracked
  distinct values so a high-cardinality column cannot grow memory without
  bound.
"""

from __future__ import annotations

import math
import random
from collections import Counter

#: Values kept for quantile estimation. 2001 is large enough that the
#: median/quartiles of any column under ~2k rows are exact, and small
#: enough that memory stays flat on multi-million-row files.
RESERVOIR_SIZE = 2001

#: Distinct values tracked per column before counting saturates.
MAX_DISTINCT_TRACKED = 10_000


class RunningStats:
    """Mean and sample variance in one pass (Welford, 1962)."""

    __slots__ = ("count", "mean", "_m2", "minimum", "maximum")

    def __init__(self) -> None:
        self.count = 0
        self.mean = 0.0
        self._m2 = 0.0
        self.minimum = math.inf
        self.maximum = -math.inf

    def add(self, value: float) -> None:
        self.count += 1
        delta = value - self.mean
        self.mean += delta / self.count
        self._m2 += delta * (value - self.mean)
        self.minimum = min(self.minimum, value)
        self.maximum = max(self.maximum, value)

    @property
    def variance(self) -> float | None:
        if self.count < 2:
            return None
        return self._m2 / (self.count - 1)

    @property
    def stddev(self) -> float | None:
        var = self.variance
        return math.sqrt(var) if var is not None else None


class Reservoir:
    """Uniform sample of a stream (Algorithm R, Vitter 1985)."""

    __slots__ = ("size", "_sample", "_seen", "_rng")

    def __init__(self, size: int = RESERVOIR_SIZE, seed: int = 42) -> None:
        self.size = size
        self._sample: list[float] = []
        self._seen = 0
        self._rng = random.Random(seed)

    def add(self, value: float) -> None:
        self._seen += 1
        if len(self._sample) < self.size:
            self._sample.append(value)
        elif (j := self._rng.randrange(self._seen)) < self.size:
            self._sample[j] = value

    @property
    def count(self) -> int:
        return self._seen

    @property
    def exact(self) -> bool:
        """True when the sample holds every value seen so far."""
        return self._seen <= self.size

    def quantiles(self, qs: tuple[float, ...] = (0.25, 0.5, 0.75)) -> dict[float, float]:
        """Linear-interpolated quantiles (type-7, the numpy default)."""
        if not self._sample:
            return {}
        ordered = sorted(self._sample)
        n = len(ordered)
        out: dict[float, float] = {}
        for q in qs:
            pos = q * (n - 1)
            lo = math.floor(pos)
            hi = math.ceil(pos)
            if lo == hi:
                out[q] = ordered[lo]
            else:
                out[q] = ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)
        return out


def iqr_bounds(q1: float, q3: float, k: float = 1.5) -> tuple[float, float]:
    """Tukey fences: values outside [Q1 - k*IQR, Q3 + k*IQR] are outliers."""
    iqr = q3 - q1
    return q1 - k * iqr, q3 + k * iqr


class TopValues:
    """Frequency table for a column, capped at MAX_DISTINCT_TRACKED keys."""

    __slots__ = ("_counter", "_distinct", "truncated")

    def __init__(self) -> None:
        self._counter: Counter[str] = Counter()
        self._distinct = 0
        self.truncated = False

    def add(self, value: str) -> None:
        if value in self._counter:
            self._counter[value] += 1
            return
        if self._distinct >= MAX_DISTINCT_TRACKED:
            self.truncated = True
            return
        self._counter[value] = 1
        self._distinct += 1

    @property
    def distinct(self) -> int:
        return self._distinct

    def most_common(self, n: int) -> list[tuple[str, int]]:
        return self._counter.most_common(n)
