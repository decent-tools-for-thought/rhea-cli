from __future__ import annotations

import argparse
import sys
from typing import Any

from .client import RheaHttpClient
from .columns import DEFAULT_COLUMNS
from .core import RheaError, RheaService, parse_columns
from .docs import render_docs
from .mappings import MAPPING_DATASETS
from .sparql import SPARQL_PRESETS, render_sparql_preset


def _add_common_connection_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--email", help="Contact email sent in the User-Agent header")
    parser.add_argument("--timeout", type=float, help="Per-request timeout in seconds")
    parser.add_argument("--base-url", help="Override the web query base URL")
    parser.add_argument("--ftp-base-url", help="Override the FTP/download base URL")
    parser.add_argument("--sparql-base-url", help="Override the SPARQL endpoint base URL")


def _add_query_args(parser: argparse.ArgumentParser, *, default_columns: list[str]) -> None:
    parser.add_argument(
        "--columns",
        default=",".join(default_columns),
        help="Comma-separated result columns (see 'rhea columns')",
    )
    parser.add_argument(
        "--limit", type=int, default=20, help="Max rows to return (ignored with --fetch-all)"
    )
    parser.add_argument(
        "--format", choices=["json", "jsonl", "text", "tsv"], default="text", help="Output format"
    )
    parser.add_argument(
        "--fetch-all",
        action="store_true",
        help="Export the complete result set, not just --limit rows",
    )
    parser.add_argument(
        "--page-size", type=int, help="Paginate the full result set into pages of this size"
    )
    parser.add_argument("--page", type=int, default=1, help="1-based page number when paginating")
    parser.add_argument("--cursor-file", help="Persist pagination state here for resumable scans")
    parser.add_argument(
        "--resume", action="store_true", help="Resume from the offset stored in --cursor-file"
    )


def _configure_download_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("rhea_id")
    parser.add_argument("--direction", choices=["auto", "master", "lr", "rl", "bi"], default="auto")


