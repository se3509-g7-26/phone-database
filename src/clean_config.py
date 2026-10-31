"""M3 constants; rationale and sensitivity are recorded in the cleaning report."""
from pathlib import Path

MAPPINGS = Path(__file__).resolve().parents[1] / 'data' / 'mappings'
MISSING_TOKENS = frozenset(('', '-', 'n/a', 'na', 'unknown'))  # Explicit nonmeasurements; 'No' is meaningful.
MIN_YEAR = 1900  # Conservative calendar screen, not an asserted first-phone date.
MEMORY_UNIT_BASE = 1000  # SI MB/GB/TB conversion; binary units are not inferred.
IQR_FACTOR = 1.5  # Exploratory Tukey fence: flags extremes, never deletes measurements.
MIN_COHORT = 20  # Avoid unstable fences in very small field/unit/OS cohorts.
MISSING_WARN_SHARE = 0.30  # Coverage warning, not an exclusion rule.
COVERAGE_DAYS = 30  # Snapshot currency relative to newest landed observation, not wall clock.
NUMERIC_FIELDS = ('price', 'year', 'internalmemory', 'weight', 'displaysize', 'batdescription1')
NUMBER_PATTERN = r'-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?'  # Grouped comma thousands, dot decimals; no locale guessing.
