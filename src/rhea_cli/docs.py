from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .columns import DOCUMENTED_COLUMN_SPECS
from .mappings import MAPPING_DATASETS


@dataclass(frozen=True)
class QueryField:
    name: str
    description: str
    example: str


# Searchable fields accepted by the Rhea web query endpoint (the ``query=``
# parameter behind ``search``/``table``/``ids``). Verified against
# https://www.rhea-db.org/rhea?query=... ; ``*`` is a wildcard and an empty
# query matches the whole table.
QUERY_FIELDS: tuple[QueryField, ...] = (
    QueryField(
        "(free text)",
        "Full-text search over reaction names, equations, compound and enzyme labels",
        "oxidoreductase",
    ),
    QueryField("rhea", "A Rhea reaction identifier", "rhea:10000"),
    QueryField("ec", "Reactions annotated with an Enzyme Commission number", "ec:1.1.1.1"),
    QueryField("chebi", "Reactions with a given ChEBI participant", "chebi:15377"),
    QueryField("uniprot", "Reactions annotated to a UniProtKB accession", "uniprot:P00350"),
    QueryField("pubmed", "Reactions cited by a PubMed identifier", "pubmed:12345678"),
)

QUERY_GRAMMAR_NOTES: tuple[str, ...] = (
    "Combine a field and value with a colon, e.g. 'ec:1.1.1.1'.",
    "'*' is a wildcard: 'ec:*' returns every reaction carrying any EC number.",
    "An empty query ('') matches the entire reaction table.",
    "Pair any query with --fetch-all (search/table/ids) to export the complete result set as TSV/JSON.",
)

# High-level command surface, grouped by intent, for agent discovery.
COMMAND_GROUPS: tuple[dict[str, Any], ...] = (
    {
        "group": "Entity lookup",
        "summary": "Resolve a single reaction or a biology entity to its reactions.",
        "commands": [
            {"command": "reaction", "summary": "Fetch one reaction by Rhea ID with directions."},
            {"command": "compound", "summary": "Reactions containing a ChEBI compound."},
            {"command": "enzyme", "summary": "Reactions annotated with an EC number."},
            {"command": "protein", "summary": "Reactions annotated to a UniProtKB accession."},
            {"command": "publication", "summary": "Reactions cited by a PubMed ID."},
            {"command": "term", "summary": "Free-text reaction search."},
            {"command": "resolve", "summary": "Classify mixed identifiers and look each one up."},
        ],
    },
    {
        "group": "Reaction graph",
        "summary": "Inspect a reaction's directions, participants, and cross-references.",
        "commands": [
            {"command": "directions", "summary": "Master/LR/RL/BI identifiers for a reaction."},
            {"command": "counterparts", "summary": "Directional counterparts of a reaction."},
            {"command": "canonicalize", "summary": "Map any directional ID to its master."},
            {"command": "equation", "summary": "Print a reaction equation."},
            {"command": "participants", "summary": "List ChEBI participants of a reaction."},
            {"command": "xrefs", "summary": "Collect all cross-references for a reaction."},
            {"command": "explain", "summary": "Human-readable reaction summary."},
            {"command": "enzymes-for", "summary": "Group enzymes (EC) for one ChEBI compound."},
            {"command": "proteins-for", "summary": "Group proteins for one ChEBI compound."},
        ],
    },
    {
        "group": "Table & bulk export",
        "summary": "Query the Rhea table and export full result sets. See 'rhea fields' and 'rhea columns'.",
        "commands": [
            {
                "command": "search",
                "summary": "Query the reaction table; use --fetch-all for everything.",
            },
            {"command": "table", "summary": "Alias of search for table-style exports."},
            {
                "command": "ids",
                "summary": "Export just rhea-id for a query (supports --fetch-all).",
            },
            {"command": "grep", "summary": "Free-text search returning rhea-id and equation."},
            {"command": "fields", "summary": "List searchable query fields and wildcard syntax."},
            {"command": "columns", "summary": "List selectable result columns."},
        ],
    },
    {
        "group": "Bulk mappings",
        "summary": "Authoritative, release-pinned rhea2* cross-reference tables (preferred for bulk).",
        "commands": [
            {"command": "mappings list", "summary": "List the canonical mapping datasets."},
            {
                "command": "mappings get",
                "summary": "Download/parse one mapping (e.g. 'mappings get ec').",
            },
        ],
    },
    {
        "group": "Files & releases",
        "summary": "Directional reaction files, release manifests, and archive browsing.",
        "commands": [
            {"command": "download", "summary": "Fetch a directional RXN/RD file."},
            {"command": "release", "summary": "Inspect releases and downloadable file groups."},
            {"command": "archive", "summary": "Browse and extract FTP archive contents."},
        ],
    },
    {
        "group": "SPARQL & discovery",
        "summary": "Query the SPARQL endpoint and introspect this CLI's own surface.",
        "commands": [
            {"command": "sparql", "summary": "Run queries and inspect the endpoint schema."},
            {
                "command": "docs",
                "summary": "Describe this CLI's surface, query grammar, and data sources.",
            },
        ],
    },
)

