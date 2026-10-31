# Cleaning Report - Cellphone Launch Prices and Specifications

## 1. Summary

This investigation uses the offline M2 database containing 14,877 GSMArena catalog models, 598,283 specification cells, and supporting Wikidata and Wikipedia records. The main problems are absent price evidence, configuration lists that cannot be reduced to one memory measurement, catalog prices without verified launch context, and identities that are not one-to-one across sources. Five announcement strings also contain a release year earlier than their announcement year. The M3 layer retains every model and specification cell, preserves its source value, and adds normalized text, conservative numeric measurements, OS categories, and constrained flags without imputing values. All M2 table-content hashes remain unchanged, repeated cleaning produces identical contents, and validation passes its STOP checks while reporting coverage and interpretation warnings. Team investigation attribution and the M2-feedback section are intentionally deferred for the group to complete; no claim of member ownership or feedback resolution is made here.

## 2. Profile highlights

The executable investigation is [m3_profile.ipynb](../notebooks/m3_profile.ipynb). It runs against M2 alone: neither the cleaned tables nor an internet connection is required. Its raw counts are separated from provisional numeric parsing. Announcement-year groups describe device cohorts, whereas retrieval timestamps describe the collection window; they are not interchangeable timelines.

| M2 table | Rows | Grain |
|---|---:|---|
| raw_file | 15,565 | Landed response |
| phone | 14,877 | Catalog source ID |
| phone_snapshot | 14,881 | Model and retrieval timestamp |
| specification | 598,283 | Snapshot and source cell ordinal |
| wikidata_item | 2,539 | QID |
| phone_item_link | 2,566 | Model-QID association |
| wikipedia_article / article_revision | 1,806 each | Page / page-revision timestamp |
| quarantine | 11 | Rejected source record |

| Current field | Present cells | Absent models | Source NULL cells | Usable numeric cells |
|---|---:|---:|---:|---:|
| price | 10,352 | 4,525 | 0 | 9,892 |
| year | 14,877 | 0 | 14 | 14,745 |
| internalmemory | 13,041 | 1,836 | 0 | 5,637 |
| weight | 14,877 | 0 | 91 | 13,118 |
| displaysize | 14,877 | 0 | 1,213 | 13,645 |
| batdescription1 | 14,877 | 0 | 15 | 13,419 |
| os | 11,044 | 3,833 | 0 | Not a numeric field |

The notebook regenerates detailed local CSVs: every distinct specification string with `repr()`, entity first/last appearance, rows per entity, per-entity/field missing counts and min/median/max, and source names/URLs with `repr()`. Numeric summaries never pool different currencies. These detailed source-derived extracts are ignored by Git, like the raw responses; reproducible code, aggregate outputs and representative examples remain in the repository. Per-entity numeric summaries generally contain one observation, so their min, median and max coincide and do not establish stability over time.

The profile deliberately uses the complete catalog as its coverage denominator rather than only models already linked to Wikidata. Restricting the denominator to linked models would conceal unlinked entities and make cross-source coverage look better. Likewise, a present price row is not automatically a usable amount: the first count measures source coverage, while the second measures supported interpretation. The exported source IDs let a reviewer inspect any unusual or unsupported example in its original M2 snapshot and landed response. Re-running the notebook after a mapping change refreshes all summaries instead of leaving a hand-maintained spreadsheet of exceptions.

## 3. Issues register

The Investigated by column is deliberately pending, as requested. Counts in this register use current model cells unless identified as all observations.

