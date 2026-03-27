from __future__ import annotations

import argparse
import sys
from typing import Any

from .client import RheaHttpClient
from .columns import DEFAULT_COLUMNS
from .core import RheaError, RheaService, parse_columns


def _add_common_connection_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--email")
    parser.add_argument("--timeout", type=float)
    parser.add_argument("--base-url")
    parser.add_argument("--ftp-base-url")


def _add_query_args(parser: argparse.ArgumentParser, *, default_columns: list[str]) -> None:
    parser.add_argument("--columns", default=",".join(default_columns))
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--format", choices=["json", "jsonl", "text", "tsv"], default="text")
    parser.add_argument("--fetch-all", action="store_true")
    parser.add_argument("--page-size", type=int)
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--cursor-file")
    parser.add_argument("--resume", action="store_true")


def _configure_download_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("rhea_id")
    parser.add_argument("--direction", choices=["auto", "master", "lr", "rl", "bi"], default="auto")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rhea")
    _add_common_connection_args(parser)
    subparsers = parser.add_subparsers(dest="command")

    search = subparsers.add_parser("search")
    search.add_argument("query", nargs="?")
    _add_query_args(search, default_columns=DEFAULT_COLUMNS)

    table = subparsers.add_parser("table")
    table.add_argument("query", nargs="?")
    _add_query_args(table, default_columns=DEFAULT_COLUMNS)

    for command_name, arg_name in [
        ("term", "text"),
        ("compound", "chebi"),
        ("neighborhood", "chebi"),
        ("enzyme", "ec"),
        ("protein", "uniprot"),
        ("publication", "pubmed"),
    ]:
        command = subparsers.add_parser(command_name)
        command.add_argument(arg_name)
        _add_query_args(
            command,
            default_columns=DEFAULT_COLUMNS
            if command_name != "publication"
            else ["rhea-id", "equation", "pubmed", "ec", "uniprot"],
        )

    reaction = subparsers.add_parser("reaction")
    reaction.add_argument("rhea_id")
    reaction.add_argument("--columns", default=",".join(DEFAULT_COLUMNS))
    reaction.add_argument(
        "--direction", choices=["auto", "master", "lr", "rl", "bi"], default="auto"
    )
    reaction.add_argument("--format", choices=["json", "text", "tsv"], default="json")

    fetch = subparsers.add_parser("fetch")
    fetch.add_argument("rhea_id")
    fetch.add_argument("--columns", default=",".join(DEFAULT_COLUMNS))
    fetch.add_argument("--direction", choices=["auto", "master", "lr", "rl", "bi"], default="auto")
    fetch.add_argument("--format", choices=["json", "text", "tsv", "rxn", "rd"], default="json")

    download = subparsers.add_parser("download")
    _configure_download_args(download)
    download.add_argument("--file-format", choices=["rxn", "rd"], required=True)

    for simple in [
        "directions",
        "counterparts",
        "canonicalize",
        "equation",
        "participants",
        "xrefs",
        "explain",
    ]:
        command = subparsers.add_parser(simple)
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

    ids = subparsers.add_parser("ids")
    ids.add_argument("query")
    ids.add_argument("--limit", type=int, default=20)
    ids.add_argument("--format", choices=["json", "jsonl", "text", "tsv"], default="text")
    ids.add_argument("--fetch-all", action="store_true")
    ids.add_argument("--page-size", type=int)
    ids.add_argument("--page", type=int, default=1)
    ids.add_argument("--cursor-file")
    ids.add_argument("--resume", action="store_true")

    grep = subparsers.add_parser("grep")
    grep.add_argument("text")
    grep.add_argument("--limit", type=int, default=20)
    grep.add_argument("--format", choices=["json", "jsonl", "text", "tsv"], default="text")
    grep.add_argument("--fetch-all", action="store_true")
    grep.add_argument("--page-size", type=int)
    grep.add_argument("--page", type=int, default=1)
    grep.add_argument("--cursor-file")
    grep.add_argument("--resume", action="store_true")

    columns = subparsers.add_parser("columns")
    columns.add_argument("--format", choices=["json", "text", "tsv"], default="text")

    for grouping in ["enzymes-for", "proteins-for"]:
        command = subparsers.add_parser(grouping)
        command.add_argument("chebi")
        command.add_argument("--limit", type=int, default=100)
        command.add_argument("--format", choices=["json", "text", "tsv"], default="text")

    resolve = subparsers.add_parser("resolve")
    resolve.add_argument("terms", nargs="+")
    resolve.add_argument("--limit", type=int, default=5)
    resolve.add_argument("--format", choices=["json", "text"], default="json")

    release = subparsers.add_parser("release")
    release_sub = release.add_subparsers(dest="release_command")
    current = release_sub.add_parser("current")
    current.add_argument("--format", choices=["json", "text"], default="json")
    listing = release_sub.add_parser("list")
    listing.add_argument("--format", choices=["json", "text", "tsv"], default="text")
    files = release_sub.add_parser("files")
    files.add_argument("category", choices=["tsv", "rdf", "biopax", "ctfiles", "all"])
    files.add_argument("--format", choices=["json", "text", "tsv"], default="text")
    bundle = release_sub.add_parser("bundle")
    bundle.add_argument("release", nargs="?", default="current")
    bundle.add_argument("--format", choices=["json", "text"], default="json")

    archive = subparsers.add_parser("archive")
    archive_sub = archive.add_subparsers(dest="archive_command")
    ls_cmd = archive_sub.add_parser("ls")
    ls_cmd.add_argument("path", nargs="?", default="tsv/")
    ls_cmd.add_argument("--format", choices=["json", "text", "tsv"], default="text")
    members = archive_sub.add_parser("members")
    members.add_argument("path")
    members.add_argument("--limit", type=int, default=200)
    members.add_argument("--format", choices=["json", "text", "tsv"], default="text")
    dl = archive_sub.add_parser("download")
    dl.add_argument("path_or_url")
    dl.add_argument("output")
    dl.add_argument("--format", choices=["json", "text"], default="json")
    return parser


def _build_service(args: argparse.Namespace) -> RheaService:
    return RheaService(
        RheaHttpClient(
            base_url=args.base_url,
            ftp_base_url=args.ftp_base_url,
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
