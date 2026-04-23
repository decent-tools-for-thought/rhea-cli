from __future__ import annotations

import json
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rhea_cli import cli


class CliTests(unittest.TestCase):
    def _run(self, argv: list[str]) -> tuple[int, str, str]:
        out = StringIO()
        err = StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_help_lists_new_command_groups(self) -> None:
        code, stdout, stderr = self._run([])
        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("release", stdout)
        self.assertIn("archive", stdout)
        self.assertIn("columns", stdout)
        self.assertIn("sparql", stdout)

    def test_columns_json(self) -> None:
        code, stdout, stderr = self._run(["columns", "--format", "json"])
        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        payload = json.loads(stdout)
        self.assertGreaterEqual(payload["count"], 13)

    def test_release_current_renders_json(self) -> None:
        with patch("rhea_cli.cli._build_service") as build_service:
            fake = build_service.return_value
            fake.archives.release_info.return_value = {
                "currentRelease": "140",
                "releaseDate": "2026-01-21",
            }
            code, stdout, stderr = self._run(["release", "current", "--format", "json"])
        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(json.loads(stdout)["currentRelease"], "140")

    def test_archive_download_invokes_service(self) -> None:
        with patch("rhea_cli.cli._build_service") as build_service:
            fake = build_service.return_value
            fake.archives.download.return_value = {"path": "/tmp/x", "bytes": 1}
            code, stdout, stderr = self._run(
                ["archive", "download", "tsv/rhea-tsv.tar.gz", "/tmp/x"]
            )
        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(json.loads(stdout)["bytes"], 1)

    def test_fetch_rxn_prints_raw_payload(self) -> None:
        with patch("rhea_cli.cli._build_service") as build_service:
            fake = build_service.return_value
            fake.fetch_ctfile.return_value = "$RXN\n"
            code, stdout, stderr = self._run(["fetch", "10000", "--format", "rxn"])
        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(stdout, "$RXN\n\n")

    def test_sparql_queries_lists_presets(self) -> None:
        with patch("rhea_cli.cli._build_service") as build_service:
            fake = build_service.return_value
            fake.list_sparql_queries.return_value = {
                "count": 1,
                "items": [{"name": "predicates", "description": "List predicates."}],
            }
            code, stdout, stderr = self._run(["sparql", "queries", "--format", "json"])
        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(json.loads(stdout)["items"][0]["name"], "predicates")

    def test_sparql_query_renders_boolean_text(self) -> None:
        with patch("rhea_cli.cli._build_service") as build_service:
            fake = build_service.return_value
            fake.sparql_query.return_value = {"kind": "ask", "boolean": True, "body": "true"}
            code, stdout, stderr = self._run(["sparql", "query", "ASK { ?s ?p ?o }"])
        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(stdout.strip(), "true")

    def test_sparql_show_prints_query_text(self) -> None:
        code, stdout, stderr = self._run(["sparql", "show", "predicates", "--limit", "3"])
        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("SELECT ?predicate", stdout)
        self.assertIn("LIMIT 3", stdout)


if __name__ == "__main__":
    unittest.main()
