from __future__ import annotations

import csv
import io
import math
import re
from collections import defaultdict
from typing import Any, Protocol, cast

from .archive import ArchiveService, load_cursor, save_cursor
from .client import RheaHttpClient
from .columns import (
    DEFAULT_COLUMNS,
    XREF_COLUMNS,
    normalize_row,
    parse_columns,
    summarize_normalized_value,
)
from .sparql import (
    list_sparql_presets,
    parse_sparql_json,
    render_sparql_preset,
    sparql_accept_header,
)

FULL_SCAN_LIMIT = 200000
RHEA_ID_RE = re.compile(r"^(?:RHEA:)?\d+$", re.IGNORECASE)
CHEBI_RE = re.compile(r"^(?:CHEBI:)?\d+$", re.IGNORECASE)
EC_RE = re.compile(r"^(?:EC:)?\d+(?:\.\d+|\.-){0,3}$", re.IGNORECASE)
UNIPROT_RE = re.compile(
    r"^[A-NR-Z][0-9][A-Z0-9]{3}[0-9]$|^[OPQ][0-9][A-Z0-9]{3}[0-9]$", re.IGNORECASE
)
PUBMED_RE = re.compile(r"^\d+$")


class HttpClientProtocol(Protocol):
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


class RheaError(RuntimeError):
    pass