| ID | Family | Table.column | Finding and extent | Evidence | Cause | Decision / flag | Investigated by |
|---|---|---|---|---|---|---|---|
| I-01 | Missing | specification.price | 4,525 models have no price cell | Notebook coverage against all phone keys | Unknown provider omission; cohort dependence observed | No synthetic cell or price; absent fields remain absent | Pending |
| I-02 | Missing | specification.value_text | 12,045 NULL cells; 3,043 explicit tokens across all snapshots | `N/A`: 1,499; `-`: 1,544 | Confirmed representation in M2; reason unknown | NULL with separate missing_not_reported / missing_token flags | Pending |
| I-03 | Invalid / across fields | specification.year | Five release-before-announcement year conflicts | Source IDs 2893, 10619, 7098, 4783, 4784 | Unknown; contradictory chronology, not a proven corrected date | Numeric year NULL, invalid_year; text retained | Pending |
| I-04 | Unusual | specification numeric fields | Positive extremes include large tablets and rugged devices | HP Slate 17: 2,005 g and 17.3 inches; Ulefone Armor Pad 3 Pro: 33,280 mAh | Inferred product heterogeneity from names and specifications | IQR flag; keep measurement | Pending |
| I-05 | Text / units | specification.internalmemory | 4,881 ambiguous lists and 2,523 unsupported current strings | Configuration separators and storage-only/legacy forms | Confirmed source structure; individual interpretation unresolved | NULL numeric pair; ambiguous or unparsed | Pending |
| I-06 | Text / units | specification.price | 460 current strings cannot establish one supported amount/currency | Multiple offers or unsupported/ambiguous monetary notation | Confirmed source syntax; offer context unknown | Numeric NULL; ambiguous/unparsed | Pending |
| I-07 | Identity | phone_item_link | 24 models link to multiple QIDs; 37 QIDs link to multiple models | Grouped source-ID counts | Inferred entity/family granularity differences; specific causes unknown | Preserve links, no automatic identity merge | Pending |
| I-08 | Identity | phone.name | Normalized `vivo y11` occurs under IDs 7219 and 14564 | Exact normalized-name collision | Unknown from name alone | Keep both IDs; empty identity decision file | Pending |
| I-09 | Across rows | phone_snapshot | One model has five snapshots; 14,876 have one | Sorted observations and first/last timestamps | Confirmed collection pattern | No unsupported stuck/spike/level-shift correction | Pending |
| I-10 | Identity / coverage | article_revision.content | 237 redirect revisions | Case-insensitive leading `#redirect` check | Confirmed redirect syntax | Keep M2 text; do not treat redirect as price evidence | Pending |
| I-11 | Interpretation | specification.price | No source-verified launch/market/configuration linkage | M2 schema and price text | Unknown price reference date and context | Catalog amount only; persistent MSRP warning | Pending |

### Checked and not found

| Family | Check | Result |
|---|---|---|
| Invalid | Parsed positive-quantity rules, excluding NULL/unsupported text | No source nonpositive measurements after correct grouped-number parsing |
| Invalid | Complete announcement dates later than their retrieval day | 0 |
| Text | NFC and collapsed-whitespace changes to all model names and specification values | 0 changes needed |
| Identity | Wikipedia pages without a retained QID reference | 0 |
| Across rows | `PRAGMA foreign_key_check` | 0 violations |
| Missing coverage | All resolved models observed within 30 days of latest landed observation | 0 outside window |

The initially apparent zero battery was a parser defect: `16,000 mAh` must parse as 16,000, not as its final digits. A regression test now covers this case and rejects malformed grouping. It is not reported as a source error.

## 4. Missing values

Price absence is strongly associated with observable cohorts. All 82 models with a usable 2000 announcement year lack price text, compared with 61 of 669 in 2020. OS grouping also differs: 1,872 of 9,572 Android-group models lack price text, compared with 2,424 of 4,277 models with absent or unmapped OS. These patterns oppose an MCAR interpretation. MAR conditional on observed age/product characteristics is an inference worth testing, not an established mechanism. MNAR remains possible if difficult-to-price, obscure or discontinued products are preferentially omitted; this extract cannot distinguish those explanations. M4 must show cohort-specific denominators and cannot generalize a complete-case price distribution to the whole catalog.

Explicit tokens and NULL cells describe different observed representations, not known maintenance or collection causes. Their underlying mechanism is unknown; neither MCAR nor a substantive failure cause is assumed. The text `No` occurs 47,859 times and remains meaningful, rather than becoming NULL. Absent fields are counted separately from present empty cells. No missing sensor or maintenance mechanism is invented for this catalog.

Memory availability combines source absence with deliberate parser restraint. A single explicit storage/RAM pair supplies two measurements, while multiple configurations supply no chosen pair. Storage-only or legacy forms do not establish both quantities under this rule. All 81 mapped iOS models fail the joint pair rule, illustrating that parser-induced missingness depends on observed source format and OS. This is a deterministic selection mechanism resembling MAR conditional on format, with additional source omissions of unknown mechanism. It is not evidence that those devices lack RAM or storage. Future extraction can expand supported grammars with tests, but M4 must not compare the retained subset as if it were representative.

