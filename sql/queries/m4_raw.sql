-- M2-only baseline: latest rows, raw Android prefix, raw year cast, no flags.
-- Deliberately naive SQLite CAST of About ... EUR; no cleaning or variants.
WITH models AS (
 SELECT p.phone_key,substr(p.name,1,instr(p.name || ' ',' ')-1) AS brand,
 MAX(CASE WHEN s.source_field='os' THEN s.value_text END) AS os,
 MAX(CASE WHEN s.source_field='year' THEN CAST(s.value_text AS INTEGER) END) AS year,
 MAX(CASE WHEN s.source_field='price' AND s.value_text LIKE :price_pattern
 THEN CAST(replace(replace(s.value_text,'About ',''),' EUR','') AS REAL) END) AS price
 FROM phone p JOIN specification s ON s.phone_key=p.phone_key AND s.retrieved_at=p.retrieved_at
 GROUP BY p.phone_key,p.name
)
SELECT brand,COUNT(*) AS catalog_n,COUNT(price) AS n,AVG(price) AS mean_price
FROM models WHERE os LIKE :os_pattern AND year BETWEEN :start AND :end
 AND brand IN (SELECT value FROM json_each(:brands)) GROUP BY brand ORDER BY brand;
