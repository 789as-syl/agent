"""Helpers for locating a workspace-local Docling runtime bundle."""

from __future__ import annotations

import sys
from pathlib import Path


def ensure_docling_runtime_on_path() -> Path | None:
    """Add a vendored Docling runtime directory to ``sys.path`` when present."""
    candidate_roots = [
        Path(".vendor/docling_runtime"),
        Path.home() / ".codex" / "memories" / "docling_runtime_complete",
        Path.home() / ".codex" / "memories" / "docling_runtime",
        Path.home() / ".codex" / "memories" / "docling_runtime_overlay",
    ]
    first_root: Path | None = None
    for runtime_root in candidate_roots:
        try:
            exists = runtime_root.exists()
        except Exception:
            continue
        if not exists:
            continue
        resolved = str(runtime_root.resolve())
        if resolved not in sys.path:
            sys.path.insert(0, resolved)
        if first_root is None:
            first_root = runtime_root
    return first_root