## 5. Flags and rules

Cleaning first loads reviewable mappings, resolves supplied identity decisions, normalizes text, recognizes missing representations, parses units, checks invalid quantities and chronology, and finally applies robust fences. The first applicable missing/invalid rule wins. Unusual flags are applied only to retained numeric values; when storage and RAM both qualify, storage's unusual flag takes precedence. Conversion remains observable from source text and units even when an unusual flag takes precedence over unit_converted.

| Order | Flag | Rule and cleaned result | All-observation count |
|---|---|---|---:|
| 1 | missing_not_reported | Source NULL; normalized text remains NULL | 12,045 text cells |
| 2 | missing_token | Explicit empty/unknown marker; normalized text NULL | 3,043 text cells |
| 3 | text_normalized | NFC/whitespace change; normalized text | 0 |
| 4 | not_applicable | No numeric field rule; numeric NULL | 515,358 |
| 5 | unparsed | Unsupported measurement grammar; numeric NULL | 3,686 |
| 5 | ambiguous | Multiple/ambiguous configurations or amounts; numeric NULL | 6,290 |
| 6 | invalid_year | Outside calendar bounds, invalid exact day, future exact date, or contradictory chronology; numeric NULL | 5 |
| 6 | invalid_nonpositive | Nonpositive parsed measurement; numeric NULL | 0 |
| 7 | unit_converted | Explicit MB/TB converted to GB; value retained | 1,309 |
| 8 | unusual_low / unusual_high | Outside cohort IQR fence; measurements retained | 258 / 4,155 |
| Otherwise | ok | Trusted under supported grammar | 64,754 numeric cells |

Numeric missing_not_reported and missing_token counts are respectively 1,333 and 1,135, subsets of the text missingness above. Category flags are mapped (10,604), unmapped (444), or not_applicable (587,235). Name flags are ok for all 14,877 models. These columns have independent denominators; their counts should not be added together.

`phone_clean` has the phone key and grain; `specification_clean` has the full specification composite key and grain. Text, numeric and category groups each retain their exact M2 source string. `number_raw` and `number_flag` jointly cover the parsed number, optional RAM measurement and unit because they come from one indivisible source cell; this is the justified group-level flag permitted by the brief. Other M2 tables are not transformed, so no redundant clean copies are created. Every M3 table is STRICT; entity-bearing tables declare foreign keys. Mapping dictionaries are loaded from CSVs, not embedded identity/category decisions.

### Constants

| Constant | Value and justification / sensitivity |
|---|---|
| MIN_YEAR | 1900: deliberately broad calendar screen, not a historical first-phone assertion; no current valid year is near it |
| MEMORY_UNIT_BASE | 1000: explicit SI-prefix conversion; no inference of GiB/MiB |
| NUMBER_PATTERN | Comma-grouped thousands and dot decimals; other locale syntax remains unsupported |
| IQR_FACTOR | 1.5: exploratory Tukey screening; changing it changes flags, not measurements |
| MIN_COHORT | 20: pragmatic small-sample guard, not an empirically optimal cutoff; smaller groups receive no fence |
| MISSING_WARN_SHARE | 0.30: makes losing roughly a third of available fields visible; never excludes a model |
| COVERAGE_DAYS | 30: broad within-extract coverage window relative to latest observation; not a live-feed freshness claim |
| MISSING_TOKENS | Empty, -, n/a, na, unknown after comparison normalization; No is intentionally excluded |
| NUMERIC_FIELDS | The six project-relevant measurement fields; other specifications remain normalized text |

The 56 supported cohorts separate field, currency/unit and observed OS family; RAM gets separate fences from storage. Zero-IQR cohorts receive no fence. Canonical representatives are chosen before estimating fences if an identity map is supplied. Flagged examples include tablets and rugged hardware; their source strings support retaining extremes, while their exact correctness remains unverified. These cohorts still mix years, manufacturers and form factors, so unusual means review, not error. A threshold-change test widens the fence, checks that only numeric flags change, then restores the original complete contents.

## 6. Mapping and identity decisions

