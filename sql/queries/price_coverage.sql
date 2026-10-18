-- Question: how much of the catalog has price evidence and a Wikidata link?
-- Result grain: one row for each (price-text-present, Wikidata-link-present) pair.
-- Start with one current row per phone. Correlated EXISTS prevents specification
-- rows and many-to-many Wikidata links from multiplying the phone count.
-- This measures evidence coverage, not launch MSRP or comparable monetary values.
WITH coverage AS (
    SELECT
        EXISTS (SELECT 1 FROM specification s
                WHERE s.phone_key=p.phone_key AND s.retrieved_at=p.retrieved_at
                  AND s.source_field='price' AND s.value_text IS NOT NULL) AS has_price_text,
        EXISTS (SELECT 1 FROM phone_item_link l
                WHERE l.phone_key=p.phone_key) AS has_wikidata_link
    FROM phone p
)
SELECT has_price_text, has_wikidata_link, COUNT(*) AS models
FROM coverage
GROUP BY has_price_text, has_wikidata_link
ORDER BY has_price_text, has_wikidata_link;
