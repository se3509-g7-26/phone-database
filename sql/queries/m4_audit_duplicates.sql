-- Analytical fields that appear more than once for one current catalog model.
-- The cohort query pivots with MAX(), so any row here needs a cleaning decision.
SELECT phone_key,source_field,COUNT(*) AS n
FROM specification_current
WHERE source_field IN (SELECT value FROM json_each(:fields))
GROUP BY phone_key,source_field
HAVING COUNT(*)>1;