def _add_sparql_result_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--format", choices=["json", "text", "csv", "tsv", "raw"], default="text")
    parser.add_argument("--accept")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rhea",
        description=(
            "Command-line client for Rhea: reaction lookup, table and bulk export, "
            "cross-reference mappings, releases, archives, and SPARQL."
        ),
        epilog=(
            "Discovery: 'rhea docs' describes the whole surface, query grammar, and data "
            "sources; 'rhea fields' lists query fields; 'rhea columns' lists result columns. "
            "Bulk: 'rhea search <query> --fetch-all' exports the full table, and "
            "'rhea mappings get <name>' fetches the canonical rhea2* tables."
        ),
    )
    _add_common_connection_args(parser)
    subparsers = parser.add_subparsers(dest="command")

    search = subparsers.add_parser(
        "search", help="Query the reaction table; use --fetch-all for the full result set"
    )
    search.add_argument(
        "query",
        nargs="?",
        help="Query string; supports field:value and wildcards (see 'rhea fields'). Empty matches all.",
    )
    _add_query_args(search, default_columns=DEFAULT_COLUMNS)

    table = subparsers.add_parser("table", help="Query the reaction table (alias of search)")
    table.add_argument(
        "query",
        nargs="?",
        help="Query string; supports field:value and wildcards (see 'rhea fields'). Empty matches all.",
    )
    _add_query_args(table, default_columns=DEFAULT_COLUMNS)

    entity_help = {
        "term": ("text", "Free-text reaction search"),
        "compound": ("chebi", "Reactions containing a ChEBI compound"),
        "neighborhood": ("chebi", "Reactions containing a ChEBI compound (graph neighborhood)"),
        "enzyme": ("ec", "Reactions annotated with an EC number"),
        "protein": ("uniprot", "Reactions annotated to a UniProtKB accession"),
        "publication": ("pubmed", "Reactions cited by a PubMed identifier"),
    }
    for command_name, (arg_name, command_help) in entity_help.items():
        command = subparsers.add_parser(command_name, help=command_help)
        command.add_argument(arg_name, help=command_help)
        _add_query_args(
            command,
            default_columns=DEFAULT_COLUMNS
            if command_name != "publication"
            else ["rhea-id", "equation", "pubmed", "ec", "uniprot"],
        )

    reaction = subparsers.add_parser(
        "reaction", help="Fetch one reaction by Rhea ID with direction metadata"
    )
    reaction.add_argument("rhea_id")
    reaction.add_argument("--columns", default=",".join(DEFAULT_COLUMNS))
    reaction.add_argument(
        "--direction", choices=["auto", "master", "lr", "rl", "bi"], default="auto"
    )
    reaction.add_argument("--format", choices=["json", "text", "tsv"], default="json")

    fetch = subparsers.add_parser(
        "fetch", help="Fetch one reaction as table rows or an RXN/RD file"
    )
    fetch.add_argument("rhea_id")
    fetch.add_argument("--columns", default=",".join(DEFAULT_COLUMNS))
    fetch.add_argument("--direction", choices=["auto", "master", "lr", "rl", "bi"], default="auto")
    fetch.add_argument("--format", choices=["json", "text", "tsv", "rxn", "rd"], default="json")

    download = subparsers.add_parser("download", help="Download a directional RXN/RD reaction file")
    _configure_download_args(download)
    download.add_argument("--file-format", choices=["rxn", "rd"], required=True)

    simple_help = {
        "directions": "Show master/LR/RL/BI identifiers for a reaction",
        "counterparts": "Show directional counterparts of a reaction",
        "canonicalize": "Map any directional ID to its master reaction",
        "equation": "Print a reaction equation",
        "participants": "List ChEBI participants of a reaction",
        "xrefs": "Collect all cross-references for a reaction",
        "explain": "Print a human-readable reaction summary",
    }
    for simple, simple_summary in simple_help.items():
        command = subparsers.add_parser(simple, help=simple_summary)
        command.add_argument("rhea_id")
        if simple in {"directions", "counterparts", "canonicalize", "xrefs"}:
            command.add_argument(
                "--format",
                choices=["json", "text"],
                default="json" if simple == "xrefs" else "text",
            )
        elif simple == "equation":
            command.add_argument("--format", choices=["text", "json"], default="text")
        elif simple == "participants":
            command.add_argument("--format", choices=["json", "text", "tsv"], default="text")
        elif simple == "explain":
            command.add_argument(
                "--direction", choices=["auto", "master", "lr", "rl", "bi"], default="auto"
            )

    ids = subparsers.add_parser(
        "ids", help="Export rhea-id values for a query (supports --fetch-all)"
    )
    ids.add_argument("query")
    ids.add_argument("--limit", type=int, default=20, help="Max rows (ignored with --fetch-all)")
    ids.add_argument("--format", choices=["json", "jsonl", "text", "tsv"], default="text")
    ids.add_argument("--fetch-all", action="store_true", help="Export every matching rhea-id")
    ids.add_argument("--page-size", type=int)
    ids.add_argument("--page", type=int, default=1)
    ids.add_argument("--cursor-file")
    ids.add_argument("--resume", action="store_true")

    grep = subparsers.add_parser("grep", help="Free-text search returning rhea-id and equation")
    grep.add_argument("text")
    grep.add_argument("--limit", type=int, default=20, help="Max rows (ignored with --fetch-all)")
    grep.add_argument("--format", choices=["json", "jsonl", "text", "tsv"], default="text")
    grep.add_argument("--fetch-all", action="store_true", help="Export every matching row")
    grep.add_argument("--page-size", type=int)
    grep.add_argument("--page", type=int, default=1)
    grep.add_argument("--cursor-file")
    grep.add_argument("--resume", action="store_true")

    columns = subparsers.add_parser("columns", help="List selectable result columns")
    columns.add_argument("--format", choices=["json", "text", "tsv"], default="text")

    fields = subparsers.add_parser(
        "fields", help="List searchable query fields and wildcard grammar"
    )
    fields.add_argument("--format", choices=["json", "text", "tsv"], default="text")

    grouping_help = {
        "enzymes-for": "Group enzymes (EC) annotated to reactions of a ChEBI compound",
        "proteins-for": "Group proteins annotated to reactions of a ChEBI compound",
    }
    for grouping, grouping_summary in grouping_help.items():
        command = subparsers.add_parser(grouping, help=grouping_summary)
        command.add_argument("chebi")
        command.add_argument("--limit", type=int, default=100)
        command.add_argument("--format", choices=["json", "text", "tsv"], default="text")

    resolve = subparsers.add_parser(
        "resolve", help="Classify mixed identifiers and look each one up"
    )
    resolve.add_argument("terms", nargs="+")
    resolve.add_argument("--limit", type=int, default=5)
    resolve.add_argument("--format", choices=["json", "text"], default="json")

    release = subparsers.add_parser("release", help="Inspect releases and downloadable file groups")
    release_sub = release.add_subparsers(dest="release_command")
    current = release_sub.add_parser("current", help="Show the current release number and date")
    current.add_argument("--format", choices=["json", "text"], default="json")
    listing = release_sub.add_parser("list", help="List archived past releases")
    listing.add_argument("--format", choices=["json", "text", "tsv"], default="text")
    files = release_sub.add_parser("files", help="List downloadable files in a category")
    files.add_argument("category", choices=["tsv", "rdf", "biopax", "ctfiles", "all"])
    files.add_argument("--format", choices=["json", "text", "tsv"], default="text")
    bundle = release_sub.add_parser("bundle", help="Resolve the download URL for a release bundle")
    bundle.add_argument("release", nargs="?", default="current")
    bundle.add_argument("--format", choices=["json", "text"], default="json")

    archive = subparsers.add_parser("archive", help="Browse and extract FTP archive contents")
    archive_sub = archive.add_subparsers(dest="archive_command")
    ls_cmd = archive_sub.add_parser("ls", help="List files in an archive category directory")
    ls_cmd.add_argument("path", nargs="?", default="tsv/")
    ls_cmd.add_argument("--format", choices=["json", "text", "tsv"], default="text")
    members = archive_sub.add_parser("members", help="List members inside a tar archive")
    members.add_argument("path")
    members.add_argument("--limit", type=int, default=200)
    members.add_argument("--format", choices=["json", "text", "tsv"], default="text")
    dl = archive_sub.add_parser("download", help="Download an archive file to a local path")
    dl.add_argument("path_or_url")
    dl.add_argument("output")
    dl.add_argument("--format", choices=["json", "text"], default="json")

    mappings = subparsers.add_parser(
        "mappings", help="Download canonical rhea2* cross-reference tables"
    )
    mappings.set_defaults(mappings_parser=mappings)
    mappings_sub = mappings.add_subparsers(dest="mappings_command")
    mappings_list = mappings_sub.add_parser("list", help="List the available mapping datasets")
    mappings_list.add_argument("--format", choices=["json", "text", "tsv"], default="text")
    mappings_get = mappings_sub.add_parser(
        "get", help="Download or parse one mapping dataset (e.g. 'mappings get ec')"
    )
    mappings_get.add_argument("name", choices=sorted(MAPPING_DATASETS))
    mappings_get.add_argument(
        "--limit", type=int, default=None, help="Limit rows for parsed (tsv/json) output"
    )
    mappings_get.add_argument("--output", help="Write the raw file to this path instead of stdout")
    mappings_get.add_argument("--format", choices=["tsv", "json"], default="tsv")

    docs = subparsers.add_parser(
        "docs", help="Describe the CLI surface, query grammar, and data sources"
    )
    docs.add_argument(
        "selector",
        nargs="?",
        default="all",
        choices=["all", "commands", "query", "fields", "mappings", "columns"],
        help="Limit output to one section (default: all)",
    )
    docs.add_argument("--format", choices=["text", "json"], default="text")

    sparql = subparsers.add_parser("sparql", help="Run SPARQL queries and inspect the schema")
    sparql.set_defaults(sparql_parser=sparql)
    sparql_sub = sparql.add_subparsers(dest="sparql_command")

    sparql_query = sparql_sub.add_parser("query", help="Run an arbitrary SPARQL query")
    sparql_query.add_argument("query", nargs="?")
    sparql_query.add_argument("--file", help="Read the query from a file instead of the argument")
    _add_sparql_result_args(sparql_query)

    sparql_queries = sparql_sub.add_parser(
        "queries", help="List the built-in schema-discovery presets"
    )
    sparql_queries.add_argument("--format", choices=["json", "text", "tsv"], default="text")

    sparql_show = sparql_sub.add_parser("show", help="Print the source of a built-in preset")
    sparql_show.add_argument("name", choices=sorted(SPARQL_PRESETS))
    sparql_show.add_argument("--limit", type=int, default=25)
    sparql_show.add_argument("--format", choices=["text", "json"], default="text")

    for preset_name in sorted(SPARQL_PRESETS):
        preset = sparql_sub.add_parser(
            preset_name, help=f"Run the '{preset_name}' schema-discovery preset"
        )
        preset.add_argument("--limit", type=int, default=25)
        _add_sparql_result_args(preset)
    return parser


