"""Utilities shared by sample-gate/report scripts."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_structured_file(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        try:
            import yaml  # type: ignore
        except Exception as exc:  # pragma: no cover - optional dependency fallback
            raise ValueError(
                f"Cannot parse structured file {path}. Install PyYAML or use JSON-compatible content."
            ) from exc
        payload = yaml.safe_load(text)

    if not isinstance(payload, dict):
        raise ValueError(f"Structured file {path} must contain a JSON/YAML object")
    return payload


def normalized_category_counts(samples: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for sample in samples:
        category = str(sample.get("category") or "").strip()
        if not category:
            continue
        counts[category] = counts.get(category, 0) + 1
    return counts

