# Data sources

These are initial source cards. Confirm the coverage, first retrieval timestamps and access terms during the M1 ingestion work. A phone's currently displayed price is not evidence of its original launch MSRP.

## GSMArena

| Field | Value |
| --- | --- |
| source_name | GSMArena phone catalog and model pages |
| provider | Arena Kom OOD |
| url | https://www.gsmarena.com/makers.php3 |
| access_method | Public web pages; automated collection pending confirmation of terms and instructor approval |
| licence | No open data licence established |
| terms_notes | https://www.gsmarena.com/terms.php3 restricts use and redistribution; do not publish raw pages. Robots rules alone do not grant permission to collect them. |
| update_cadence | New models appear over time; exact schedule not stated |
| coverage | Historical and current phone models; exact usable count to measure |
| record_meaning | One source page describes a model or variant |
| join_key | GSMArena phone ID where Wikidata property P4723 exists; otherwise manually reviewed manufacturer and model |
| first_retrieved | Pending |
| known_issues | Launch MSRP may be absent or confused with a later retail price; regional names and variants differ. Catalog may include tablets and watches. Automated access has not been confirmed. |

## Wikipedia

| Field | Value |
| --- | --- |
| source_name | English Wikipedia phone articles |
| provider | Wikimedia Foundation and Wikipedia contributors |
| url | https://en.wikipedia.org/w/api.php |
| access_method | MediaWiki Action API; descriptive User-Agent required |
| licence | Article text: CC BY-SA; verify attribution and any separately licensed media before reuse |
| terms_notes | API policy and attribution apply; raw responses are kept locally and excluded from Git. |
| update_cadence | Articles are edited continuously |
| coverage | Phone model and family articles; exact count to measure |
| record_meaning | One API page response describes an article or revision |
| join_key | Wikidata QID through the page's associated Wikibase item |
| first_retrieved | Pending |
| known_issues | Some pages cover a family rather than a single model; infobox fields and MSRP evidence vary. |

## Wikidata

| Field | Value |
| --- | --- |
| source_name | Wikidata phone entities |
| provider | Wikimedia Foundation and Wikidata contributors |
| url | https://www.wikidata.org/wiki/Wikidata:Data_access |
| access_method | Wikidata Query Service and entity API; descriptive User-Agent required |
| licence | Structured Wikidata data: CC0 |
| terms_notes | Follow Wikimedia API usage limits and identify the client. |
| update_cadence | Entities are edited continuously |
| coverage | Phone model entities; exact count and field coverage to measure |
| record_meaning | One entity represents a Wikidata item, sometimes a family or variant |
| join_key | QID to Wikipedia; GSMArena phone ID (P4723) where present |
| first_retrieved | Pending |
| known_issues | Missing specifications and price claims; an unqualified price (P2284) is not necessarily launch MSRP. |
