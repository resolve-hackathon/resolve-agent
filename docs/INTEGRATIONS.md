# Integration handoff

## Zetaris: REST research and impact queries implemented

Set `RESOLVE_RESEARCH=zetaris` with `ZETARIS_REST_URL`, `ZETARIS_API_KEY`, and
`ZETARIS_ORG_ID` in the ignored `.env`. `make_researcher` selects this adapter for
CLI and Discord research. The REST adapter sends fixed SELECT/WITH statements
through `/sql-editor/sqls/run`, validates results, rejects truncated responses,
and never accepts model-generated SQL. A Zetaris failure does not fall back to
SQLite. `SQLResearcher.local()` remains an explicit offline snapshot, with
`provenance.via=local` rather than `zetaris`.

Four separate demo PostgreSQL databases can be loaded with
`zetaris/export_csv.py` and `zetaris/load_postgres.sh`, then registered with
`zetaris/register.sql`. Their normalized columns are:

| View | Columns used by research and impact |
| --- | --- |
| accounts | row_id, discord_id, client_version, last_working_version, payload, plan, os |
| kb | row_id, component, payload |
| releases | row_id, component, payload |
| issues | row_id, component, state, affects_version, payload, platform |

`payload` is the JSON source record. Research returns `(source, row_id, payload)`
rows from component-scoped queries, then filters stable version ranges and
symptoms in Python. Original source IDs and URLs are preserved. The impact query
joins accounts and issues on version and groups by plan/OS inside Zetaris; the
new-regression query counts the verified client's version population without
claiming confirmed exposure. Both use fixed SQL with bound values.

These are synthetic source fixtures, not a continuous GitHub/KB ingestion
pipeline. Local Docker REST queries, source counts, query plans, and R1–R5 were
verified on 2026-11-03. See [impact setup and rehearsal](IMPACT_ANALYSIS.md),
including the one-time metadata refresh required by an older installation.

The DB-API seam remains `SQLResearcher(connect, query, identity_query, via=...)`.
A custom connection supplies `cursor()`, `execute()`, `fetchall()`/`fetchone()`, and
`close()`. Tenant-specific virtual sources should preserve these normalized
columns. Never interpolate customer text or allow a model to supply SQL.

## NVIDIA Nemotron: optional compatible transport implemented

The adapter calls `/chat/completions` at the configured base URL with bearer
authentication. Both hypothesis and semantic verification use the configured
model; triage and reply rendering remain local for this starter. Copy the exact
available model ID from your provider. Invalid JSON, unsupported actions, false
claims, rejected verification, and service errors cannot bypass the hard gate.
No provider credentials or live inference were available during development.

Official API reference: [NVIDIA chat completion interface](https://docs.api.nvidia.com/nim/reference/nvidia-llama-3_1-nemotron-ultra-253b-v1-infer).
This link documents the interface; it is not a requirement to use that model.

## Meterless: explicit state pattern only

`TaskState` is a serializable shared object. The role prompts live in
`resolve/reasoning.py`; `events` provide inspectable decisions and citations.
There are no Meterless SDK, prompt-library, memory, or service calls yet. Confirm
the event requirement, then map these seams to the actual service. Do not claim
sponsor usage from the local dataclass alone. H-MEM is deferred as a stretch goal.

## GitHub: live action handlers, snapshot research

`LiveActions` implements a comment on an existing issue and opening/re-reading a
new one. The offline issue records are fictional fixtures. Replace them with a
real demo repository's records before live `link_issue`; revalidate versions and
workarounds when importing. Keep the external API repository fixed in
configuration, separate from model output. Seed the component labels yourself.

Next, add a GitHub issue importer with pagination and explicit version metadata
(for example, component and affected-version labels) or register the GitHub API
source in Zetaris. Do not parse arbitrary issue prose into trusted executable
actions. Live POSTs have no automatic HTTP retry; a persistent action journal
blocks duplicate question IDs after success, failure, or process interruption.
It cannot guarantee exactly-once delivery across a remote timeout: reconcile
the receipts in `runtime/actions.sqlite` and the service before manual recovery.

Official references: [issue creation](https://docs.github.com/en/rest/issues/issues#create-an-issue)
and [issue comments](https://docs.github.com/en/rest/issues/comments#create-an-issue-comment).

## Discord: optional one-server bot

The bot is deliberately scoped to one server and support channel. With live
actions disabled it posts preview replies only. With live actions enabled,
fixed REST handlers send source-based replies and evidence packets, collecting
message IDs. Mentions are disabled in generated messages. GitHub writes happen
only in the configured demo repository.

Official references: [discord.py API](https://discordpy.readthedocs.io/en/latest/api.html)
and [Message Content intent](https://discordpy.readthedocs.io/en/stable/intents.html).

## Cursor and submission evidence

Open this checkout in Cursor, configure the actual Zetaris MCP server there,
and capture a working query and component while building. This starter cannot
retroactively claim it was authored in Cursor or that its MCP connection exists.
After tenant integration, rerun the four acceptance scenarios against the real
services, including visible receipts and the escalation channel, before recording.
The ten offline cases measure deterministic fixture behavior, not live Nemotron
accuracy, sponsor compliance, or production readiness.
