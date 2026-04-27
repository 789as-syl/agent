from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

EXCLUDED_DIRS = {
    "node_modules",
    "dist",
    "__pycache__",
    ".venv",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
}
CODE_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx"}


@dataclass(frozen=True)
class FileStat:
    path: str
    lines: int
    sha256: str


def iter_code_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in EXCLUDED_DIRS for part in path.parts):
            continue
        if path.suffix.lower() not in CODE_EXTENSIONS:
            continue
        files.append(path)
    return files


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def file_lines(path: Path) -> int:
    return sum(1 for _ in path.open("r", encoding="utf-8", errors="ignore"))


def collect_stats(files: list[Path], project_root: Path) -> list[FileStat]:
    stats: list[FileStat] = []
    for file_path in files:
        stats.append(
            FileStat(
                path=str(file_path.relative_to(project_root)).replace("\\", "/"),
                lines=file_lines(file_path),
                sha256=file_sha256(file_path),
            )
        )
    return stats


def frontend_duplication(stats: list[FileStat]) -> dict[str, Any]:
    target_prefixes = (
        "front/shared/api/",
        "front/shared/types/",
        "front/client/src/api/",
        "front/client/src/types/",
        "front/admin/src/api/",
        "front/admin/src/types/",
    )
    candidates = [s for s in stats if s.path.startswith(target_prefixes)]
    if not candidates:
        return {
            "target_file_count": 0,
            "duplicate_file_count": 0,
            "duplicate_ratio": 0.0,
            "duplicate_groups": [],
        }

    groups: dict[str, list[str]] = {}
    for item in candidates:
        groups.setdefault(item.sha256, []).append(item.path)

    duplicate_groups = [paths for paths in groups.values() if len(paths) > 1]
    duplicate_file_count = sum(len(group) for group in duplicate_groups)
    duplicate_ratio = duplicate_file_count / len(candidates)
    return {
        "target_file_count": len(candidates),
        "duplicate_file_count": duplicate_file_count,
        "duplicate_ratio": round(duplicate_ratio, 4),
        "duplicate_groups": duplicate_groups,
    }


def count_cross_layer_violations(project_root: Path) -> list[dict[str, Any]]:
    checks = [
        ("app/api", "from app.repositories", "api_depends_on_repositories"),
        ("app/api", "from app.models", "api_depends_on_models"),
        ("app/services", "from app.api", "services_depends_on_api"),
        ("app/repositories", "from app.api", "repositories_depends_on_api"),
        ("app/repositories", "from app.services", "repositories_depends_on_services"),
        ("app/agents", "from app.api", "agents_depends_on_api"),
    ]

    violations: list[dict[str, Any]] = []
    for folder, needle, rule in checks:
        folder_path = project_root / folder
        if not folder_path.exists():
            continue
        for file_path in folder_path.rglob("*.py"):
            text = file_path.read_text(encoding="utf-8", errors="ignore")
            count = text.count(needle)
            if count == 0:
                continue
            violations.append(
                {
                    "rule": rule,
                    "file": str(file_path.relative_to(project_root)).replace("\\", "/"),
                    "count": count,
                    "needle": needle,
                }
            )
    return violations


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture baseline maintainability metrics.")
    parser.add_argument(
        "--scope",
        nargs="+",
        default=["front", "app"],
        help="Top-level directories to scan. Default: front app",
    )
    parser.add_argument(
        "--out",
        required=True,
        help="Output JSON path, e.g. .omx/artifacts/gate-a/baseline-metrics.json",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_root = Path.cwd()

    scoped_files: list[Path] = []
    for scope in args.scope:
        scope_path = project_root / scope
        if scope_path.exists():
            scoped_files.extend(iter_code_files(scope_path))

    stats = collect_stats(scoped_files, project_root)
    stats_sorted = sorted(stats, key=lambda item: item.lines, reverse=True)

    total_lines = sum(item.lines for item in stats)
    top_hotspots = [
        {"path": item.path, "lines": item.lines}
        for item in stats_sorted[:10]
    ]
    top1_lines = stats_sorted[0].lines if stats_sorted else 0
    top1_share = (top1_lines / total_lines) if total_lines else 0.0

    cross_layer_violations = count_cross_layer_violations(project_root)
    duplication = frontend_duplication(stats)

    result = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "scope": args.scope,
        "code_file_count": len(stats),
        "total_code_lines": total_lines,
        "top_hotspots": top_hotspots,
        "top1_hotspot_share": round(top1_share, 4),
        "frontend_duplication": duplication,
        "cross_layer_dependency_violations": {
            "count": len(cross_layer_violations),
            "items": cross_layer_violations,
        },
    }

    out_path = project_root / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(str(out_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
