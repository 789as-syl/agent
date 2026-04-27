from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SEARCH_ROOTS = [
    ROOT / "app",
    ROOT / "scripts",
    ROOT / "docs",
    ROOT / "alembic",
]
TEXT_SUFFIXES = {".py", ".md", ".json"}
FORBIDDEN_TOKENS = (
    "rewrite_query",
    "knowledge_retrieval_probe",
    "RewriteService",
    "RewriteResult",
    "build_rewrite_prompt",
    "agent_probe_",
    "probe_strength",
    "suggested_next_step",
)


def test_three_tool_surface_has_no_rewrite_or_probe_runtime_references() -> None:
    offenders: list[str] = []
    self_path = Path(__file__).resolve()

    for root in SEARCH_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix not in TEXT_SUFFIXES:
                continue
            if "__pycache__" in path.parts:
                continue
            if path.resolve() == self_path:
                continue
            text = path.read_text(encoding="utf-8")
            for token in FORBIDDEN_TOKENS:
                if token in text:
                    offenders.append(f"{path.relative_to(ROOT)} -> {token}")

    assert offenders == []