class RheaService:
    def __init__(self, client: HttpClientProtocol | None = None) -> None:
        self.client = client or RheaHttpClient()
        self.archives = ArchiveService(self.client)
        self._directions_by_any_id: dict[str, dict[str, str]] | None = None

    def search(
        self,
        *,
        query: str | None,
        columns: list[str],
        limit: int,
        fetch_all: bool = False,
        page_size: int | None = None,
        page: int = 1,
        cursor_file: str | None = None,
        resume: bool = False,
    ) -> dict[str, Any]:
        requested_limit = FULL_SCAN_LIMIT if fetch_all or page_size or cursor_file else limit
        rows = self._query_rows(query=query, columns=columns, limit=requested_limit)
        selected_rows = rows if (fetch_all or page_size or cursor_file) else rows[:limit]
        result = {
            "query": query or "",
            "columns": columns,
            "count": len(rows),
            "items": selected_rows,
            "normalizedItems": [normalize_row(item) for item in selected_rows],
        }
        if page_size or cursor_file:
            return self._paginate_result(
                result,
                page_size=page_size or limit,
                page=page,
                cursor_file=cursor_file,
                resume=resume,
            )
        if fetch_all:
            result["items"] = rows
            result["normalizedItems"] = [normalize_row(item) for item in rows]
        return result

    def term(self, text: str, *, columns: list[str], limit: int, **kwargs: Any) -> dict[str, Any]:
        return self.search(query=text, columns=columns, limit=limit, **kwargs)

    def compound(
        self, chebi: str, *, columns: list[str], limit: int, **kwargs: Any
    ) -> dict[str, Any]:
        return self.search(
            query=f"chebi:{normalize_chebi_id(chebi).split(':', 1)[1]}",
            columns=columns,
            limit=limit,
            **kwargs,
        )

    def enzyme(self, ec: str, *, columns: list[str], limit: int, **kwargs: Any) -> dict[str, Any]:
        return self.search(
            query=f"ec:{normalize_ec(ec).split(':', 1)[1]}", columns=columns, limit=limit, **kwargs
        )

    def protein(
        self, uniprot: str, *, columns: list[str], limit: int, **kwargs: Any
    ) -> dict[str, Any]:
        return self.search(
            query=f"uniprot:{normalize_uniprot(uniprot)}", columns=columns, limit=limit, **kwargs
        )

    def publication(
        self, pubmed: str, *, columns: list[str], limit: int, **kwargs: Any
    ) -> dict[str, Any]:
        return self.search(
            query=f"pubmed:{normalize_pubmed(pubmed)}", columns=columns, limit=limit, **kwargs
        )

    def fetch_reaction(self, rhea_id: str, *, columns: list[str], direction: str) -> dict[str, Any]:
        item = self._single_row(rhea_id, columns)
        directions = self.directions(rhea_id)
        resolved = self._resolve_direction(directions, direction=direction)
        return {
            "id": directions["requested"],
            "direction": directions["requestedRole"],
            "resolvedDirectionalId": format_rhea_id(resolved),
            "summary": item,
            "normalizedSummary": normalize_row(item),
            "directions": directions,
            "downloads": {
                "rxn": f"{self.client.ftp_base_url}/ctfiles/rxn/{resolved}.rxn",
                "rd": f"{self.client.ftp_base_url}/ctfiles/rd/{resolved}.rd",
            },
        }

    def fetch_ctfile(self, rhea_id: str, *, direction: str, file_format: str) -> str:
        directions = self.directions(rhea_id)
        resolved = self._resolve_direction(directions, direction=direction)
        response = self.client.request(
            method="GET",
            path=f"ctfiles/{file_format}/{resolved}.{file_format}",
            base="ftp",
            accept="text/plain",
        )
        return response.text()

    def directions(self, rhea_id: str) -> dict[str, str]:
        normalized = normalize_rhea_id(rhea_id)
        if self._directions_by_any_id is None:
            self._load_directions()
        assert self._directions_by_any_id is not None
        record = self._directions_by_any_id.get(normalized)
        if record is None:
            raise RheaError(f"no direction mapping found for {format_rhea_id(normalized)}")
        return {
            "requested": format_rhea_id(normalized),
            "requestedRole": self._role_for_requested(record, normalized),
            "master": format_rhea_id(record["master"]),
            "lr": format_rhea_id(record["lr"]),
            "rl": format_rhea_id(record["rl"]),
            "bi": format_rhea_id(record["bi"]),
        }

    def counterparts(self, rhea_id: str) -> dict[str, Any]:
        directions = self.directions(rhea_id)
        return {
            "requested": directions["requested"],
            "requestedRole": directions["requestedRole"],
            "counterparts": [
                {"role": role, "rhea-id": directions[role]}
                for role in ["master", "lr", "rl", "bi"]
                if role != directions["requestedRole"]
            ],
        }

    def canonicalize(self, rhea_id: str) -> dict[str, Any]:
        directions = self.directions(rhea_id)
        return {
            "requested": directions["requested"],
            "requestedRole": directions["requestedRole"],
            "canonical": directions["master"],
            "directions": directions,
        }

    def equation(self, rhea_id: str) -> dict[str, str]:
        item = self._single_row(rhea_id, ["rhea-id", "equation"])
        return {"rhea-id": item["rhea-id"], "equation": item.get("equation", "")}

    def participants(self, rhea_id: str) -> dict[str, Any]:
        item = self._single_row(rhea_id, ["rhea-id", "chebi", "chebi-id"])
        names = self._split_field(item.get("chebi", ""))
        ids = self._split_field(item.get("chebi-id", ""))
        participants = [
            {"chebi-id": chebi_id, "name": names[index] if index < len(names) else ""}
            for index, chebi_id in enumerate(ids)
        ]
        return {"rhea-id": item["rhea-id"], "participants": participants}

    def xrefs(self, rhea_id: str) -> dict[str, Any]:
        item = self._single_row(rhea_id, XREF_COLUMNS)
        normalized = normalize_row(item)
        return {
            "rhea-id": normalized["rhea-id"],
            "equation": normalized["equation"],
            "chebi": normalized["chebi"],
            "chebi-id": normalized["chebi-id"],
            "ec": normalized["ec"],
            "uniprot": normalized["uniprot"],
            "go": normalized["go"],
            "pubmed": normalized["pubmed"],
            "reaction-xrefs": {
                "EcoCyc": normalized["reaction-xref(EcoCyc)"],
                "MetaCyc": normalized["reaction-xref(MetaCyc)"],
                "KEGG": normalized["reaction-xref(KEGG)"],
                "Reactome": normalized["reaction-xref(Reactome)"],
                "M-CSA": normalized["reaction-xref(M-CSA)"],
            },
        }

    def explain(self, rhea_id: str, *, direction: str) -> str:
        reaction = self.fetch_reaction(rhea_id, columns=XREF_COLUMNS, direction=direction)
        xrefs = self.xrefs(rhea_id)
        lines = [
            f"Reaction: {reaction['id']}",
            f"Equation: {reaction['summary'].get('equation', '')}",
            f"Requested role: {reaction['direction']}",
            f"Resolved directional ID: {reaction['resolvedDirectionalId']}",
            f"EC: {summarize_normalized_value(xrefs['ec']) or '-'}",
            f"ChEBI IDs: {summarize_normalized_value(xrefs['chebi-id']) or '-'}",
            f"ChEBI names: {summarize_normalized_value(xrefs['chebi']) or '-'}",
            f"GO: {summarize_normalized_value(xrefs['go']) or '-'}",
            f"PubMed: {summarize_normalized_value(xrefs['pubmed']) or '-'}",
            f"UniProt count: {xrefs['uniprot']}",
            f"Reaction xrefs: {summarize_normalized_value(sum((xrefs['reaction-xrefs'][db] for db in xrefs['reaction-xrefs']), [])) or '-'}",
            f"RXN: {reaction['downloads']['rxn']}",
            f"RD: {reaction['downloads']['rd']}",
        ]
        return "\n".join(lines)

    def enzymes_for(self, chebi: str, *, limit: int) -> dict[str, Any]:
        result = self.compound(chebi, columns=["rhea-id", "ec"], limit=limit, fetch_all=True)
        groups: dict[str, list[str]] = defaultdict(list)
        for item in result["items"]:
            for ec in self._split_field(item.get("ec", "")):
                groups[ec].append(item["rhea-id"])
        items = [
            {"ec": ec, "reaction-count": len(ids), "reaction-ids": ";".join(ids)}
            for ec, ids in sorted(groups.items(), key=lambda entry: (-len(entry[1]), entry[0]))
        ]
        return {"query": normalize_chebi_id(chebi), "count": len(items), "items": items}

    def proteins_for(self, chebi: str, *, limit: int) -> dict[str, Any]:
        result = self.compound(chebi, columns=["rhea-id", "uniprot"], limit=limit, fetch_all=True)
        items = [
            {
                "uniprot-count": item.get("uniprot", "0"),
                "reaction-count": 1,
                "reaction-ids": item["rhea-id"],
            }
            for item in result["items"]
        ]
        items.sort(key=lambda item: (-int(item["uniprot-count"] or "0"), item["reaction-ids"]))
        return {"query": normalize_chebi_id(chebi), "count": len(items), "items": items}

    def resolve(self, terms: list[str], *, limit: int) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for term in terms:
            kind, normalized = self._classify_term(term)
            if kind == "rhea":
                results.append(
                    {
                        "input": term,
                        "kind": kind,
                        "result": self.fetch_reaction(
                            normalized, columns=DEFAULT_COLUMNS, direction="auto"
                        ),
                    }
                )
            elif kind == "chebi":
                results.append(
                    {
                        "input": term,
                        "kind": kind,
                        "result": self.compound(normalized, columns=DEFAULT_COLUMNS, limit=limit),
                    }
                )
            elif kind == "ec":
                results.append(
                    {
                        "input": term,
                        "kind": kind,
                        "result": self.enzyme(normalized, columns=DEFAULT_COLUMNS, limit=limit),
                    }
                )
            elif kind == "uniprot":
                results.append(
                    {
                        "input": term,
                        "kind": kind,
                        "result": self.protein(normalized, columns=DEFAULT_COLUMNS, limit=limit),
                    }
                )
            elif kind == "pubmed":
                results.append(
                    {
                        "input": term,
                        "kind": kind,
                        "result": self.publication(
                            normalized, columns=["rhea-id", "equation", "pubmed"], limit=limit
                        ),
                    }
                )
            else:
                results.append(
                    {
                        "input": term,
                        "kind": "term",
                        "result": self.term(term, columns=DEFAULT_COLUMNS, limit=limit),
                    }
                )
        return results

    def list_columns(self) -> dict[str, Any]:
        from .columns import DOCUMENTED_COLUMN_SPECS

        return {
            "count": len(DOCUMENTED_COLUMN_SPECS),
            "items": [
                {
                    "id": spec.id,
                    "label": spec.label,
                    "kind": spec.kind,
                    "description": spec.description,
                }
                for spec in DOCUMENTED_COLUMN_SPECS.values()
            ],
        }

    def sparql_query(
        self, query: str, *, output_format: str, accept: str | None = None
    ) -> dict[str, Any]:
        response = self.client.request(
            method="GET",
            path="/sparql",
            query={"query": query},
            base="sparql",
            accept=sparql_accept_header(output_format, accept),
        )
        payload: dict[str, Any] = {
            "query": query,
            "contentType": getattr(response, "content_type", ""),
            "body": response.text(),
        }
        if "json" in str(payload["contentType"]) or payload["body"].lstrip().startswith("{"):
            raw = response.json()
            payload["raw"] = raw
            payload.update(parse_sparql_json(raw))
        return payload

    def list_sparql_queries(self) -> dict[str, Any]:
        items = list_sparql_presets()
        return {"count": len(items), "items": items}

    def sparql_preset(
        self, name: str, *, limit: int, output_format: str, accept: str | None = None
    ) -> dict[str, Any]:
        query = render_sparql_preset(name, limit=limit)
        result = self.sparql_query(query, output_format=output_format, accept=accept)
        result["preset"] = name
        return result

    def _single_row(self, rhea_id: str, columns: list[str]) -> dict[str, str]:
        normalized = normalize_rhea_id(rhea_id)
        result = self.search(query=f"rhea:{normalized}", columns=columns, limit=1)
        if not result["items"]:
            raise RheaError(f"no Rhea reaction found for {format_rhea_id(normalized)}")
        return cast(dict[str, str], result["items"][0])

    def _query_rows(
        self, *, query: str | None, columns: list[str], limit: int
    ) -> list[dict[str, str]]:
        response = self.client.request(
            method="GET",
            path="/rhea/",
            query={
                "query": query or "",
                "columns": ",".join(columns),
                "format": "tsv",
                "limit": limit,
            },
            base="web",
            accept="text/plain",
        )
        rows = list(csv.reader(io.StringIO(response.text()), delimiter="\t"))
        items: list[dict[str, str]] = []
        for row in rows[1:]:
            if not row:
                continue
            values = list(row) + [""] * max(0, len(columns) - len(row))
            item = {column: values[index] for index, column in enumerate(columns)}
            items.append(item)
        return items

    def _paginate_result(
        self,
        result: dict[str, Any],
        *,
        page_size: int,
        page: int,
        cursor_file: str | None,
        resume: bool,
    ) -> dict[str, Any]:
        start = (page - 1) * page_size
        if cursor_file and resume:
            state = load_cursor(cursor_file)
            start = int(state.get("nextOffset", 0))
        total = int(result["count"])
        end = min(start + page_size, total)
        items = result["items"][start:end]
        normalized = [normalize_row(item) for item in items]
        page_result = {
            "query": result["query"],
            "columns": result["columns"],
            "count": total,
            "pageSize": page_size,
            "page": 1 if cursor_file and resume else page,
            "offset": start,
            "nextOffset": end if end < total else None,
            "totalPages": max(1, math.ceil(total / page_size)) if page_size else 1,
            "items": items,
            "normalizedItems": normalized,
        }
        if cursor_file:
            save_cursor(
                cursor_file,
                {
                    "query": result["query"],
                    "columns": result["columns"],
                    "pageSize": page_size,
                    "nextOffset": end,
                    "finished": end >= total,
                    "count": total,
                },
            )
            page_result["cursorFile"] = cursor_file
            page_result["finished"] = end >= total
        return page_result

    def _load_directions(self) -> None:
        rows = self._fetch_tsv_file("tsv/rhea-directions.tsv")
        mapping: dict[str, dict[str, str]] = {}
        for row in rows:
            record = {
                "master": normalize_rhea_id(row["RHEA_ID_MASTER"]),
                "lr": normalize_rhea_id(row["RHEA_ID_LR"]),
                "rl": normalize_rhea_id(row["RHEA_ID_RL"]),
                "bi": normalize_rhea_id(row["RHEA_ID_BI"]),
            }
            for key in record.values():
                mapping[key] = record
        self._directions_by_any_id = mapping

    def _fetch_tsv_file(self, path: str) -> list[dict[str, str]]:
        response = self.client.request(method="GET", path=path, base="ftp", accept="text/plain")
        return list(csv.DictReader(io.StringIO(response.text()), delimiter="\t"))

    def _resolve_direction(self, directions: dict[str, str], *, direction: str) -> str:
        if direction == "auto":
            if directions["requestedRole"] in {"lr", "rl", "bi"}:
                return normalize_rhea_id(directions[directions["requestedRole"]])
            return normalize_rhea_id(directions["lr"])
        if direction == "master":
            raise RheaError(
                "master reactions do not have standalone RXN/RD files; use lr, rl, bi, or auto"
            )
        return normalize_rhea_id(directions[direction])

    def _role_for_requested(self, record: dict[str, str], requested: str) -> str:
        for role in ["master", "lr", "rl", "bi"]:
            if record[role] == requested:
                return role
        return "master"

    def _split_field(self, value: str) -> list[str]:
        return [item.strip() for item in value.split(";") if item.strip()]

    def _classify_term(self, term: str) -> tuple[str, str]:
        raw = term.strip()
        if RHEA_ID_RE.match(raw):
            return "rhea", normalize_rhea_id(raw)
        if CHEBI_RE.match(raw):
            return "chebi", normalize_chebi_id(raw)
        if raw.lower().startswith("ec:") or EC_RE.match(raw):
            return "ec", normalize_ec(raw)
        if raw.lower().startswith("pmid:") or raw.lower().startswith("pubmed:"):
            return "pubmed", normalize_pubmed(raw.split(":", 1)[1])
        if UNIPROT_RE.match(raw.upper()):
            return "uniprot", normalize_uniprot(raw)
        if PUBMED_RE.match(raw):
            return "pubmed", normalize_pubmed(raw)
        return "term", raw


