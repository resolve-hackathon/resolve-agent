SELECT a.client_version AS version, NULL AS platform, a.plan, a.os,
       COUNT(*) AS accounts, NULL AS exposed
FROM accounts_src.accounts a
WHERE a.client_version = ?
GROUP BY a.client_version, a.plan, a.os
ORDER BY a.plan, a.os
