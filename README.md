# csvprof — Streaming CSV Profiler

Zero-dependency CSV profiling in pure Python. Point it at a file and get a
per-column report: inferred type, missing values, distinct counts, numeric
statistics, date ranges, top values, duplicate rows and IQR outliers — in a
single streaming pass, so a 10 GB file profiles in constant memory.

```bash
pip install .
csvprof data/customers.csv
csvprof data/customers.csv --json -o report.json
```

```python
from csvprof import profile_csv

profile = profile_csv("data/customers.csv")
print(profile.to_dict()["columns"][0])
```

## Example output

```
File: data/customers.csv
Rows: 12,480  Columns: 6  Delimiter: ','  Encoding: utf-8
Duplicate rows: 37

  customer_id  [integer]
    rows: 12,480  null: 0 (0.0%)  distinct: 12,443
    length: min 5  max 5  mean 5.0
    numeric: min 10001  max 99999  mean 54,821  stddev 25,940
    quartiles: Q1 32,104  median 54,930  Q3 77,512
    outliers (IQR): 0
    top values: '10001' (1), '10002' (1), '10003' (1)

  signup_date  [date]
    rows: 12,480  null: 214 (1.7%)  distinct: 1,892
    range: 2019-03-02 .. 2026-11-01
    top values: '2024-01-15' (41), '2024-06-30' (38)
```

## What it reports

- **Type inference** — `boolean`, `integer`, `float`, `date`, `datetime` or
  `string`, decided per column by the values themselves. A column is only
  typed when one kind explains at least 90% of its non-null values;
  anything messier is reported as a mixed `string` column, never silently
  coerced.
- **Missing data** — counts and ratios, with a configurable set of null
  spellings (`""`, `NA`, `null`, `N/A`, `-`, …).
- **Numeric statistics** — min, max, mean, standard deviation, quartiles
  and median, plus Tukey IQR outlier counts.
- **Text statistics** — distinct counts, value lengths, most frequent
  values.
- **File-level facts** — duplicate rows (by content hash), malformed rows
  with the wrong field count, auto-detected delimiter and encoding.

## Design decisions

1. **One pass, constant memory.** Means and variances use Welford's online
   algorithm; quantiles come from a bounded reservoir sample (2,001 values,
   exact for any column up to that size); distinct-value tracking and
   duplicate hashes are capped and flagged when they saturate. The only
   second pass is the outlier count, which needs the IQR fences first —
   it re-reads the file instead of holding it in memory.
2. **Evidence-based typing, not guessing.** `1`/`0` are integers, never
   booleans; `01/02/2024` is parsed day-first and only falls back to
   month-first when the day-first parse is impossible. A value that
   matches no known shape is a string.
3. **Honest approximations.** When a cap is hit — reservoir sampling,
   distinct-value tracking, duplicate hashes — the report says so
   (`quantiles_exact: false`, `distinct_truncated`, …) instead of
   presenting an estimate as a fact.

## Usage

```
csvprof FILE [--json] [-o FILE] [--top N] [--delimiter CHAR]
             [--null-values TOKENS] [--max-rows N] [--no-outliers]
```

| Flag | Meaning |
| ---- | ------- |
| `--json` | Emit the full report as JSON |
| `-o FILE` | Write the report to a file instead of stdout |
| `--top N` | Most-frequent values shown per column (default 5) |
| `--delimiter CHAR` | Override the auto-detected delimiter |
| `--null-values TOKENS` | Extra comma-separated spellings to treat as missing |
| `--max-rows N` | Profile only the first N data rows |
| `--no-outliers` | Skip the outlier-counting pass |

## Library use

```python
from csvprof import profile_csv

profile = profile_csv("data.csv", top_n=10, max_rows=100_000)
for column in profile.columns:
    print(column.name, column.type, f"{column.null_ratio:.1%} null")
print("duplicates:", profile.duplicate_rows)
```

## Running tests

```bash
pip install pytest
python -m pytest
```

## Tech stack

Python 3.10+ standard library only — `csv`, `hashlib`, `statistics`-free
hand-rolled online algorithms. No third-party dependencies.
