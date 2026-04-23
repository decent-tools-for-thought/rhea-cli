from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

DEFAULT_BASE_URL = "https://www.rhea-db.org"
DEFAULT_FTP_BASE_URL = "https://ftp.expasy.org/databases/rhea"
DEFAULT_SPARQL_BASE_URL = "https://sparql.rhea-db.org"
DEFAULT_TIMEOUT_SECONDS = 30.0


class RheaClientError(RuntimeError):
    pass


@dataclass
class Response:
    status: int
    headers: dict[str, str]
    body: bytes

    @property
    def content_type(self) -> str:
        return self.headers.get("content-type", "")

    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")

    def json(self) -> Any:
        return json.loads(self.text())


class RheaHttpClient:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        ftp_base_url: str | None = None,
        sparql_base_url: str | None = None,
        timeout: float | None = None,
        user_agent: str | None = None,
        email: str | None = None,
    ) -> None:
        self.base_url = (base_url or os.environ.get("RHEA_BASE_URL") or DEFAULT_BASE_URL).rstrip(
            "/"
        )
        self.ftp_base_url = (
            ftp_base_url or os.environ.get("RHEA_FTP_BASE_URL") or DEFAULT_FTP_BASE_URL
        ).rstrip("/")
        self.sparql_base_url = (
            sparql_base_url or os.environ.get("RHEA_SPARQL_BASE_URL") or DEFAULT_SPARQL_BASE_URL
        ).rstrip("/")
        timeout_raw = os.environ.get("RHEA_TIMEOUT_SECONDS")
        self.timeout = (
            timeout if timeout is not None else float(timeout_raw or DEFAULT_TIMEOUT_SECONDS)
        )
        self.user_agent = user_agent or os.environ.get("RHEA_USER_AGENT") or "rhea-cli/0.1.0"
        self.email = email or os.environ.get("RHEA_EMAIL")

    def request(
        self,
        *,
        method: str,
        path: str,
        query: dict[str, Any] | None = None,
        base: str = "web",
        accept: str = "*/*",
    ) -> Response:
        query_items: list[tuple[str, str]] = []
        for key, value in (query or {}).items():
            if value is None:
                continue
            if isinstance(value, (list, tuple)):
                query_items.extend((key, str(item)) for item in value)
            else:
                query_items.append((key, str(value)))

        root = (
            self.base_url
            if base == "web"
            else self.ftp_base_url
            if base == "ftp"
            else self.sparql_base_url
        )
        url = (
            path
            if path.startswith("http://") or path.startswith("https://")
            else f"{root}/{path.lstrip('/')}"
        )
        if query_items:
            url = f"{url}?{urllib.parse.urlencode(query_items, doseq=True)}"

        headers = {
            "Accept": accept,
            "User-Agent": self._user_agent_value(),
        }
        request = urllib.request.Request(url, headers=headers, method=method.upper())
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return Response(
                    status=response.status,
                    headers={key.lower(): value for key, value in response.headers.items()},
                    body=response.read(),
                )
        except urllib.error.HTTPError as exc:
            payload = exc.read().decode("utf-8", errors="replace")
            raise RheaClientError(f"{exc.code} {exc.reason}: {url}\n{payload}") from exc
        except urllib.error.URLError as exc:
            raise RheaClientError(f"request failed for {url}: {exc.reason}") from exc

    def _user_agent_value(self) -> str:
        if self.email:
            return f"{self.user_agent} ({self.email})"
        return self.user_agent