def normalize_rhea_id(value: str) -> str:
    cleaned = value.strip().upper()
    if cleaned.startswith("RHEA:"):
        cleaned = cleaned[5:]
    if not cleaned.isdigit():
        raise RheaError(f"invalid Rhea identifier: {value}")
    return cleaned


def format_rhea_id(value: str) -> str:
    return f"RHEA:{normalize_rhea_id(value)}"


def normalize_chebi_id(value: str) -> str:
    cleaned = value.strip().upper()
    if cleaned.startswith("CHEBI:"):
        cleaned = cleaned[6:]
    if not cleaned.isdigit():
        raise RheaError(f"invalid ChEBI identifier: {value}")
    return f"CHEBI:{cleaned}"


def normalize_ec(value: str) -> str:
    cleaned = value.strip().upper()
    if not cleaned.startswith("EC:"):
        cleaned = f"EC:{cleaned}"
    return cleaned


def normalize_uniprot(value: str) -> str:
    cleaned = value.strip().upper()
    if not UNIPROT_RE.match(cleaned):
        raise RheaError(f"invalid UniProt accession: {value}")
    return cleaned


def normalize_pubmed(value: str) -> str:
    cleaned = value.strip()
    if cleaned.upper().startswith("PMID:"):
        cleaned = cleaned[5:]
    if not cleaned.isdigit():
        raise RheaError(f"invalid PubMed identifier: {value}")
    return cleaned


__all__ = ["RheaError", "RheaService", "DEFAULT_COLUMNS", "parse_columns", "normalize_rhea_id"]
