from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rhea_cli.archive import parse_index
from rhea_cli.columns import normalize_row, parse_columns
from rhea_cli.core import RheaError, RheaService, normalize_rhea_id
from rhea_cli.sparql import parse_sparql_json, render_sparql_preset


class FakeResponse:
    def __init__(self, text: str, body: bytes | None = None) -> None:
        self._text = text
        self.body = body if body is not None else text.encode("utf-8")
        self.content_type = "application/json" if text.lstrip().startswith("{") else "text/plain"

    def text(self) -> str:
        return self._text

    def json(self) -> Any:
        return json.loads(self._text)


class FakeClient:
    def __init__(self, responses: dict[tuple[str, str], FakeResponse]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, str, dict[str, Any] | None]] = []
        self.ftp_base_url = "https://ftp.example/rhea"

    def request(
        self,
        *,
        method: str,
        path: str,
        query: dict[str, Any] | None = None,
        base: str = "web",
        accept: str = "*/*",
    ) -> FakeResponse:
        del method, accept
        self.calls.append((base, path, query))
        key = (base, path)
        if key not in self.responses:
            raise AssertionError(f"unexpected request: {key}")
        return self.responses[key]


def directions_tsv() -> str:
    return "RHEA_ID_MASTER\tRHEA_ID_LR\tRHEA_ID_RL\tRHEA_ID_BI\n10000\t10001\t10002\t10003\n"


def full_table_text() -> str:
    return (
        "Reaction identifier\tEquation\tChEBI name\tChEBI identifier\tEC number\tEnzymes\tGene Ontology\tPubMed\tCross-reference (KEGG)\n"
        "RHEA:10000\ta + b = c\twater;foo\tCHEBI:15377;CHEBI:1\tEC:1.1.1.1\t5\tGO:0001 label\t123;456\tKEGG:R00001\n"
        "RHEA:10001\tx + y = z\tbar\tCHEBI:2\tEC:2.2.2.2\t0\t\t\t\n"
    )


