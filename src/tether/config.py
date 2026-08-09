from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv() -> None:
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv()


@dataclass(frozen=True)
class Settings:
    gms_url: str = os.getenv("DATAHUB_GMS_URL", "http://localhost:8080")
    frontend_url: str = os.getenv("DATAHUB_FRONTEND_URL", "http://localhost:9002")
    token: str = os.getenv("DATAHUB_TOKEN", "")
    timeout: int = int(os.getenv("TETHER_TIMEOUT", "30"))
    demo_mode: bool = os.getenv("DEMO_MODE", "0") == "1"
    record: bool = os.getenv("TETHER_RECORD", "0") == "1"
    # which recorded fixture set to replay/record (cold vs warm graph), for the offline loop demo
    fixture_set: str = os.getenv("TETHER_FIXTURE_SET", "")
    ledger_path: Path = ROOT / "predictions.jsonl"

    @property
    def fixture_dir(self) -> Path:
        base = ROOT / "fixtures"
        return base / self.fixture_set if self.fixture_set else base
    # where the feature-engineering SQL lives. Tether reads this (not the graph) to get the
    # column precision DataHub's dataset-level ML lineage does not store.
    features_dir: Path = Path(os.getenv("TETHER_FEATURES_DIR", str(ROOT / "demo" / "warehouse" / "features")))

    # github
    gh_token: str = os.getenv("GITHUB_TOKEN", "")
    gh_repo: str = os.getenv("GITHUB_REPOSITORY", "")

    def entity_url(self, urn: str) -> str:
        kind = urn.split(":")[2] if urn.startswith("urn:li:") else "dataset"
        return f"{self.frontend_url}/{kind}/{urn}"


settings = Settings()