PROGRAMMATIC_NOTE = (
    "For in-script use, import the library instead of shelling out per record: "
    "`from rhea_cli import RheaService`. Use `RheaService().search(query=..., "
    "columns=[...], fetch_all=True)` for bulk table exports, or `fetch_mapping(name)` "
    "for the canonical rhea2* tables."
)

DATA_SOURCES = {
    "web_query": "https://www.rhea-db.org/rhea",
    "ftp": "https://ftp.expasy.org/databases/rhea",
    "sparql": "https://sparql.rhea-db.org/sparql",
}

_SELECTORS = ("all", "commands", "query", "fields", "mappings", "columns")


def docs_payload(selector: str, *, ftp_base_url: str) -> dict[str, Any]:
    if selector not in _SELECTORS:
        raise KeyError(
            f"unknown docs selector '{selector}'; choose one of: {', '.join(_SELECTORS)}"
        )

    def show(section: str) -> bool:
        return selector in ("all", section)

    payload: dict[str, Any] = {"kind": "rhea_cli_docs", "selector": selector}
    if selector == "all":
        payload["data_sources"] = DATA_SOURCES
        payload["programmatic"] = PROGRAMMATIC_NOTE
    if show("commands"):
        payload["command_groups"] = [dict(group) for group in COMMAND_GROUPS]
    if show("query") or show("fields"):
        payload["query_fields"] = [
            {"name": field.name, "description": field.description, "example": field.example}
            for field in QUERY_FIELDS
        ]
        payload["query_grammar"] = list(QUERY_GRAMMAR_NOTES)
    if show("mappings"):
        payload["mappings"] = [
            {
                "name": dataset.name,
                "file": dataset.file,
                "target": dataset.target,
                "description": dataset.description,
                "url": f"{ftp_base_url}/tsv/{dataset.file}",
            }
            for dataset in MAPPING_DATASETS.values()
        ]
    if show("columns"):
        payload["columns"] = [
            {"id": spec.id, "label": spec.label, "kind": spec.kind, "description": spec.description}
            for spec in DOCUMENTED_COLUMN_SPECS.values()
        ]
    return payload


def render_docs(selector: str, output_format: str, *, ftp_base_url: str) -> str:
    payload = docs_payload(selector, ftp_base_url=ftp_base_url)
    if output_format == "json":
        return json.dumps(payload, indent=2, sort_keys=False)
    return _render_markdown(payload)


def _render_markdown(payload: dict[str, Any]) -> str:
    lines = ["# rhea CLI", "", f"- selector: {payload['selector']}"]
    if "data_sources" in payload:
        lines.append("")
        lines.append("## Data sources")
        lines.append("")
        for key, url in payload["data_sources"].items():
            lines.append(f"- {key}: {url}")
    if "command_groups" in payload:
        lines.extend(["", "## Commands", ""])
        for group in payload["command_groups"]:
            lines.append(f"### {group['group']}")
            lines.append(f"_{group['summary']}_")
            lines.append("")
            for command in group["commands"]:
                lines.append(f"- `{command['command']}` — {command['summary']}")
            lines.append("")
    if "query_fields" in payload:
        lines.extend(["## Query fields", ""])
        for field in payload["query_fields"]:
            lines.append(
                f"- `{field['name']}` — {field['description']} (e.g. `{field['example']}`)"
            )
        lines.append("")
        lines.append("Grammar:")
        for note in payload["query_grammar"]:
            lines.append(f"- {note}")
        lines.append("")
    if "mappings" in payload:
        lines.extend(["## Bulk mappings", ""])
        for mapping in payload["mappings"]:
            lines.append(
                f"- `{mapping['name']}` → {mapping['target']}: {mapping['description']} ({mapping['url']})"
            )
        lines.append("")
    if "columns" in payload:
        lines.extend(["## Result columns", ""])
        for column in payload["columns"]:
            lines.append(f"- `{column['id']}` ({column['kind']}) — {column['description']}")
        lines.append("")
    if "programmatic" in payload:
        lines.extend(["## Programmatic use", "", payload["programmatic"], ""])
    return "\n".join(lines).rstrip() + "\n"


__all__ = [
    "QUERY_FIELDS",
    "QUERY_GRAMMAR_NOTES",
    "QueryField",
    "docs_payload",
    "render_docs",
]
