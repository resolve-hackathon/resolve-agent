"""Deterministic impact summaries and a local ledger of observed reports.

Exposure comes from source SQL. Report counts are distinct customers observed by
this Resolve installation, not a count of confirmed GitHub comments or victims.
"""

from __future__ import annotations

import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ImpactGroup:
    plan: str
    os: str
    accounts: int
    exposed: int | None


@dataclass
class Impact:
    via: str
    sources: list[str]
    version: str
    platform: str | None
    total: int
    exposed: int | None
    groups: list[ImpactGroup]
    reported: int = 0

    def summary(self) -> str:
        origin = "federated query" if self.via == "zetaris" else "local snapshot query"
        scope = " and ".join(self.sources)
        plans, systems = {}, {}
        for group in self.groups:
            plans[group.plan] = plans.get(group.plan, 0) + group.accounts
            systems[group.os] = systems.get(group.os, 0) + group.accounts

        def breakdown(counts):
            return ", ".join(f"{name} {count}" for name, count in
                             sorted(counts.items(), key=lambda item: (-item[1], item[0])))

        if self.exposed is None:
            population = f"{self.total} accounts on {self.version}; exposure is not established"
        else:
            noun = "account" if self.exposed == 1 else "accounts"
            population = (f"{self.exposed} exposed {noun} ({self.version}, {self.platform}) "
                          f"of {self.total} on {self.version}")
        return (f"Impact ({origin} across {scope}): {population} "
                f"(plan: {breakdown(plans)}; OS: {breakdown(systems)}). "
                f"Customers who reported it via Resolve: {self.reported}.")


def parse_impact(rows, *, via: str, version: str, known_issue: bool) -> Impact:
    """Reject incomplete/inconsistent aggregates instead of guessing exposure."""
    if not rows:
        raise ValueError("No impact population returned")

    def count(value):
        if isinstance(value, bool) or not re.fullmatch(r"\d+", str(value)):
            raise ValueError("Invalid impact count")
        return int(value)

    groups, seen = [], set()
    if len(rows[0]) != 6:
        raise ValueError("Invalid impact row")
    platform = rows[0][1] or None
    if platform is not None and not isinstance(platform, str):
        raise ValueError("Invalid impact platform")
    for row in rows:
        if len(row) != 6:
            raise ValueError("Invalid impact row")
        release, row_platform, plan, system, total, exposed = row
        if release != version or (row_platform or None) != platform:
            raise ValueError("Impact scope does not match verified evidence")
        if not isinstance(plan, str) or not plan or not isinstance(system, str) or not system:
            raise ValueError("Missing impact dimensions")
        if (plan, system) in seen:
            raise ValueError("Duplicate impact group")
        seen.add((plan, system))
        total = count(total)
        exposed = None if exposed is None else count(exposed)
        if not total or (exposed is not None and exposed > total):
            raise ValueError("Inconsistent impact count")
        if (exposed is None) != (platform is None) or (not known_issue and platform is not None):
            raise ValueError("Exposure requires explicit issue platform metadata")
        groups.append(ImpactGroup(plan, system, total, exposed))
    return Impact(via, ["accounts", "issues"] if known_issue else ["accounts"],
                  version, platform, sum(g.accounts for g in groups),
                  None if platform is None else sum(g.exposed for g in groups), groups)


class ReportLedger:
    """Deduplicate repeated reports by customer and selected issue/release.

    Persistent paths are inside ignored runtime storage. A missing path uses an
    isolated in-memory ledger, useful for embedded clients and tests.
    """

    def __init__(self, path: Path | None = None):
        self.path = path
        self.observed = set()

    def observe(self, scope: str, customer_id: str) -> int:
        if self.path is None:
            self.observed.add((scope, customer_id))
            return sum(key == scope for key, _ in self.observed)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("CREATE TABLE IF NOT EXISTS reports "
                               "(scope TEXT, customer_id TEXT, PRIMARY KEY (scope, customer_id))")
            connection.execute("INSERT OR IGNORE INTO reports VALUES (?, ?)", (scope, customer_id))
            return connection.execute("SELECT COUNT(*) FROM reports WHERE scope = ?", (scope,)).fetchone()[0]
