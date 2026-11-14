"""Build the reviewable notebook source; execution is a separate command."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
cells=[]

def md(text):
    cells.append(dict(cell_type='markdown',metadata={},source=text.splitlines(keepends=True)))

def code(text):
    cells.append(dict(cell_type='code',metadata={},source=text.splitlines(keepends=True),execution_count=None,outputs=[]))

md('''# M4 — Cellphone catalog prices and specifications

This exploration reads the M3 layer without changing it. Catalog prices are **not verified launch MSRP**. Android is an OS grouping, not a validated smartphone-only device class. See the generated [EDA report](../docs/eda_report.md).
''')
code('''# All analytical choices and seeds are set before any query or summary.
from pathlib import Path
import os, sys, json
ROOT = Path.cwd().resolve()
if not (ROOT / 'src').is_dir():
    ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / 'src'))
PARAMS = {
    'brands': ['Samsung', 'Xiaomi', 'Huawei', 'Sony'],
    'os': 'Android', 'currency': 'EUR',
    'start_year': 2010, 'end_year': 2025,
    'flags': ['ok', 'unit_converted', 'unusual_low', 'unusual_high'],
    'strict_flags': ['ok', 'unit_converted'],
    'min_models': 20, 'min_prices': 10, 'min_coverage': 0.5,
    'min_joint': 10,
    'large_display_in': 7.0,
    'bin_trials': [50, 100, 200], 'bin_width': 100,
    'comparison': ['Samsung', 'Xiaomi'], 'comparison_start': 2015,
    'bootstrap_reps': 5000, 'block_length': 2, 'seed': 20261111,
}
DATABASE = Path(os.environ.get('PHONE_M4_DB', str(ROOT / 'data/phones.db')))
print(json.dumps(PARAMS, indent=2))
print('Database:', DATABASE.relative_to(ROOT).as_posix() if DATABASE.is_relative_to(ROOT) else DATABASE)
''')
md('''## Read-only build and analytical grain

Question: which observations can answer a price/specification question? The SQL pivots current fields to one row per source catalog ID; all joins keep the full latest-snapshot key. Numeric flag lists are bound parameters. OS must be mapped and year must be `ok`. The pipeline stops on repeated analytical fields or new identity mappings rather than silently collapsing them. The relationship scatter is written before coefficients are calculated. Figures use a standard-library SVG backend; there are no network or plotting-package dependencies.
''')
code('''from db import connect
from explore import analyze, database_hash, print_table
before = database_hash(DATABASE)
with connect(DATABASE, read_only=True) as connection:
    RESULT = analyze(connection, PARAMS, ROOT)
assert database_hash(DATABASE) == before, 'Database bytes changed'
print('Read-only analysis completed; database SHA-256 unchanged:', before)
print('Full catalog:', RESULT['catalog_n'], 'Selected cohort:', RESULT['cohort_n'])
print('Duplicate-field and identity checks:', RESULT['audit'])
''')
md('''## 2.1 Raw versus cleaned

Question: how much does trusting SQLite's raw price cast change the mean EUR catalog price by brand? The M2 baseline removes the `About`/`EUR` wrapper and casts the remaining source string without repairing grouped thousands; this is explicitly a naive raw baseline. Cleaned results use the M3 parser and primary flags. Both queries and cohort differences are retained in the report. Neither result establishes MSRP.
''')
code('''for name in ['m4_raw.sql', 'm4_cohort.sql']:
    print(name)
    print((ROOT / 'sql/queries' / name).read_text())
print('M2 raw baseline:')
print_table(RESULT['raw'], ['brand', 'catalog_n', 'n', 'mean_price'])
print('M3 cleaned:')
print_table(RESULT['groups'], ['brand', 'catalog_n', 'price_n', 'mean', 'median', 'p95'])
''')
md('''## 2.2 The question and summary

Question: among the four selected Android brand cohorts, how do typical EUR catalog amounts differ, and how does RAM relate to price where a single configuration is available? The median answers the typical-model question; the mean answers average amount per priced model. P95 describes the expensive tail. Every statistic carries its usable-price count, with catalog counts as the coverage denominator. Brand-wide descriptive aggregates need catalog n >= 20, usable price n >= 10, and >= 50% price coverage; no inference is made for a failed group.
''')
code('''print_table(RESULT['groups'], ['brand','catalog_n','price_n','mean','median','p95','eligible'])
for statistic in ['median', 'mean', 'p95']:
    print(statistic, 'descending:', [r['brand'] for r in sorted(RESULT['groups'], key=lambda r:r[statistic], reverse=True)])
''')
md('''## 2.3 Shape

Question: what features of the distribution would a single summary hide? Three natural EUR bin widths are compared below; EUR 100 is used in the shared-scale histogram. The ECDF removes dependence on bin placement. All priced rows are included for descriptive shape, including thin yearly cells; the figures do not turn those cells into yearly estimates.

![Price histograms](../figures/01_price_histogram.svg)

![Price ECDF](../figures/02_price_ecdf.svg)
''')
code('''print_table(RESULT['bins'], ['width','nonempty_bins','peak_bin_n','upper','n'])
print('Overall priced cohort:', RESULT['overall'])
''')
md('''## 2.4 Coverage and flag sensitivity

Question: which brand-years have enough observed prices to support a summary? The denominator is the landed catalog cohort, not the unknown universe of every released phone. One entity has one latest observation, so its price availability is 0/1; the annual and brand tables sum those indicators. No observation is invented for an absent field. A table with failed groups is retained for auditing, but failed groups do not enter the annual plotted comparison. The 50% coverage and minimum-count rules are pragmatic stability screens, not a guarantee against selection bias. Compare the same equal-year contrast with and without this rule. The strict filter removes unusual values, including legitimate premium devices.

![Coverage by brand and year](../figures/03_coverage.svg)
''')
code('''print_table(RESULT['groups'], ['brand','catalog_n','price_n','joint_n','price_coverage','ram_price_coverage'])
print_table(RESULT['annual'], ['brand','year','catalog_n','price_n','joint_n','price_coverage','eligible'])
print('Primary flags:', PARAMS['flags'])
print_table(RESULT['groups'], ['brand','price_n','mean','median','p95'])
print('Strict flags:', PARAMS['strict_flags'])
print_table(RESULT['strict_groups'], ['brand','price_n','mean','median','p95'])
print('With coverage rule:', RESULT['comparison']['estimate'], RESULT['comparison']['years'])
print('Without coverage rule:', RESULT['without_coverage_rule'])
''')
md('''## 2.5 Announcement cohorts and collection clock

Question: how do annual and five-year device cohorts differ? Announcement year is a source calendar year with no recoverable timezone; it is not a UTC timestamp. It must not be tz-converted or interpreted as a transaction date. Retrieval is explicitly UTC and only documents the collection window. The 2026 announcement cohort is excluded because the collection predates year end. The 2010 left edge and 2025 right edge are inspected in the coverage table; passing a rule does not establish completeness. Annual and five-year medians are cohort patterns, not historical price trajectories. Day-of-week, holidays, and seasonality cannot be tested from year-only dates. Brand within announcement cohort is the alternative grouping structure available here.

![Announcement cohort summaries](../figures/04_announcement_cohorts.svg)
''')
code('''print('Retrieval UTC range:', RESULT['retrieval_range'])
print('Announcement range retained:', RESULT['cohort_year_range'])
print('Boundary brand-years:')
print_table([r for r in RESULT['annual'] if r['year'] in [PARAMS['start_year'],PARAMS['end_year']]], ['brand','year','catalog_n','price_n','price_coverage','eligible'])
print('Five-year cohorts; same flag and coverage rules:')
print_table(RESULT['periods'], ['brand','period','catalog_n','price_n','median','eligible'])
''')
md('''## 2.6 Relationships and drivers

Question: how much of RAM versus price is shared generation/brand structure or a few extremes? Inspect the scatter first. Both coefficients use the same complete pairs; at least 10 pairs are required per brand or brand-year coefficient. Coefficients on all pairs are descriptive complete-case results, with their denominator against the eligible catalog shown above. Sensitivities remove rows above the marginal 99th percentiles, omit one brand at a time, and demean RAM and price within brand-year cells with >= 10 pairs. Spearman on those residuals is a sensitivity, not a formal partial rank coefficient. No missing configuration is parsed or chosen in this notebook.

Device type is a second candidate driver: Android also covers tablets, and the cleaned layer has no device class. Display size is the measured attribute closest to it, so the coefficients are recomputed separately for phone-sized screens and for screens of at least `large_display_in` inches (7.0, the smallest tablet screen among these pairs). The large-screen pairs are listed in full, because a screen-size group is not a device class and nothing here relabels a model.

RAM is recorded at a few discrete levels, so the scatter overplots. The binned view takes each recorded level as a bin and draws the price median and interquartile range for all pairs and for phone-sized screens; a level needs at least `min_joint` pairs to be drawn. It shows where along the RAM axis the association comes from.

![RAM and price by brand](../figures/05_ram_price.svg)

![Median price per RAM level](../figures/07_ram_binned_medians.svg)
''')
code('''print('Overall:', RESULT['relationship'])
print('Trim cutoffs:', RESULT['trim_thresholds'], 'removed:', RESULT['trim_removed'])
print('After trim:', RESULT['trimmed'])
print('Within brand:', json.dumps(RESULT['by_brand'], indent=2))
print('Leave one brand out:', json.dumps(RESULT['leave_one_brand_out'], indent=2))
print_table(RESULT['within_brand_year'], ['brand','year','n','pearson','spearman'])
print('Brand-year demeaned:', RESULT['group_demeaned'])
screens = RESULT['display_split']
print(f"Display split at {screens['threshold_in']} in; pairs without a display size: {screens['display_missing']}")
print_table([dict(group=f"display < {screens['threshold_in']} in", **screens['phone_sized']),
             dict(group=f"display >= {screens['threshold_in']} in", **screens['large_screen'])],
            ['group', 'n', 'pearson', 'spearman'])
print('Large-screen pairs by brand:', screens['large_screen_by_brand'])
print('Large-screen pairs, most expensive first:')
print_table(RESULT['large_screen_pairs'], ['name', 'year', 'display_in', 'ram', 'price'])
print('Price by RAM level (all pairs, then display <', PARAMS['large_display_in'], 'in):')
print_table(RESULT['ram_levels'], ['ram', 'n', 'median', 'q1', 'q3', 'eligible',
                                   'phone_n', 'phone_median', 'phone_eligible', 'year_median'])
''')
md('''## 2.7 A comparison, an interval and a look count

Question: how much larger is Samsung's typical catalog amount than Xiaomi's in common supported years? The primary estimand is the equal-year mean of within-year median differences, with paired two-year circular block bootstrap resampling. This keeps the brands paired and preserves some short-range dependence; only a small number of years are available. The pooled median gap answers a different, mixture-weighted question. We inspect all six pooled brand pairs, then the preselected Samsung/Xiaomi contrast, its annual strata, coverage sensitivity, and flag sensitivity. These are exploratory looks on the same extract, with no multiplicity-adjusted significance claim or held-out test.

![Brand comparison](../figures/06_brand_comparison.svg)
''')
code('''print('Comparison:', json.dumps(RESULT['comparison'], indent=2))
print('All six pooled brand-pair looks:')
print_table(RESULT['all_pairs'], ['a','b','pooled_median_difference','a_n','b_n'])
''')
md('''## 2.8 Findings and decisions

The report is written from these executed results. Attribution is explicitly pending member review; preparation does not establish who explored or can explain a finding. There is no held-out confirmation of the price/specification relationships. The cleaning register is updated with interpretation/selection limits rather than an unsupported new parser fix.
''')
code('''from explore_report import write_report
write_report(RESULT, ROOT)
evidence = {'database_sha256_before':before, 'database_sha256_after':database_hash(DATABASE),
            'database_unchanged':before==database_hash(DATABASE),
            'figure_files':sorted(p.name for p in (ROOT/'figures').glob('*.svg')),
            'parameters':PARAMS}
(ROOT/'docs/m4').mkdir(parents=True, exist_ok=True)
(ROOT/'docs/m4/results.json').write_text(json.dumps(RESULT,indent=2)+'\\n',encoding='utf-8')
(ROOT/'docs/m4/notebook-verification.json').write_text(json.dumps(evidence,indent=2)+'\\n',encoding='utf-8')
print('Wrote report,', len(evidence['figure_files']), 'SVG figures, aggregate results and read-only verification.')
print('Parameters actually used:', json.dumps(PARAMS, sort_keys=True))
''')
notebook=dict(cells=cells,metadata=dict(kernelspec=dict(display_name='Python 3',language='python',name='python3'),language_info=dict(name='python',version='3.12')),nbformat=4,nbformat_minor=5)
for index,cell in enumerate(cells):
    cell['id']='m4-'+str(index).zfill(2)
(ROOT/'notebooks/m4_eda.ipynb').write_text(json.dumps(notebook,indent=1)+'\n',encoding='utf-8')
print('Built notebooks/m4_eda.ipynb')
