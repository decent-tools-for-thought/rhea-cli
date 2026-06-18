from __future__ import annotations

import csv
import gzip
import io
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class MappingDataset:
    name: str
    file: str
    target: str
    description: str
    gzipped: bool = False


# Canonical Rhea cross-reference tables published under <ftp>/tsv/.
# These are the authoritative, release-pinned bulk mappings; prefer them over
# scraping the web query endpoint (e.g. ``search 'ec:*'``) when a full,
# stable mapping is needed.
MAPPING_DATASETS: dict[str, MappingDataset] = {
    "ec": MappingDataset(
        "ec", "rhea2ec.tsv", "EC", "Rhea reactions to Enzyme Commission (EC) numbers"
    ),
    "uniprot": MappingDataset(
        "uniprot", "rhea2uniprot.tsv", "UniProtKB", "Rhea reactions to UniProtKB proteins"
    ),
    "uniprot-sprot": MappingDataset(
        "uniprot-sprot",
        "rhea2uniprot_sprot.tsv",
        "UniProtKB/Swiss-Prot",
        "Rhea reactions to reviewed (Swiss-Prot) UniProtKB proteins",
    ),
    "uniprot-trembl": MappingDataset(
        "uniprot-trembl",
        "rhea2uniprot_trembl.tsv.gz",
        "UniProtKB/TrEMBL",
        "Rhea reactions to unreviewed (TrEMBL) UniProtKB proteins (large, gzipped)",
        gzipped=True,
    ),
    "go": MappingDataset("go", "rhea2go.tsv", "GO", "Rhea reactions to Gene Ontology (GO) terms"),
    "kegg": MappingDataset(
        "kegg", "rhea2kegg_reaction.tsv", "KEGG", "Rhea reactions to KEGG reactions"
    ),
    "metacyc": MappingDataset(
        "metacyc", "rhea2metacyc.tsv", "MetaCyc", "Rhea reactions to MetaCyc reactions"
    ),
    "ecocyc": MappingDataset(
        "ecocyc", "rhea2ecocyc.tsv", "EcoCyc", "Rhea reactions to EcoCyc reactions"
    ),
    "reactome": MappingDataset(
        "reactome", "rhea2reactome.tsv", "Reactome", "Rhea reactions to Reactome reactions"
    ),
    "macie": MappingDataset(
        "macie", "rhea2macie.tsv", "M-CSA", "Rhea reactions to M-CSA / MACiE entries"
    ),
    "xrefs": MappingDataset(
        "xrefs",
        "rhea2xrefs.tsv",
        "all xrefs",
        "Rhea reactions to every cross-referenced resource in one table",
    ),
}


class MappingClientProtocol(Protocol):
    ftp_base_url: str

    def request(
        self,
        *,
        method: str,
        path: str,
        query: dict[str, Any] | None = None,
        base: str = "web",
        accept: str = "*/*",
    ) -> Any: ...


def resolve_mapping(name: str) -> MappingDataset:
    key = name.strip().lower()
    dataset = MAPPING_DATASETS.get(key)
    if dataset is None:
        available = ", ".join(sorted(MAPPING_DATASETS))
        raise KeyError(f"unknown mapping '{name}'; choose one of: {available}")
    return dataset


def list_mapping_datasets(ftp_base_url: str) -> list[dict[str, str]]:
    return [
        {
            "name": dataset.name,
            "file": dataset.file,
            "target": dataset.target,
            "description": dataset.description,
            "url": f"{ftp_base_url}/tsv/{dataset.file}",
        }
        for dataset in MAPPING_DATASETS.values()
    ]


def parse_mapping_rows(
    text: str, *, limit: int | None = None
) -> tuple[list[str], list[dict[str, str]]]:
    reader = csv.reader(io.StringIO(text), delimiter="\t")
    header = next(reader, [])
    rows: list[dict[str, str]] = []
    for row in reader:
        if not row:
            continue
        values = list(row) + [""] * max(0, len(header) - len(row))
        rows.append({column: values[index] for index, column in enumerate(header)})
        if limit is not None and len(rows) >= limit:
            break
    return list(header), rows


def decode_mapping_body(body: bytes, *, gzipped: bool) -> str:
    raw = gzip.decompress(body) if gzipped else body
    return raw.decode("utf-8", errors="replace")
