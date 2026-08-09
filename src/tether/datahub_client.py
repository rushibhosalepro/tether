"""One place that talks to DataHub. GraphQL for reads and incidents, SDK for emitting.

DEMO_MODE=1 serves recorded responses from fixtures/ so the demo survives a dead Docker.
"""

from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Any

import requests

from .config import settings

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


class DataHubError(RuntimeError):
    pass


class DataHubClient:
    def __init__(self, gms_url: str | None = None, token: str | None = None):
        self.gms_url = (gms_url or settings.gms_url).rstrip("/")
        self.token = token or settings.token
        self._session = requests.Session()
        if self.token:
            self._session.headers["Authorization"] = f"Bearer {self.token}"
        self._session.headers["Content-Type"] = "application/json"

    # ---------- transport ----------

    def graphql(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        variables = variables or {}
        if settings.demo_mode:
            return self._replay(query, variables)

        resp = self._session.post(
            f"{self.gms_url}/api/graphql",
            json={"query": query, "variables": variables},
            timeout=settings.timeout,
        )
        if resp.status_code >= 400:
            raise DataHubError(f"{resp.status_code} from GMS: {resp.text[:500]}")
        body = resp.json()
        if body.get("errors"):
            raise DataHubError(json.dumps(body["errors"])[:800])
        if settings.record:
            self._record(query, variables, body)
        return body["data"]

    def health(self) -> bool:
        try:
            r = self._session.get(f"{self.gms_url}/health", timeout=5)
            return r.ok
        except requests.RequestException:
            return False

    # ---------- fixtures ----------

    @staticmethod
    def _key(query: str, variables: dict[str, Any]) -> str:
        blob = json.dumps({"q": " ".join(query.split()), "v": variables}, sort_keys=True)
        return hashlib.sha1(blob.encode()).hexdigest()[:16]

    def _record(self, query: str, variables: dict[str, Any], body: dict) -> None:
        d = settings.fixture_dir
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{self._key(query, variables)}.json").write_text(json.dumps(body, indent=2), encoding="utf-8")

    def _replay(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        path = settings.fixture_dir / f"{self._key(query, variables)}.json"
        if not path.exists():
            raise DataHubError(
                f"DEMO_MODE: no fixture for this query ({path.name}). "
                "Re-record with TETHER_RECORD=1 against a live DataHub."
            )
        return json.loads(path.read_text(encoding="utf-8"))["data"]


_client: DataHubClient | None = None


def client() -> DataHubClient:
    global _client
    if _client is None:
        _client = DataHubClient()
    return _client
