from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ColumnSpec:
    id: str
    label: str
    kind: str
    description: str


DOCUMENTED_COLUMN_SPECS: dict[str, ColumnSpec] = {
    "rhea-id": ColumnSpec("rhea-id", "Reaction identifier", "rhea-id", "Rhea reaction identifier"),
    "equation": ColumnSpec("equation", "Equation", "string", "Reaction equation"),
    "chebi": ColumnSpec("chebi", "ChEBI name", "list", "ChEBI participant names"),
    "chebi-id": ColumnSpec(
        "chebi-id", "ChEBI identifier", "chebi-id-list", "ChEBI participant identifiers"
    ),
    "ec": ColumnSpec("ec", "EC number", "ec-list", "Enzyme Commission numbers"),
    "uniprot": ColumnSpec(
        "uniprot", "Enzymes", "int", "Count of UniProtKB proteins annotated to the reaction"
    ),
    "go": ColumnSpec("go", "Gene Ontology", "go-list", "GO identifiers with labels"),
    "pubmed": ColumnSpec("pubmed", "PubMed", "pubmed-list", "PubMed identifiers"),
    "reaction-xref(EcoCyc)": ColumnSpec(
        "reaction-xref(EcoCyc)",
        "Cross-reference (EcoCyc)",
        "xref-list",
        "EcoCyc reaction cross-references",
    ),
    "reaction-xref(MetaCyc)": ColumnSpec(
        "reaction-xref(MetaCyc)",
        "Cross-reference (MetaCyc)",
        "xref-list",
        "MetaCyc reaction cross-references",
    ),
    "reaction-xref(KEGG)": ColumnSpec(
        "reaction-xref(KEGG)",
        "Cross-reference (KEGG)",
        "xref-list",
        "KEGG reaction cross-references",
    ),
    "reaction-xref(Reactome)": ColumnSpec(
        "reaction-xref(Reactome)",
        "Cross-reference (Reactome)",
        "xref-list",
        "Reactome reaction cross-references",
    ),
    "reaction-xref(M-CSA)": ColumnSpec(
        "reaction-xref(M-CSA)",
        "Cross-reference (N-CSA/MACiE)",
        "xref-list",
        "M-CSA / MACiE cross-references",
    ),
}

DOCUMENTED_COLUMNS = list(DOCUMENTED_COLUMN_SPECS)
DEFAULT_COLUMNS = ["rhea-id", "equation", "chebi-id", "ec", "uniprot"]
XREF_COLUMNS = [
    "rhea-id",
    "equation",
    "chebi",
    "chebi-id",
    "ec",
    "uniprot",
    "go",
    "pubmed",
    "reaction-xref(EcoCyc)",
    "reaction-xref(MetaCyc)",
    "reaction-xref(KEGG)",
    "reaction-xref(Reactome)",
    "reaction-xref(M-CSA)",
]


def parse_columns(raw: str | None) -> list[str]:
    if not raw:
        return list(DEFAULT_COLUMNS)
    columns = list(dict.fromkeys(item.strip() for item in raw.split(",") if item.strip()))
    if not columns:
        return list(DEFAULT_COLUMNS)
    return columns


def normalize_row(row: dict[str, str]) -> dict[str, Any]:
    return {column: normalize_column_value(column, value) for column, value in row.items()}


def normalize_column_value(column: str, value: str) -> Any:
    spec = DOCUMENTED_COLUMN_SPECS.get(column)
    if spec is None:
        return value
    if spec.kind == "string":
        return value
    if spec.kind == "int":
        return int(value) if value.strip() else 0
    if spec.kind == "list":
        return _split_values(value)
    if spec.kind == "chebi-id-list":
        values = _split_values(value)
        return [{"id": item} for item in values]
    if spec.kind == "ec-list":
        values = _split_values(value)
        return [{"id": item} for item in values]
    if spec.kind == "pubmed-list":
        values = _split_values(value)
        return [{"id": item} for item in values]
    if spec.kind == "xref-list":
        values = _split_values(value)
        return [{"id": item} for item in values]
    if spec.kind == "go-list":
        return _parse_go_values(value)
    if spec.kind == "rhea-id":
        return value
    return value


def summarize_normalized_value(value: Any) -> str:
    if isinstance(value, list):
        if value and isinstance(value[0], dict):
            return ";".join(str(item.get("id") or item.get("label") or item) for item in value)
        return ";".join(str(item) for item in value)
    return str(value)


def _split_values(value: str) -> list[str]:
    return [item.strip() for item in value.split(";") if item.strip()]


def _parse_go_values(value: str) -> list[dict[str, str]]:
    values = _split_values(value)
    parsed: list[dict[str, str]] = []
    for item in values:
        if " " in item:
            go_id, label = item.split(" ", 1)
            parsed.append({"id": go_id, "label": label})
        else:
            parsed.append({"id": item, "label": ""})
    return parsed