class CoreTests(unittest.TestCase):
    def test_normalize_rhea_id(self) -> None:
        self.assertEqual(normalize_rhea_id("RHEA:10000"), "10000")

    def test_parse_columns_passthrough(self) -> None:
        self.assertEqual(parse_columns("rhea-id,nope,rhea-id"), ["rhea-id", "nope"])

    def test_normalize_row_handles_documented_types(self) -> None:
        normalized = normalize_row(
            {
                "rhea-id": "RHEA:10000",
                "chebi": "water;foo",
                "chebi-id": "CHEBI:15377;CHEBI:1",
                "ec": "EC:1.1.1.1",
                "uniprot": "5",
                "go": "GO:0001 label",
                "pubmed": "123;456",
                "reaction-xref(KEGG)": "KEGG:R00001",
            }
        )
        self.assertEqual(normalized["uniprot"], 5)
        self.assertEqual(normalized["chebi"][0], "water")
        self.assertEqual(normalized["chebi-id"][0]["id"], "CHEBI:15377")
        self.assertEqual(normalized["go"][0]["id"], "GO:0001")
        self.assertEqual(normalized["pubmed"][1]["id"], "456")

    def test_directions_resolution(self) -> None:
        service = RheaService(
            FakeClient({("ftp", "tsv/rhea-directions.tsv"): FakeResponse(directions_tsv())})
        )
        payload = service.directions("10002")
        self.assertEqual(payload["requestedRole"], "rl")
        self.assertEqual(payload["master"], "RHEA:10000")

    def test_search_includes_normalized_items(self) -> None:
        client = FakeClient({("web", "/rhea/"): FakeResponse(full_table_text())})
        service = RheaService(client)
        result = service.search(
            query="x",
            columns=[
                "rhea-id",
                "equation",
                "chebi",
                "chebi-id",
                "ec",
                "uniprot",
                "go",
                "pubmed",
                "reaction-xref(KEGG)",
            ],
            limit=2,
        )
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["normalizedItems"][0]["uniprot"], 5)

    def test_paginated_search_uses_cursor_file(self) -> None:
        client = FakeClient({("web", "/rhea/"): FakeResponse(full_table_text())})
        service = RheaService(client)
        with tempfile.TemporaryDirectory() as tmpdir:
            cursor = str(Path(tmpdir) / "cursor.json")
            first = service.search(
                query="", columns=["rhea-id", "equation"], limit=2, page_size=1, cursor_file=cursor
            )
            second = service.search(
                query="",
                columns=["rhea-id", "equation"],
                limit=2,
                page_size=1,
                cursor_file=cursor,
                resume=True,
            )
            self.assertEqual(first["items"][0]["rhea-id"], "RHEA:10000")
            self.assertEqual(second["items"][0]["rhea-id"], "RHEA:10001")
            saved = json.loads(Path(cursor).read_text())
            self.assertIn("nextOffset", saved)

    def test_fetch_reaction_returns_normalized_summary(self) -> None:
        client = FakeClient(
            {
                ("ftp", "tsv/rhea-directions.tsv"): FakeResponse(directions_tsv()),
                ("web", "/rhea/"): FakeResponse(
                    "Reaction identifier\tEquation\tEnzymes\nRHEA:10000\ta + b = c\t5\n"
                ),
            }
        )
        payload = RheaService(client).fetch_reaction(
            "10000", columns=["rhea-id", "equation", "uniprot"], direction="auto"
        )
        self.assertEqual(payload["normalizedSummary"]["uniprot"], 5)
        self.assertEqual(payload["resolvedDirectionalId"], "RHEA:10001")

    def test_participants_pairs_names_and_ids(self) -> None:
        client = FakeClient(
            {
                ("web", "/rhea/"): FakeResponse(
                    "Reaction identifier\tChEBI name\tChEBI identifier\nRHEA:10000\twater;foo\tCHEBI:15377;CHEBI:1\n"
                )
            }
        )
        payload = RheaService(client).participants("10000")
        self.assertEqual(payload["participants"][0]["name"], "water")

    def test_xrefs_collects_reaction_crossrefs(self) -> None:
        client = FakeClient(
            {
                ("web", "/rhea/"): FakeResponse(
                    "Reaction identifier\tEquation\tChEBI name\tChEBI identifier\tEC number\tEnzymes\tGene Ontology\tPubMed\tCross-reference (EcoCyc)\tCross-reference (MetaCyc)\tCross-reference (KEGG)\tCross-reference (Reactome)\tCross-reference (N-CSA/MACiE)\n"
                    "RHEA:10000\ta + b = c\twater\tCHEBI:15377\tEC:1.1.1.1\t5\tGO:0001 label\t123\tEcoCyc:RXN\tMetaCyc:RXN\tKEGG:R1\tReactome:R-HSA\tM-CSA:1\n"
                )
            }
        )
        payload = RheaService(client).xrefs("10000")
        self.assertEqual(payload["reaction-xrefs"]["KEGG"][0]["id"], "KEGG:R1")

    def test_archive_index_parser(self) -> None:
        entries = parse_index(
            "<table><tr class='odd'><td>x</td><td><a href='foo.tsv'>foo.tsv</a></td><td>2026-01-28</td><td>1K</td></tr></table>"
        )
        self.assertEqual(entries[0].name, "foo.tsv")

    def test_release_info_and_listing(self) -> None:
        client = FakeClient(
            {
                ("ftp", "rhea-release.properties"): FakeResponse(
                    "rhea.release.number=140\nrhea.release.date=2026-01-21\n"
                ),
                ("ftp", "old_releases/"): FakeResponse(
                    "<table><tr class='odd'><td>x</td><td><a href='140.tar.bz2'>140.tar.bz2</a></td><td>2026-01-28</td><td>417M</td></tr></table>"
                ),
            }
        )
        service = RheaService(client)
        self.assertEqual(service.archives.release_info()["currentRelease"], "140")
        self.assertEqual(service.archives.list_old_releases()[0]["release"], "140")

    def test_invalid_uniprot_raises(self) -> None:
        with self.assertRaises(RheaError):
            RheaService(FakeClient({})).protein("bad", columns=["rhea-id"], limit=1)

    def test_parse_sparql_json_select(self) -> None:
        parsed = parse_sparql_json(
            {
                "head": {"vars": ["predicate", "count"]},
                "results": {
                    "bindings": [
                        {
                            "predicate": {"type": "uri", "value": "http://example/p"},
                            "count": {
                                "type": "literal",
                                "datatype": "http://www.w3.org/2001/XMLSchema#integer",
                                "value": "3",
                            },
                        }
                    ]
                },
            }
        )
        self.assertEqual(parsed["kind"], "select")
        self.assertEqual(parsed["items"][0]["count"], "3^^http://www.w3.org/2001/XMLSchema#integer")

    def test_sparql_query_parses_boolean_result(self) -> None:
        client = FakeClient(
            {
                ("sparql", "/sparql"): FakeResponse('{"head": {"link": []}, "boolean": true}'),
            }
        )
        payload = RheaService(client).sparql_query("ASK { ?s ?p ?o }", output_format="json")
        self.assertEqual(payload["kind"], "ask")
        self.assertTrue(payload["boolean"])

    def test_render_sparql_preset_includes_limit(self) -> None:
        query = render_sparql_preset("predicates", limit=7)
        self.assertIn("LIMIT 7", query)


if __name__ == "__main__":
    unittest.main()
