"""csvprof — streaming CSV profiler.

Profile a CSV file in a single pass: infer each column's type, compute
descriptive statistics, and report missing values, duplicates and outliers.
"""

from .profile import Profile, profile_csv

__version__ = "1.0.0"
__all__ = ["profile_csv", "Profile", "__version__"]