def _build_service(args: argparse.Namespace) -> RheaService:
    return RheaService(
        RheaHttpClient(
            base_url=args.base_url,
            ftp_base_url=args.ftp_base_url,
            sparql_base_url=args.sparql_base_url,
            timeout=args.timeout,
            email=args.email,
        )
    )


def _query_kwargs(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "fetch_all": getattr(args, "fetch_all", False),
        "page_size": getattr(args, "page_size", None),
        "page": getattr(args, "page", 1),
        "cursor_file": getattr(args, "cursor_file", None),
        "resume": getattr(args, "resume", False),
    }


def _render_items(result: dict[str, Any], output_format: str, columns: list[str]) -> str:
    payload: Any = result
    if output_format == "jsonl":
        payload = result["normalizedItems"]
    elif output_format == "json":
        payload = result
    elif output_format in {"text", "tsv"}:
        payload = result["items"]
    if output_format == "text":
        return _render_table(payload, columns)
    if output_format == "tsv":
        return _render_tsv(payload, columns)
    if output_format == "jsonl":
        return "\n".join(_to_json_line(item) for item in payload)
    return _to_json(payload)


def _render_table(items: list[dict[str, Any]], columns: list[str]) -> str:
    if not items:
        return ""
    widths = {
        column: max(len(column), *(len(_display_value(item.get(column, ""))) for item in items))
        for column in columns
    }
    lines = ["  ".join(column.ljust(widths[column]) for column in columns)]
    for item in items:
        lines.append(
            "  ".join(
                _display_value(item.get(column, "")).ljust(widths[column]) for column in columns
            )
        )
    return "\n".join(lines)