The committed [mapping CSVs](../data/mappings/) contain six field rules, eleven OS aliases, seven currency aliases, and no accepted identity merges. Metadata identifies the decisions as automated reproducible rules; human review attribution remains for the group. OS matching uses exact normalized keys, then a boundary-delimited prefix, with the longest matching alias winning. Normalization is NFC, explicit Turkish-letter folding, then casefold. Currency amounts require a complete single-amount grammar; a bare dollar symbol does not establish currency or market.

Across all observations, 10,604 OS cells map and 444 remain unmapped. No fuzzy proposals are accepted. The configured iPhone OS alias has no match, and literal USD and GBP tokens do not occur; the pound symbol does occur. All six field rules match observed fields. Empty phone_identity.csv is intentional: matching names or a shared QID is insufficient merge evidence. The resolved views retain original keys and expose canonical keys without dropping rows; source IDs in CSV are looked up at load time. Identity chains/cycles and unmatched identity IDs fail visibly rather than creating parents.

## 7. Counts and validation

The complete final outputs are [first cleaning run](m3/clean-first.txt), [second cleaning run](m3/clean-second.txt), and [validation](m3/validate.txt). Both clean runs report COMPLETE. The [hash evidence](m3/verification.json) compares every complete M2 table before/after and all six M3 tables between runs; both comparisons pass. [Regression results](m3/tests.txt) record 35 passing tests. The notebook is also executed against a newly built full M2 database, rather than relying on existing clean tables; the [fresh-build comparison](m3/fresh-build-check.json) confirms all nine rebuilt M2 tables match the original hashes.

| Final result | Interpretation |
|---|---|
| All seven STOP expectations pass | Counts/grain, raw keys, numeric rules, foreign keys, STRICT tables, exact source companions, flag/value consistency |
| Price unavailable 33.5%; joint memory unavailable 62.1% | Measurement/source-format coverage problem; no imputation |
| 4,872 models exceed 30% unavailable numeric fields | Measurement/heterogeneous-product coverage; diagnostic, not deletion criterion |
| 460 price strings unresolved | Source interpretation / conservative parser limitation |
| 24 models have multiple QIDs | Source identity granularity uncertainty |
| No verified launch MSRP linkage | Evidence limitation, not pipeline failure |
| Within-extract coverage passes | All models represented in the expected snapshot window |

Each STOP is deliberately failed on a temporary database copy, and the CLI must print STOP and exit nonzero:

| STOP check | Injected failure |
|---|---|
| Counts/grain | Delete a clean specification row |
| Raw keys | Change a clean source-row key without changing count |
| Numeric validity | Set a clean price to -1 |
| Foreign keys | Insert an orphan clean model with enforcement disabled for injection |
| STRICT | Add a non-STRICT test table |
| Exact raw companions | Alter name_raw |
| Flag/value agreement | Mark a retained price ambiguous without nulling its number |

Atomicity tests inject an actual SQLite trigger failure partway through insertion and compare all prior M3 contents and M2 hashes. A separate first-build failure verifies schema creation rolls back too. WARN-only runs exit successfully. Cleaning failures roll back and return nonzero; the production scripts never edit M2 or call an API.

## 8. What we cannot say

Cleaning does not turn a catalog price into launch MSRP. We still lack verified price date, region, tax treatment and configuration linkage. Currencies stay separate; no exchange rates, inflation adjustment, filled memory values or inferred launch dates are introduced. M4 must establish an eligible smartphone cohort before describing smartphones: the catalog contains tablets, watches and feature phones, and an OS label alone does not settle device class.

The handful of repeated model observations cannot support sensor-style stuck, spike or level-shift claims. Announcement years can remain unsupported or contradictory, and a release-before-announcement conflict does not reveal which date is correct. Wikidata and Wikipedia associations can describe families, variants or redirects. Their presence increases provenance coverage but does not independently verify a price. Complete-case comparisons can inherit source omissions and grammar selection, particularly across eras and OS groups. These limitations must remain visible in M4 rather than disappearing behind a cleaned-table name.

Any later manual investigation should add evidence to a mapping CSV and change a tested rule, rather than overwrite a cleaned cell. This preserves the ability to rebuild earlier decisions and compare their consequences. New category aliases should be reviewed for overly broad matches, and an identity proposal should explain why two source identifiers refer to the same model rather than merely sharing a family name. Expanding a numeric grammar also changes the population eligible for analysis, so its new coverage counts belong in the next quality review.
