# Impact analysis

After verifying a known bug or a new regression, Resolve queries the affected
version's account population. It appends the summary to the planned GitHub
comment/body. Customer replies contain the source remedy and citation only.
GitHub and Discord actions remain dry-run by default.

For a known issue, `sql/impact_zetaris.sql` joins `accounts_src.accounts` with
`issues_src.issues` on version, groups by plan and OS, and counts exposure using
the issue's explicit `platform`. GH-182 now declares `Windows`. A platform of
`all` matches every OS; missing/blank metadata means unknown exposure, not zero.
The author must supply platform metadata; Resolve does not infer it from prose.

For a new regression, `sql/impact_release_zetaris.sql` counts accounts on the
verified customer's version. This population is not proof of exposure, so the
summary explicitly says exposure is not established. Empty results, inconsistent
aggregates, and query failures produce an unavailable-impact note without
discarding the independently verified action. There is no silent switch to
SQLite when Zetaris fails.

`state.impact` contains totals, grouped rows, source names, backend, and report
count. `state.world_context.entities` exposes namespaced evidence IDs and
`provenance.via` (`zetaris` or `local`); the existing `state.evidence` remains.
This is inspectable application state, not a Meterless SDK integration.

## Update an existing installation

From the checkout in WSL:

```bash
python3 -m resolve seed
python3 zetaris/export_csv.py
ZETARIS_BUNDLE=~/zetaris-platform bash zetaris/load_postgres.sh accounts issues
```

The loader accepts an optional list of fixture sources; no arguments loads all
four. It replaces only the named tables in the `resolve_*` demo databases.
Accounts now expose `plan` and `os`; issues expose `platform`, alongside their
existing JSON payloads. Other fixture files are unchanged.

For an already registered installation, run these statements separately in the
Zetaris SQL Editor **once after upgrading the schema**:

```sql
REFRESH DATASOURCE TABLES FROM accounts_src
```

```sql
REFRESH DATASOURCE TABLES FROM issues_src
```

This reimports registered table metadata, as documented in the
[Zetaris SQL reference](https://github.com/zetaris/getting-started/blob/main/docs/guides/zetaris-lightning-sql-commands.md#410-refresh-datasource-tables).
Subsequent changes to row values need only the source reload.
New installations can use `zetaris/register.sql` after loading all four sources.

## Rehearse R1–R4

With `RESOLVE_RESEARCH=zetaris` and the local instance configured in `.env`:

```bash
python3 -m resolve ask --customer-id c-031 "Desktop sync stopped after the update"
python3 -m resolve ask --customer-id c-003 "I can reproduce an upload crash after 3.8.2"
clip.exe < zetaris/impact_handtest.sql
```

R1 selects `link_issue` and ends its engineer comment with:

```text
Impact (federated query across accounts and issues): 1 exposed account (3.8.1, Windows) of 13 on 3.8.1 (plan: team 9, starter 4; OS: macOS 12, Windows 1). Customers who reported it via Resolve: 1.
```

R2 selects `open_issue` and reports 12 accounts on 3.8.2 with unknown exposure.
R3: paste the copied query into the SQL Editor and execute it. Expected rows:

| version | platform | plan | os | accounts | exposed |
| --- | --- | --- | --- | ---: | ---: |
| 3.8.1 | Windows | starter | macOS | 4 | 0 |
| 3.8.1 | Windows | team | Windows | 1 | 1 |
| 3.8.1 | Windows | team | macOS | 8 | 0 |

The query plan contains `ACCOUNTS_SRC` and `ISSUES_SRC`. R4: History contains the
agent's `WITH customer AS` research and `SELECT t.version` impact queries.

Report counts track distinct customers submitting a verified issue/regression
report to this Resolve installation, including dry runs. They do not count
confirmed GitHub deliveries or prove a customer is exposed. Repeated runs by the
same customer do not inflate the count. Counts are scoped by selected issue or
release and version, and survive reseeding in ignored runtime SQLite ledgers:
`zetaris-reports.sqlite` for Zetaris, `<snapshot-name>-reports.sqlite` for local.
Counts may exceed 1 after other customers report the same issue. Demo/eval use
temporary isolated ledgers; no report history is written into source fixtures.

## Rehearse R5 and restore your data

Keep an exact backup of your current file, including any edits of your own:

```bash
backup=$(mktemp)
cp data/accounts.json "$backup"
python3 - <<'PY'
import json
from pathlib import Path
p = Path('data/accounts.json')
rows = json.loads(p.read_text())
customer = next(row for row in rows if row['id'] == 'c-006')
assert customer['client_version'] == '3.8.1' and customer['os'] == 'macOS'
customer['os'] = 'Windows'
p.write_text(json.dumps(rows, indent=2) + '\n')
PY
python3 zetaris/export_csv.py
ZETARIS_BUNDLE=~/zetaris-platform bash zetaris/load_postgres.sh accounts
```

Run the same R3 query: exposure sums to **2**, with no metadata refresh. Then
restore in the same shell (the backup preserves your exact original bytes):

```bash
cp "$backup" data/accounts.json
python3 zetaris/export_csv.py &&
ZETARIS_BUNDLE=~/zetaris-platform bash zetaris/load_postgres.sh accounts &&
rm "$backup"
```

R3 returns **1** again. `git diff -- data/accounts.json` should show no new changes
from this rehearsal. If a reload fails, keep the backup and retry restoration.

## Validation

```bash
python3 -m unittest discover -s tests -v
python3 -m resolve eval
```

On the local Zetaris instance on 2026-11-03, R1–R4 passed over the REST API, and
R5 returned **1 → 2 → 1**, restoring the original account file and source rows.
The captured [impact query plan](evidence/zetaris_impact_query_plan.txt) includes
both sources with masked connection metadata. The suite has 37 tests and the
existing offline evaluation remains 10/10; the dataset still has 10 KB articles.
