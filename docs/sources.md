# Data sources

The counts and timestamps below were measured during the first full ingestion run, from 2026-10-09 to 2026-10-11. All times are UTC. A phone's currently displayed price is not evidence of its original launch MSRP.

The three sources join in a chain. A GSMArena phone page carries a numeric phone ID. Wikidata records that ID on its item for the same phone (property P4723). The Wikidata item links to the phone's English Wikipedia article.

## GSMArena

| Field | Value |
| --- | --- |
| source_name | GSMArena phone catalog and model pages |
| provider | GSMArena.com (Arena Kom OOD) |
| url | https://www.gsmarena.com/makers.php3 (brand index). One page per model, for example https://www.gsmarena.com/apple_iphone_13-11103.php |
| access_method | Public web pages over HTTPS; no API and no key. The site sends non-browser clients to its mobile host, m.gsmarena.com, so that is what the script requests and saves. |
| licence | No open data licence. "Copyright 2000-2026 Arena Kom OOD. All Rights Reserved." |
| terms_notes | https://www.gsmarena.com/terms.php3 allows downloading and copying pages "solely for personal, informational, non-commercial purposes", unmodified, and forbids publishing or distributing them without written permission; do not publish raw pages. robots.txt does not disallow the brand and model pages, but robots rules alone do not grant permission to collect them. https://www.gsmarena.com/license.xml asks for attribution and prohibits use for AI training. |
| update_cadence | Continuous. New models appear as they are announced and existing pages are edited; no schedule is stated. |
| coverage | Historical and current models: 126 brands and 14,877 model pages on 2026-10-10, from the 1990s to 2026. |
| record_meaning | One saved file is one HTML page. A model page describes a model or variant; a listing page lists the models of one brand. |
| join_key | GSMArena phone ID, the number that ends the page address (`...-11103.php`), where Wikidata property P4723 exists; otherwise manually reviewed manufacturer and model |
| first_retrieved | 2026-10-09T13:02:22Z |
| known_issues | Launch MSRP may be absent or confused with a later retail price; regional names and variants differ. Catalog includes tablets and watches. Details below. |

Found during the first full run:

- **Rate limit.** One address gets about 7.5 pages a minute. Past that, the site answers with HTTP 200 and the text "please slow down" instead of 429. The script recognises that text, waits 60 seconds and retries. A full crawl takes about 34 hours.
- **No API.** Discovery depends on the shape of links in the HTML, so a layout change would break it.
- **Page addresses are irregular.** 931 model addresses contain punctuation such as `+`, `(`, `)`, `&` or `@`. One contains square brackets and only works when requested unencoded; the encoded form redirects without end.
- **Listings hold links that look like models.** Brand pages link to filter pages such as `apple-phones-f-48-15.php`, which the script excludes.
- **Pages are renamed.** One model page changed its address during the crawl. The raw folder can therefore hold two copies of one phone; M3 must keep one per phone ID.
- **Duplicates in the raw folder.** Early runs fetched some brand listings more than once, and one early response is a 49-byte "please slow down" body (`20261009T131244120996Z_000621.html`) saved before the check existed. Raw files are never deleted, so M3 must pick the newest valid copy of each page.
- **The price is not a launch price.** Of the 2,542 models that Wikidata links to, 2,122 have a price. For 93% of those it is a rough estimate such as "About 140 EUR"; for the rest it is a current shop price in several currencies.
- **Free text and gaps.** Every field is text written for readers, such as "146.7 x 71.5 x 7.7 mm (5.78 x 2.81 x 0.30 in)". Older phones lack many fields: among the linked models, 29% have no operating system entry.

## Wikipedia

| Field | Value |
| --- | --- |
| source_name | English Wikipedia phone articles |
| provider | Wikimedia Foundation and Wikipedia contributors |
| url | https://en.wikipedia.org/w/api.php |
| access_method | MediaWiki Action API (`action=query`, `prop=revisions\|pageprops`), JSON results, 25 titles per request; no key; descriptive User-Agent required |
| licence | Article text: CC BY-SA 4.0; verify attribution and any separately licensed media before reuse |
| terms_notes | API policy and attribution apply; the text may be redistributed with attribution under the same licence. Raw responses (17 MB) are kept locally and excluded from Git; they regenerate in a few minutes. |
| update_cadence | Articles are edited continuously. Each saved page carries the timestamp of the revision that was current. |
| coverage | The 1,806 English articles that the Wikidata items link to (2026-10-09) |
| record_meaning | One API page object holds the current wikitext and page properties of one article |
| join_key | Wikidata QID through the page's associated Wikibase item (`pageprops.wikibase_item`) |
| first_retrieved | 2026-10-09T13:18:04Z |
| known_issues | Some pages cover a family rather than a single model; infobox fields and MSRP evidence vary. Details below. |

Found during the first full run:

- **Redirect pages.** 237 of the 1,806 titles are redirects. The request does not ask the API to follow them, so those responses hold only `#REDIRECT [[Target]]` and not the article.
- **No infobox.** 66 real articles have none. Where one exists, its fields are free wikitext with inconsistent names and units.
- **Launch prices are rare.** About 20 infoboxes have a price field.

## Wikidata

| Field | Value |
| --- | --- |
| source_name | Wikidata phone entities |
| provider | Wikimedia Foundation and Wikidata contributors |
| url | https://www.wikidata.org/wiki/Wikidata:Data_access (query endpoint: https://query.wikidata.org/sparql) |
| access_method | Wikidata Query Service (SPARQL over HTTPS, JSON results); no key; descriptive User-Agent required |
| licence | Structured Wikidata data: CC0 1.0 |
| terms_notes | Follow Wikimedia API usage limits and identify the client. The data may be redistributed freely; it is excluded from Git anyway so that all raw data is handled the same way. |
| update_cadence | Entities are edited continuously |
| coverage | Every item with a GSMArena phone ID (P4723): 2,576 rows, 2,539 items and 2,552 distinct GSMArena IDs on 2026-10-09 |
| record_meaning | One result row is one Wikidata item, one GSMArena phone ID and, where it exists, the address of the item's English Wikipedia article. An item sometimes represents a family or variant. |
| join_key | QID to Wikipedia; GSMArena phone ID (P4723) where present |
| first_retrieved | 2026-10-09T13:12:53Z |
| known_issues | Missing specifications and price claims; an unqualified price (P2284) is not necessarily launch MSRP. Details below. |

Found during the first full run:

- **Partial coverage.** 2,542 of GSMArena's 14,877 models (17%) have a Wikidata item with this ID, and they lean towards well-known models.
- **Not one-to-one.** 37 items list more than one GSMArena ID and 24 IDs appear on more than one item, so the join needs a link table.
- **Stale IDs.** 10 IDs in Wikidata match no page in GSMArena's current listings.
- **Paging over live data.** Results come 500 rows at a time with LIMIT and OFFSET. An edit between two pages could shift a row; the query orders by item to keep that unlikely.
- **Narrow query.** Only the ID and the article link are requested. Other properties, such as price (P2284) or dates, would need a wider query.
