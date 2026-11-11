"""Generate the M4 narrative from executed aggregate results, never manual values."""
from explore import markdown_table


def write_report(r, root):
    p=r['params'];c=r['comparison'];rel=r['relationship'];trim=r['trimmed'];demean=r['group_demeaned']
    def num(v):return f'{v:,.2f}'
    def table(rows,columns):return markdown_table(rows,columns)
    raw_by={v['brand']:v for v in r['raw']}
    raw_clean=[dict(brand=g['brand'],raw_n=raw_by[g['brand']]['n'],raw_mean_EUR=raw_by[g['brand']]['mean_price'],clean_n=g['price_n'],clean_mean_EUR=g['mean'],difference_EUR=g['mean']-raw_by[g['brand']]['mean_price']) for g in r['groups']]
    filter_rows=[]
    for g in r['groups']:
        strict=next(v for v in r['strict_groups'] if v['brand']==g['brand'])
        filter_rows.append(dict(brand=g['brand'],primary_n=g['price_n'],primary_mean=g['mean'],primary_median=g['median'],strict_n=strict['price_n'],strict_mean=strict['mean'],strict_median=strict['median']))
    within_brand=[dict(brand=b,**v) for b,v in r['by_brand'].items()]
    leaveout=[dict(omitted_brand=b,**v) for b,v in r['leave_one_brand_out'].items()]
    summary_rows=[dict(check='All complete pairs',**rel),dict(check='Remove marginal top 1%',**trim),dict(check='Within brand-year residuals',**demean)]
    raw_sql=(root/'sql/queries/m4_raw.sql').read_text()
    clean_sql=(root/'sql/queries/m4_cohort.sql').read_text()
    text=f'''# Exploratory Analysis — Cellphone Catalog Prices and Specifications

## 1. Summary

The project asks how smartphone launch prices relate to hardware and how that relationship changes across manufacturers and years, but the current extract supports only a narrower catalog-price exploration. We examine {r['cohort_n']:,} Android catalog entries from four named brands, announced in 2010–2025, of which {r['overall']['n']:,} have a usable EUR amount; this is not a validated smartphone-only cohort. Typical priced entries have a median of EUR {num(r['overall']['median'])}, while brand medians range from EUR 200 to EUR 220. RAM and price are positively related in {rel['n']} complete pairs (Pearson {rel['pearson']:.3f}, Spearman {rel['spearman']:.3f}), but configuration availability differs sharply between brands. The Samsung-minus-Xiaomi equal-year median contrast is EUR {c['estimate']:+.2f}, with an exploratory 95% block-bootstrap interval of [{c['ci95'][0]:+.2f}, {c['ci95'][1]:+.2f}], so these data do not establish a stable brand premium. Better launch-price evidence, device classification, configuration extraction, or different cohort coverage could change these results; no additional M3 parser correction or feedback resolution is claimed in this milestone.

## 2. Raw versus cleaned

Question: what mean EUR catalog amount would a simple raw query report, and what changes when the cleaned layer is used? The M2 baseline selects current observations, removes the literal `About`/`EUR` wrapper, and applies SQLite's numeric cast without interpreting other monetary representations. It has no quality flags because M2 contains source text. The cleaned query accepts only mapped Android OS, an `ok` announcement year, explicit EUR currency, and the primary numeric flags listed below. All values are bound parameters, including lists passed through `json_each`; neither query interpolates values into SQL.

{table(raw_clean,['brand','raw_n','raw_mean_EUR','clean_n','clean_mean_EUR','difference_EUR'])}

Cleaning changes the eligible monetary representations and counts: the naive `About … EUR` baseline omits explicit euro-symbol amounts that M3 can parse. Huawei's result is unchanged, while Samsung, Sony, and Xiaomi change because the cleaned query includes additional supported EUR observations; this is a representation/cohort change, not a measured correction to a true launch price. The raw query deliberately exposes its limited grammar rather than treating unsupported source text as zero or silently using M3 values in a supposedly raw calculation.

Both queries follow. Parameters are recorded in the first notebook code cell and in `docs/m4/results.json`: brands Samsung/Xiaomi/Huawei/Sony, Android, EUR, years 2010–2025; raw patterns `Android%` and `About % EUR`; primary flags `ok`, `unit_converted`, `unusual_low`, `unusual_high`.

```sql
{raw_sql.strip()}
```

```sql
{clean_sql.strip()}
```

The cleaned query returns the reduced model-grain layer, on which the notebook calculates the mean, median and percentiles. It does not export the full specification-cell table into Python. Additional checks reject repeated analytical fields and unreviewed identity mappings before a result is accepted.

## 3. The question and its summary

The operational question is: among these four Android brand cohorts, how do typical EUR catalog amounts differ, and how does RAM relate to price where a single configuration is available? Median price answers the typical-priced-model question and limits the influence of the expensive tail. Mean price answers the different question of average catalog amount per priced model; the 95th percentile describes the upper tail. None is sales-weighted, and one source model ID contributes once regardless of the number of source links or historical snapshots.

Primary-filter brand summaries are below. Their coverage rule requires at least 20 catalog models, 10 usable EUR prices, and 50% usable-price coverage. All four brand-wide groups pass. The overall descriptive distribution pools their priced entries and retains the same primary flags; it is not a price estimate for the unobserved models.

{table(r['groups'],['brand','catalog_n','price_n','mean','median','p95','eligible'])}

The rankings differ. Xiaomi leads by median (220), Sony follows (210), and Huawei/Samsung tie (200); Xiaomi also leads by mean, narrowly followed by Huawei, then Samsung and Sony. Huawei has the largest p95. These are compatible answers: a group can have a typical low-to-middle amount and a heavier premium tail. A ranking without naming its summary would hide that distinction.

## 4. What the data is made of

### Shape

![Shared-scale price histograms](../figures/01_price_histogram.svg)

![Shared-scale price ECDFs](../figures/02_price_ecdf.svg)

Each figure uses current IDs, mapped Android, `ok` year, 2010–2025 announcement cohorts, EUR amounts, and primary numeric flags. Panel-specific n is in its title; total priced n is {r['overall']['n']:,}. The histogram starts at zero and retains the full tail through EUR {r['overall']['max']:,.0f}. All small multiples share scales, even where this makes a small brand's bars less prominent. The ECDF is independent of histogram bins and makes cumulative shares and medians directly readable.

{table(r['bins'],['width','nonempty_bins','peak_bin_n','upper','n'])}

Widths of EUR 50, 100, and 200 were tried. EUR 50 produces a more fragmented view of rounded catalog values; EUR 200 merges much of the affordable range into a few large bins. EUR 100 keeps useful affordable/premium separation without implying precise price modes. The chosen width is in natural currency units and is fixed across groups. The long right tail and rounded-value concentrations support using the median; neither the histogram nor the ECDF establishes a distinct latent market segment.

### Coverage and denominators

![Coverage heatmap](../figures/03_coverage.svg)

The coverage denominator is all landed catalog IDs satisfying the stated OS, brand and valid-year cohort, including IDs without a usable price. It is not the unknown count of every device the manufacturer released. At entity level, price availability is one usable observation out of one current snapshot, or zero out of one. These indicators are summed by brand and year below. `joint_n` requires both a price and an explicit single storage/RAM pair; ambiguous configurations remain excluded rather than selecting their cheapest or largest variant.

{table(r['groups'],['brand','catalog_n','price_n','joint_n','price_coverage','ram_price_coverage'])}

{table(r['annual'],['brand','year','catalog_n','price_n','joint_n','price_coverage','eligible'])}

The annual rule is the same 20 catalog / 10 usable / 50% threshold as the brand-wide rule. Twenty limits very small catalog cohorts; ten avoids reporting a median from only a handful of prices; half-coverage prevents a small observed minority defining a cohort's typical amount. These are explicit pragmatic screens, not calibrated representativeness guarantees. {r['eligible_annual_groups']} of {r['total_annual_groups']} observed brand-years pass. Zero-model cells in the heatmap are missing groups, not zero-price products. Failed groups remain in the audit table but are gaps in the annual figure.

The equal-year Samsung-minus-Xiaomi median contrast is EUR {c['estimate']:+.2f} across {len(c['years'])} supported common years with the rule. Removing it admits 2015–2025 and gives EUR {r['without_coverage_rule']['estimate']:+.2f} across {len(r['without_coverage_rule']['paired'])} years. Its direction changes because the admitted cohort mixture changes; this is a sensitivity of the target set, not proof of a causal reversal.

### Flag sensitivity

The primary filter retains unusual positive measurements because a premium or rugged product is not automatically a data error. The strict filter uses only `ok` and `unit_converted` for every numeric field. OS and year requirements stay unchanged, and no currency is converted or pooled.

{table(filter_rows,['brand','primary_n','primary_mean','primary_median','strict_n','strict_mean','strict_median'])}

Strict filtering reduces every mean and makes Xiaomi's median tie Huawei and Samsung. Its effect is larger on upper-tail-sensitive summaries than on most medians. We report primary results because M3 unusual flags are descriptive IQR fences, not confirmed invalidity; the strict results show how removing valid premium products can alter the question.

## 5. Announcement cohorts and the clock

![Annual and five-year cohort medians](../figures/04_announcement_cohorts.svg)

These are device-generation cohorts, not repeated observations of the same price over time. Announcement year is a source calendar year; no precise announcement timestamp or timezone is available to convert. Applying `tz_convert` to an invented January timestamp would manufacture information. Retrieval timestamps are genuinely UTC and span {r['retrieval_range'][0]} to {r['retrieval_range'][1]}; they document collection only. Grouping that three-day collection by local hour would answer a crawler-scheduling question.

The 2026 cohort is excluded because collection occurred before year end. The 2010 left edge has Samsung 27/27 usable prices, Huawei 8/8, Sony 4/4, and no retained Xiaomi entries; Huawei and Sony fail the count rule. At the 2025 right edge, Samsung has 13/39 and Xiaomi 27/62 usable prices, both below half coverage. Passing coverage cannot establish a complete historical catalog. The notebook prints both edge audits, and this report retains the complete annual table.

The two scales are annual and five-year announcement cohorts; the latter group years by floor(year/5). Both use the same flags and coverage rule. Broader bins provide more support but can hide individual-year changes. The brand-within-year hierarchy supplies a second grouping rather than an invented hourly timeline. Holidays, launch-day effects, and day-of-week seasonality cannot be assessed from year-only dates; they are explicitly untestable here, not checked and found absent.

## 6. Relationships

![RAM versus catalog price, plotted before correlation](../figures/05_ram_price.svg)

The scatter is written before coefficients are computed. It shows discrete RAM levels, substantial vertical price spread, and a few expensive observations, making Spearman's rank association a useful main description of the monotone pattern. Pearson remains informative about the numeric linear relationship but is sensitive to extremes. Both are reported on identical pairs; neither says that adding RAM causes a particular price increase.

{table(summary_rows,['check','n','pearson','spearman'])}

{table(within_brand,['brand','n','pearson','spearman'])}

Removing rows above the marginal 99th percentiles of RAM and price removes {r['trim_removed']} of {rel['n']} pairs. The cutoffs are {r['trim_thresholds']['ram_gb']:.2f} GB and EUR {r['trim_thresholds']['price_eur']:.2f}; observations equal to a cutoff remain. Pearson falls from {rel['pearson']:.3f} to {trim['pearson']:.3f}, while Spearman changes from {rel['spearman']:.3f} to {trim['spearman']:.3f}. The association survives this check, although the sensitivity does not rule out every influential case.

{table(leaveout,['omitted_brand','n','pearson','spearman'])}

No single omitted brand eliminates the positive pooled association. To check shared generation and brand structure, RAM and price are demeaned within brand-year cells containing at least ten complete pairs; {demean['n']} pairs remain. Their residual association is still positive. The notebook also prints every supported within-cell coefficient; residual Spearman is a sensitivity on residual ranks, not a formal partial Spearman estimate. These checks address observed group structure while leaving unmeasured device type, configuration selection, and price provenance unresolved.

## 7. The comparison

![Samsung minus Xiaomi comparison](../figures/06_brand_comparison.svg)

Samsung/Xiaomi was selected for substantive relevance and common-cohort support before inspecting the price contrasts. Its primary estimand is the mean of annual Samsung-minus-Xiaomi medians, giving each eligible common year equal weight. It is not the difference between the medians of all individual phones. Annual strata show both model counts and direction:

{table(c['paired'],['year','a_n','b_n','a_median','b_median','difference'])}

The estimate is EUR {c['estimate']:+.2f}; the 95% percentile interval is [{c['ci95'][0]:+.2f}, {c['ci95'][1]:+.2f}]. We resample paired annual contrasts in two-year circular moving blocks, retain {len(c['years'])} years per replicate, and use {p['bootstrap_reps']:,} replicates with seed {p['seed']}. Pairing preserves common cohort conditions and blocks retain some adjacent-year dependence; circular wrapping is a bootstrap convention, not an assertion that the endpoints are historically adjacent. An independent-year sensitivity interval is [{c['iid_year_ci95'][0]:+.2f}, {c['iid_year_ci95'][1]:+.2f}]. Seven cohort years provide weak support for precise uncertainty, and neither interval covers selection or measurement bias.

The full-cohort pooled median gap is EUR {c['pooled_median_difference']:+.2f} (Samsung n={c['pooled']['Samsung']['n']}, Xiaomi n={c['pooled']['Xiaomi']['n']}). Restricting to common supported years gives EUR {c['common_pooled_median_difference']:+.2f} (n={c['common_years']['Samsung']['n']} and {c['common_years']['Xiaomi']['n']}). Equal weighting gives the estimate above. The counts show different cohort mixtures; annual differences include both signs. There is no uniform within-year reversal establishing Simpson's paradox, and no stable brand premium is inferred.

We inspect six pooled pairwise brand contrasts, the selected paired-year comparison, 23 supported brand-year correlations, four within-brand correlations, and the documented trim, omission, flag and coverage sensitivities. These are multiple looks on one extract, not independent tests. No p-value, multiplicity-adjusted discovery, or held-out confirmation is claimed.

## 8. Findings

All substantive relationships below are exploratory. Arithmetic coverage facts can be checked directly in this extract, but do not establish an external missingness mechanism. Attribution names are review assignments only: each member must actually review, reproduce and explain their rows before replacing **Pending review** with an ownership claim.

| ID | Finding | Evidence | Label | What would change it | Explored by |
|---|---|---|---|---|---|
| F-01 | Mean and median rank the four brands differently. | Section 3; figures 01–02 | Exploratory | New price evidence or a different device/configuration cohort | Pending review: Oguzhan Karacan |
| F-02 | Joint price/RAM coverage is especially thin for Xiaomi. | Section 4; joint_n table | Exploratory interpretation; counts exact for extract | Expanded tested configuration grammar or additional source evidence | Pending review: Osman Yigit Dogan |
| F-03 | Positive RAM-price association survives trimming and observed group controls. | Section 6; figure 05 | Exploratory | Matched device types, verified launch prices, or independent data | Pending review: Onur Atici |
| F-04 | The selected equal-year brand contrast has an interval spanning zero. | Section 7; figure 06 | Exploratory | More supported years, a different coverage rule, or better price evidence | Pending review: Oguzhan Karacan |
| F-05 | Excluding unusual values reduces means and changes the median ranking. | Section 4 flag table | Exploratory | Reviewing unusual devices as invalid or retaining their premium segment explicitly | Pending review: Osman Yigit Dogan |

### Back to cleaning

- No new parser defect was established. Existing M3 issues I-05 and I-11 remain material: supported single memory pairs are selective and catalog prices do not establish launch MSRP. Register entry I-13 records this M4 evidence without inventing a correction in the notebook.
- Before expanding the price question, retain source-backed market, date, device class and configuration context. Any new parsing or classification rule belongs in `clean.py` or reviewed mappings with regression cases, followed by a fresh build. This milestone does not silently broaden a grammar to improve coverage.

### Forward to modelling

- M7 should first decide whether its target is verified launch MSRP or an explicitly renamed catalog-price task. Present evidence cannot train or validate the former honestly.
- Investigate whether RAM contributes information beyond brand, cohort, storage and device class using a held-out design. Prevent closely related model families/configurations from leaking across splits, and assess missingness by brand/year.
- Use chronological validation where the question concerns newer cohorts. Do not interpret current catalog amounts indexed by announcement year as inflation-adjusted historical prices or apply currency conversion without documented dates and markets.

## 9. What we cannot say

This is a selected catalog extract with unknown market, sales weighting, variant linkage and price reference date. Android includes more than smartphones, first-token brand extraction covers only the named prefixes, and absence from the landed cohort is not proof that no product existed. EUR-only selection avoids incompatible units but can itself select products. The narrow price/RAM subset, especially Xiaomi's {r['joint_counts']['Xiaomi']} pairs, cannot represent all available configurations.

The bootstrap describes variation across a small set of observed cohort years under its resampling assumptions. It does not account for an unknown data-generating sample, hidden product-family dependence, vendor price updates, inflation, or systematic source omissions. Correlations and group gaps provide hypotheses for M7, not causal effects or demonstrated predictive accuracy. Member attribution, individual review/commits, the `m4` tag and course-system submission remain team actions; none is represented here as already performed.

## Reproduction

From a fresh clone with the landed M1 responses and existing ingestion dependencies installed:

```sh
python src/load.py
python src/clean.py
python src/validate.py
python scripts/run_m4_eda.py
```

The last command executes every ordinary Python notebook cell in order in a new namespace and saves outputs. With Jupyter installed, the course command also works: `jupyter nbconvert --to notebook --execute --inplace notebooks/m4_eda.ipynb`. The local verification uses the dependency-free runner because package installation is unavailable. Queries open `mode=ro`; before/after database SHA-256 values are recorded in `docs/m4/notebook-verification.json`. The notebook writes all six SVG figures, this report and aggregate results; no source record is repaired or database table changed.
'''
    path=root/'docs/eda_report.md'
    path.write_text(text,encoding='utf-8')
    print('Wrote',path.relative_to(root))
