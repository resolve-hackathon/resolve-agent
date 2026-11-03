import json
import re
import sqlite3
import tempfile
import unittest
from pathlib import Path
from contextlib import closing
from unittest.mock import patch

from resolve.actions import DryRunActions
from resolve.agent import Agent
from resolve.config import ROOT
from resolve.impact import parse_impact
from resolve.reasoning import RulesReasoner
from resolve.research import SQLResearcher, seed_snapshot
from resolve.state import Action
from resolve.transport import ServiceError
from resolve.zetaris import bind, zetaris_researcher


class ImpactTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database = Path(self.temp.name) / "support.sqlite"
        seed_snapshot(ROOT / "data", self.database)
        self.researcher = SQLResearcher.local(self.database)
        self.agent = Agent(self.researcher, RulesReasoner(), DryRunActions())

    def known(self, agent=None, customer="c-031"):
        return (agent or self.agent).run("Desktop sync stopped after the update", customer, "report-1")

    def update(self, sql, params=()):
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute(sql, params)

    def test_known_issue_counts_exposure_and_preserves_customer_reply(self):
        state = self.known()
        self.assertEqual((state.impact.total, state.impact.exposed, state.impact.reported), (13, 1, 1))
        self.assertEqual(state.impact.platform, "Windows")
        self.assertEqual(sum(g.exposed for g in state.impact.groups if g.os == "macOS"), 0)
        expected = ("Impact (local snapshot query across accounts and issues): 1 exposed account "
                    "(3.8.1, Windows) of 13 on 3.8.1 (plan: team 9, starter 4; "
                    "OS: macOS 12, Windows 1). Customers who reported it via Resolve: 1.")
        self.assertEqual(state.action_result["planned"]["payload"]["comment"].splitlines()[-1], expected)
        self.assertNotIn("Impact", state.reply_text)
        self.assertNotIn("13", state.reply_text)
        self.assertEqual(state.snapshot()["world_context"]["entities"][0]["provenance"]["via"], "local")

    def test_new_bug_counts_release_population_without_claiming_exposure(self):
        state = self.agent.run("I can reproduce an upload crash after 3.8.2", "c-003", "new")
        self.assertEqual(state.action, Action.OPEN_ISSUE)
        self.assertEqual(state.impact.total, 12)
        self.assertIsNone(state.impact.exposed)
        self.assertEqual(state.impact.sources, ["accounts"])
        body = state.action_result["planned"]["payload"]["body"]
        self.assertIn("12 accounts on 3.8.2; exposure is not established", body)
        self.assertNotIn("Impact", state.reply_text)

    def test_source_change_is_visible_on_next_query(self):
        self.assertEqual(self.known().impact.exposed, 1)
        self.update("UPDATE accounts SET os = 'Windows' WHERE row_id = 'c-006'")
        changed = self.known().impact
        self.assertEqual((changed.total, changed.exposed), (13, 2))
        self.update("UPDATE accounts SET os = 'macOS' WHERE row_id = 'c-006'")
        self.assertEqual(self.known().impact.exposed, 1)

    def test_platform_metadata_all_and_unknown(self):
        self.update("UPDATE issues SET platform = 'all' WHERE row_id = 'GH-182'")
        self.assertEqual(self.known().impact.exposed, 13)
        for unknown in (None, "", "   "):
            self.update("UPDATE issues SET platform = ? WHERE row_id = 'GH-182'", (unknown,))
            impact = self.known().impact
            self.assertIsNone(impact.exposed)
            self.assertIn("exposure is not established", impact.summary())

    def test_reports_deduplicate_customers_across_processes_and_reseed(self):
        self.assertEqual(self.known().impact.reported, 1)
        self.assertEqual(self.known().impact.reported, 1)
        # A submitted report is not proof this second customer is exposed.
        self.assertEqual(self.known(customer="c-006").impact.reported, 2)
        seed_snapshot(ROOT / "data", self.database)
        restarted = Agent(SQLResearcher.local(self.database), RulesReasoner(), DryRunActions())
        self.assertEqual(self.known(restarted).impact.reported, 2)
        new = restarted.run("upload crash after 3.8.2", "c-003", "new")
        self.assertEqual(new.impact.reported, 1)

    def test_impact_outage_keeps_verified_action_and_redacts_error(self):
        with patch.object(self.researcher, "impact", side_effect=ServiceError("secret token")):
            state = self.known()
        self.assertEqual(state.action, Action.LINK_ISSUE)
        self.assertTrue(state.verified)
        self.assertIsNone(state.impact)
        self.assertIn("Impact unavailable", state.action_result["planned"]["payload"]["comment"])
        self.assertNotIn("secret token", json.dumps(state.snapshot()))
        self.assertNotIn("Impact", state.reply_text)

    def test_fix_escalation_and_failed_verification_skip_impact(self):
        with patch.object(self.researcher, "impact") as impact:
            self.agent.run("export is blank", "c-002", "fix")
            self.agent.run("human please", "c-031", "human")
            self.agent.run("sync stopped", "missing", "missing")
            impact.assert_not_called()

    def test_stale_closed_issue_cannot_produce_an_impact_count(self):
        original = self.researcher.impact

        def changed(state):
            self.update("UPDATE issues SET state = 'closed' WHERE row_id = 'GH-182'")
            return original(state)

        with patch.object(self.researcher, "impact", side_effect=changed):
            state = self.known()
        self.assertIsNone(state.impact)
        self.assertIn("Impact unavailable", state.impact_error)

    def test_zetaris_adapter_uses_federated_sql_and_truthful_provenance(self):
        queries = []
        database = self.database

        class RecordingClient:
            def run(self, sql):
                sql = re.sub(r"--[^\n]*", "", sql).strip()
                queries.append(sql)
                local = sql.replace("accounts_src.", "").replace("issues_src.", "")
                local = local.replace("kb_src.", "").replace("releases_src.", "")
                with closing(sqlite3.connect(database)) as connection:
                    rows = connection.execute(local).fetchall()
                # The live REST API serializes numeric aggregates as strings.
                return {"data": [[str(v) if v is not None else None for v in row] for row in rows]}

        with patch("resolve.zetaris.ZetarisClient.from_env", return_value=RecordingClient()):
            researcher = zetaris_researcher()
        state = self.known(Agent(researcher, RulesReasoner(), DryRunActions()))
        self.assertEqual(len(queries), 2)
        self.assertTrue(queries[0].startswith("WITH customer AS"))
        self.assertTrue(queries[1].startswith("SELECT t.version"))
        self.assertIn("issues_src.issues", queries[1])
        self.assertIn("accounts_src.accounts", queries[1])
        self.assertEqual(state.impact.exposed, 1)
        self.assertIn("Impact (federated query across accounts and issues)", state.impact.summary())
        self.assertTrue(all(e["provenance"]["via"] == "zetaris"
                            for e in state.snapshot()["world_context"]["entities"]))

    def test_hand_query_matches_agent_query_and_escapes_issue_id(self):
        template = (ROOT / "sql/impact_zetaris.sql").read_text()
        self.assertEqual(bind(template, ("GH-182",)), (ROOT / "zetaris/impact_handtest.sql").read_text())
        sql = bind(template, ("GH-182' OR 1=1 --",)).replace("accounts_src.", "").replace("issues_src.", "")
        with closing(sqlite3.connect(self.database)) as connection:
            self.assertEqual(connection.execute(sql).fetchall(), [])

    def test_malformed_or_inconsistent_aggregates_are_rejected(self):
        valid = ["3.8.1", "Windows", "team", "Windows", "1", "1"]
        invalid = [[], [[]], [valid, valid]]
        for index, value in ((0, "3.8.2"), (1, None), (1, 1), (2, None),
                             (4, "-1"), (4, "1.5"), (4, True), (5, "2"), (5, None)):
            row = valid.copy()
            row[index] = value
            invalid.append([row])
        for rows in invalid:
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                parse_impact(rows, via="zetaris", version="3.8.1", known_issue=True)

    def test_old_snapshot_schema_is_migrated(self):
        path = Path(self.temp.name) / "old.sqlite"
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.executescript("""
                CREATE TABLE accounts (row_id TEXT, discord_id TEXT, client_version TEXT,
                                       last_working_version TEXT, payload TEXT);
                CREATE TABLE issues (row_id TEXT, component TEXT, state TEXT,
                                     affects_version TEXT, payload TEXT);
            """)
        seed_snapshot(ROOT / "data", path)
        state = self.known(Agent(SQLResearcher.local(path), RulesReasoner(), DryRunActions()))
        self.assertEqual(state.impact.exposed, 1)


if __name__ == "__main__":
    unittest.main()
