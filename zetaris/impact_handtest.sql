SELECT t.version, t.platform, a.plan, a.os, COUNT(*) AS accounts,
       SUM(CASE WHEN t.platform IS NULL THEN NULL
                WHEN LOWER(t.platform) = 'all' OR LOWER(a.os) = LOWER(t.platform) THEN 1
                ELSE 0 END) AS exposed
FROM (
    SELECT affects_version AS version, NULLIF(TRIM(platform), '') AS platform
    FROM issues_src.issues
    WHERE row_id = 'GH-182' AND state = 'open'
) t
JOIN accounts_src.accounts a ON a.client_version = t.version
GROUP BY t.version, t.platform, a.plan, a.os
ORDER BY a.plan, a.os