def _render_tsv(items: list[dict[str, Any]], columns: list[str]) -> str:
    rows = ["\t".join(columns)]
    rows.extend(
        "\t".join(_display_value(item.get(column, "")) for column in columns) for item in items
    )
    return "\n".join(rows)


def _to_json(payload: Any) -> str:
    import json

    return json.dumps(payload, indent=2, sort_keys=False)


def _to_json_line(payload: Any) -> str:
    import json

    return json.dumps(payload, sort_keys=False)


def _display_value(value: Any) -> str:
    if isinstance(value, list):
        if value and isinstance(value[0], dict):
            return ";".join(str(item.get("id") or item.get("label") or item) for item in value)
        return ";".join(str(item) for item in value)
    if isinstance(value, dict):
        return _to_json(value)
    return str(value)


def _resolve_sparql_query(args: argparse.Namespace) -> str:
    if getattr(args, "file", None):
        with open(args.file, "r", encoding="utf-8") as handle:
            return handle.read()
    query = getattr(args, "query", None)
    if isinstance(query, str) and query:
        return query
    raise RheaError("provide a SPARQL query string or --file")


def _render_sparql_result(payload: dict[str, Any], output_format: str) -> str:
    if output_format in {"csv", "tsv", "raw"}:
        return str(payload["body"])
    if output_format == "json":
        return _to_json(payload.get("raw", payload))
    if payload.get("kind") == "ask":
        return "true" if payload.get("boolean") else "false"
    if payload.get("kind") == "select":
        variables = list(payload.get("variables", []))
        return _render_table(payload.get("items", []), variables)
    return str(payload["body"])


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    if args.command is None:
        parser.print_help()
        return 0
    service = _build_service(args)
    try:
        if args.command in {"search", "table"}:
            columns = parse_columns(args.columns)
            result = service.search(
                query=args.query, columns=columns, limit=args.limit, **_query_kwargs(args)
            )
            print(_render_items(result, args.format, columns))
            return 0
        if args.command in {"term", "compound", "neighborhood", "enzyme", "protein", "publication"}:
            columns = parse_columns(args.columns)
            method = getattr(
                service,
                "compound" if args.command == "neighborhood" else args.command.replace("-", "_"),
            )
            value = (
                getattr(args, "text", None)
                or getattr(args, "chebi", None)
                or getattr(args, "ec", None)
                or getattr(args, "uniprot", None)
                or getattr(args, "pubmed", None)
            )
            result = method(value, columns=columns, limit=args.limit, **_query_kwargs(args))
            print(_render_items(result, args.format, columns))
            return 0
        if args.command in {"reaction", "fetch"}:
            columns = parse_columns(args.columns)
            if args.command == "fetch" and args.format in {"rxn", "rd"}:
                print(
                    service.fetch_ctfile(
                        args.rhea_id, direction=args.direction, file_format=args.format
                    )
                )
                return 0
            result = service.fetch_reaction(args.rhea_id, columns=columns, direction=args.direction)
            if args.format == "text":
                print(_render_table([result["summary"]], columns))
                print()
                print(_to_json(result["normalizedSummary"]))
            elif args.format == "tsv":
                print(_render_tsv([result["summary"]], columns))
            else:
                print(_to_json(result))
            return 0
        if args.command == "download":
            print(
                service.fetch_ctfile(
                    args.rhea_id, direction=args.direction, file_format=args.file_format
                )
            )
            return 0
        if args.command in {"directions", "counterparts", "canonicalize", "xrefs"}:
            payload = getattr(service, args.command.replace("-", "_"))(args.rhea_id)
            print(
                _to_json(payload)
                if args.format == "json"
                else _render_table([payload], list(payload))
            )
            return 0
        if args.command == "equation":
            payload = service.equation(args.rhea_id)
            print(_to_json(payload) if args.format == "json" else payload["equation"])
            return 0
        if args.command == "participants":
            payload = service.participants(args.rhea_id)
            if args.format == "json":
                print(_to_json(payload))
            else:
                print(
                    _render_items(
                        {
                            "items": payload["participants"],
                            "normalizedItems": payload["participants"],
                        },
                        args.format,
                        ["chebi-id", "name"],
                    )
                )
            return 0
        if args.command == "explain":
            print(service.explain(args.rhea_id, direction=args.direction))
            return 0
        if args.command == "ids":
            result = service.search(
                query=args.query, columns=["rhea-id"], limit=args.limit, **_query_kwargs(args)
            )
            print(_render_items(result, args.format, ["rhea-id"]))
            return 0
        if args.command == "grep":
            result = service.term(
                args.text, columns=["rhea-id", "equation"], limit=args.limit, **_query_kwargs(args)
            )
            print(_render_items(result, args.format, ["rhea-id", "equation"]))
            return 0
        if args.command == "columns":
            payload = service.list_columns()
            if args.format == "json":
                print(_to_json(payload))
            else:
                cols = ["id", "label", "kind", "description"]
                print(
                    _render_items(
                        {"items": payload["items"], "normalizedItems": payload["items"]},
                        args.format,
                        cols,
                    )
                )
            return 0
        if args.command == "fields":
            payload = service.list_query_fields()
            if args.format == "json":
                print(_to_json(payload))
            else:
                print(
                    _render_items(
                        {"items": payload["items"], "normalizedItems": payload["items"]},
                        args.format,
                        ["name", "example", "description"],
                    )
                )
            return 0
        if args.command == "enzymes-for":
            payload = service.enzymes_for(args.chebi, limit=args.limit)
            print(
                _to_json(payload)
                if args.format == "json"
                else _render_items(
                    {"items": payload["items"], "normalizedItems": payload["items"]},
                    args.format,
                    ["ec", "reaction-count", "reaction-ids"],
                )
            )
            return 0
        if args.command == "proteins-for":
            payload = service.proteins_for(args.chebi, limit=args.limit)
            print(
                _to_json(payload)
                if args.format == "json"
                else _render_items(
                    {"items": payload["items"], "normalizedItems": payload["items"]},
                    args.format,
                    ["uniprot-count", "reaction-count", "reaction-ids"],
                )
            )
            return 0
        if args.command == "resolve":
            payload = service.resolve(args.terms, limit=args.limit)
            print(
                _to_json(payload)
                if args.format == "json"
                else _render_table(payload, ["input", "kind"])
            )
            return 0
        if args.command == "release":
            if args.release_command == "current":
                payload = service.archives.release_info()
                print(
                    _to_json(payload)
                    if args.format == "json"
                    else _render_table([payload], list(payload))
                )
                return 0
            if args.release_command == "list":
                payload = service.archives.list_old_releases()
                cols = ["release", "file", "modified", "size", "url"]
                print(
                    _to_json(payload)
                    if args.format == "json"
                    else (
                        _render_tsv(payload, cols)
                        if args.format == "tsv"
                        else _render_table(payload, cols)
                    )
                )
                return 0
            if args.release_command == "files":
                categories = (
                    ["tsv", "rdf", "biopax", "ctfiles"]
                    if args.category == "all"
                    else [args.category]
                )
                items: list[dict[str, Any]] = []
                for category in categories:
                    items.extend(service.archives.category_manifest(category)["entries"])
                cols = ["name", "kind", "modified", "size", "url"]
                print(
                    _to_json(items)
                    if args.format == "json"
                    else (
                        _render_tsv(items, cols)
                        if args.format == "tsv"
                        else _render_table(items, cols)
                    )
                )
                return 0
            if args.release_command == "bundle":
                payload = service.archives.release_bundle(args.release)
                print(
                    _to_json(payload)
                    if args.format == "json"
                    else _render_table([payload], list(payload))
                )
                return 0
        if args.command == "mappings":
            if args.mappings_command is None:
                args.mappings_parser.print_help()
                return 0
            if args.mappings_command == "list":
                payload = service.list_mappings()
                cols = ["name", "target", "file", "description", "url"]
                if args.format == "json":
                    print(_to_json(payload))
                elif args.format == "tsv":
                    print(_render_tsv(payload["items"], cols))
                else:
                    print(_render_table(payload["items"], cols))
                return 0
            if args.mappings_command == "get":
                if args.output:
                    print(_to_json(service.download_mapping(args.name, args.output)))
                    return 0
                payload = service.fetch_mapping(args.name, limit=args.limit)
                if args.format == "json":
                    print(_to_json(payload))
                else:
                    print(_render_tsv(payload["items"], payload["columns"]))
                return 0
        if args.command == "docs":
            print(render_docs(args.selector, args.format, ftp_base_url=service.client.ftp_base_url))
            return 0
        if args.command == "sparql":
            if args.sparql_command is None:
                args.sparql_parser.print_help()
                return 0
            if args.sparql_command == "query":
                payload = service.sparql_query(
                    _resolve_sparql_query(args), output_format=args.format, accept=args.accept
                )
                print(_render_sparql_result(payload, args.format))
                return 0
            if args.sparql_command == "queries":
                payload = service.list_sparql_queries()
                if args.format == "json":
                    print(_to_json(payload))
                else:
                    print(
                        _render_items(
                            {"items": payload["items"], "normalizedItems": payload["items"]},
                            args.format,
                            ["name", "description"],
                        )
                    )
                return 0
            if args.sparql_command == "show":
                query = render_sparql_preset(args.name, limit=args.limit)
                if args.format == "json":
                    print(_to_json({"name": args.name, "limit": args.limit, "query": query}))
                else:
                    print(query)
                return 0
            payload = service.sparql_preset(
                args.sparql_command,
                limit=args.limit,
                output_format=args.format,
                accept=args.accept,
            )
            print(_render_sparql_result(payload, args.format))
            return 0
        if args.command == "archive":
            if args.archive_command == "ls":
                payload = service.archives.category_manifest(args.path)
                cols = ["name", "kind", "modified", "size", "url"]
                items = payload["entries"]
                print(
                    _to_json(payload)
                    if args.format == "json"
                    else (
                        _render_tsv(items, cols)
                        if args.format == "tsv"
                        else _render_table(items, cols)
                    )
                )
                return 0
            if args.archive_command == "members":
                payload = service.archives.archive_members(args.path, limit=args.limit)
                cols = ["name", "size", "type"]
                items = payload["members"]
                print(
                    _to_json(payload)
                    if args.format == "json"
                    else (
                        _render_tsv(items, cols)
                        if args.format == "tsv"
                        else _render_table(items, cols)
                    )
                )
                return 0
            if args.archive_command == "download":
                payload = service.archives.download(args.path_or_url, args.output)
                print(
                    _to_json(payload)
                    if args.format == "json"
                    else _render_table([payload], list(payload))
                )
                return 0
    except RheaError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    parser.print_help()
    return 0
