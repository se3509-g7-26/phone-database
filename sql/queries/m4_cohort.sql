-- One row per current canonical catalog model. Every numeric field uses :flags;
-- year requires ok, OS requires mapped. No memory variant is selected.
WITH cells AS (
 SELECT p.phone_key,p.name,p.retrieved_at,
        substr(p.name,1,instr(p.name || ' ',' ')-1) AS brand,
        s.source_field,s.number,s.ram_gb,s.unit,s.number_flag,s.category,s.category_flag
 FROM phone p JOIN specification_current s USING(phone_key)
 WHERE s.resolved_phone_key=p.phone_key
), models AS (
 SELECT phone_key,name,brand,retrieved_at,
 MAX(CASE WHEN source_field='os' AND category_flag='mapped' THEN category END) AS os,
 MAX(CASE WHEN source_field='year' AND number_flag='ok' THEN CAST(number AS INTEGER) END) AS year,
 MAX(CASE WHEN source_field='price' AND unit=:currency AND number_flag IN (SELECT value FROM json_each(:flags)) THEN number END) AS price,
 MAX(CASE WHEN source_field='internalmemory' AND number_flag IN (SELECT value FROM json_each(:flags)) THEN ram_gb END) AS ram,
 MAX(CASE WHEN source_field='internalmemory' AND number_flag IN (SELECT value FROM json_each(:flags)) THEN number END) AS storage,
 MAX(CASE WHEN source_field='displaysize' AND unit='inch' AND number_flag IN (SELECT value FROM json_each(:flags)) THEN number END) AS display_in,
 MAX(CASE WHEN source_field='price' THEN 1 ELSE 0 END) AS price_present,
 MAX(CASE WHEN source_field='price' THEN number_flag END) AS price_flag
 FROM cells GROUP BY phone_key,name,brand,retrieved_at
)
SELECT * FROM models WHERE os=:os AND year BETWEEN :start AND :end
 AND brand IN (SELECT value FROM json_each(:brands)) ORDER BY phone_key;
