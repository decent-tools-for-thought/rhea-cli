from __future__ import annotations

import io
import json
import re
import tarfile
from dataclasses import dataclass
from typing import Any, Protocol, cast


@dataclass(frozen=True)
class ArchiveEntry:
    name: str
    modified: str
    size: str
    href: str
    kind: str


class HtmlClientProtocol(Protocol):
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


def parse_index(html_text: str) -> list[ArchiveEntry]:
    row_pattern = re.compile(r"<tr class=['\"](?:odd|even)['\"].*?</tr>", re.DOTALL)
    anchor_pattern = re.compile(r"<a href=['\"](?P<href>[^'\"]+)['\"]>(?P<name>[^<]+)</a>")
    cell_pattern = re.compile(r"<td[^>]*>(.*?)</td>", re.DOTALL)
    entries: list[ArchiveEntry] = []
    for row_match in row_pattern.finditer(html_text):
        row_html = row_match.group(0)
        anchor_match = anchor_pattern.search(row_html)
        if anchor_match is None:
            continue
        cells = [
            _strip_html(cell).replace("&nbsp;", "").strip()
            for cell in cell_pattern.findall(row_html)
        ]
        if len(cells) < 3:
            continue
        name = _strip_html(anchor_match.group("name")).strip()
        if name == "Parent Directory":
            continue
        modified = cells[-2]
        size = cells[-1]
        entries.append(
            ArchiveEntry(
                name=name,
                modified=modified,
                size=size,
                href=anchor_match.group("href"),
                kind="dir" if name.endswith("/") else "file",
            )
        )
    return entries


def _strip_html(value: str) -> str:
    return re.sub(r"<[^>]+>", "", value)


class ArchiveService:
    def __init__(self, client: HtmlClientProtocol) -> None:
        self.client = client

    def release_info(self) -> dict[str, str]:
        response = self.client.request(
            method="GET", path="rhea-release.properties", base="ftp", accept="text/plain"
        )
        info: dict[str, str] = {}
        for line in response.text().splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                info[key.strip()] = value.strip()
        return {
            "currentRelease": info.get("rhea.release.number", ""),
            "releaseDate": info.get("rhea.release.date", ""),
        }

    def list_old_releases(self) -> list[dict[str, str]]:
        return [
            {
                "release": entry.name.removesuffix(".tar.bz2"),
                "file": entry.name,
                "modified": entry.modified,
                "size": entry.size,
                "url": f"{self.client.ftp_base_url}/old_releases/{entry.name}",
            }
            for entry in self.list_directory("old_releases/")
            if entry.kind == "file" and entry.name.endswith(".tar.bz2")
        ]

    def list_directory(self, path: str) -> list[ArchiveEntry]:
        normalized = path.rstrip("/") + "/"
        response = self.client.request(
            method="GET", path=normalized, base="ftp", accept="text/html"
        )
        return parse_index(response.text())

    def category_manifest(self, category: str) -> dict[str, Any]:
        directory = category.rstrip("/") + "/"
        return {
            "category": category,
            "entries": [
                {
                    "name": entry.name,
                    "kind": entry.kind,
                    "modified": entry.modified,
                    "size": entry.size,
                    "url": f"{self.client.ftp_base_url}/{directory}{entry.name}",
                }
                for entry in self.list_directory(directory)
            ],
        }

    def release_bundle(self, release: str) -> dict[str, str]:
        current = self.release_info()["currentRelease"]
        resolved = current if release == "current" else release
        suffix = ".tar.bz2"
        if resolved == current:
            url = f"{self.client.ftp_base_url}/old_releases/{resolved}{suffix}"
        else:
            url = f"{self.client.ftp_base_url}/old_releases/{resolved}{suffix}"
        return {"release": resolved, "url": url}

    def download(self, path_or_url: str, output_path: str) -> dict[str, Any]:
        if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
            response = self.client.request(method="GET", path=path_or_url, base="ftp", accept="*/*")
        else:
            response = self.client.request(method="GET", path=path_or_url, base="ftp", accept="*/*")
        with open(output_path, "wb") as handle:
            handle.write(response.body)
        return {"path": output_path, "bytes": len(response.body)}

    def archive_members(self, path: str, *, limit: int = 200) -> dict[str, Any]:
        response = self.client.request(
            method="GET", path=path, base="ftp", accept="application/octet-stream"
        )
        with tarfile.open(fileobj=io.BytesIO(response.body), mode="r:*") as archive:
            members = [
                {
                    "name": member.name,
                    "size": member.size,
                    "type": "dir" if member.isdir() else "file",
                }
                for member in archive.getmembers()[:limit]
            ]
        return {"archive": path, "count": len(members), "members": members}


def load_cursor(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return cast(dict[str, Any], json.load(handle))


def save_cursor(path: str, payload: dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=False)
        handle.write("\n")
