"""Generate admin analytics drift gate report JSON."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPORT_VERSION = "1.0"
DEFAULT_THRESHOLDS = {
    "request_count_pct": 0.5,
    "avg_latency_ms_pct": 10.0,
    "hit_rate_pp": 2.0,
    "graph_nodes_pct": 5.0,
    "graph_edges_pct": 5.0,
}


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _safe_pct_delta(current: float, baseline: float) -> float:
    if baseline == 0:
        return 0.0 if current == 0 else 100.0
    return abs((current - baseline) / baseline) * 100


def _load_metric_source(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _build_report(
    *,
    window_days: int,
    min_samples: int,
    baseline_file: Path | None,
    current_file: Path | None,
) -> dict[str, Any]:
    baseline = _load_metric_source(baseline_file)
    current = _load_metric_source(current_file)

    if baseline and current:
        baseline_metrics = dict(baseline.get("metrics", {}))
        current_metrics = dict(current.get("metrics", {}))
        sample_count = int(current.get("sample_count", 0))
    else:
        baseline_metrics = {}
        current_metrics = {}
        sample_count = 0

    request_count_delta = _safe_pct_delta(
        float(current_metrics.get("request_count", 0)),
        float(baseline_metrics.get("request_count", 0)),
    )
    avg_latency_delta = _safe_pct_delta(
        float(current_metrics.get("avg_latency_ms", 0)),
        float(baseline_metrics.get("avg_latency_ms", 0)),
    )
    graph_nodes_delta = _safe_pct_delta(
        float(current_metrics.get("graph_nodes", 0)),
        float(baseline_metrics.get("graph_nodes", 0)),
    )
    graph_edges_delta = _safe_pct_delta(
        float(current_metrics.get("graph_edges", 0)),
        float(baseline_metrics.get("graph_edges", 0)),
    )
    hit_rate_delta = abs(float(current_metrics.get("hit_rate", 0)) - float(baseline_metrics.get("hit_rate", 0)))

    metric_drift = {
        "request_count_pct": round(request_count_delta, 4),
        "avg_latency_ms_pct": round(avg_latency_delta, 4),
        "hit_rate_pp": round(hit_rate_delta, 4),
        "graph_nodes_pct": round(graph_nodes_delta, 4),
        "graph_edges_pct": round(graph_edges_delta, 4),
    }

    violations: list[dict[str, Any]] = []
    if sample_count < min_samples:
        violations.append(
            {
                "reason": "INSUFFICIENT_SAMPLES",
                "sample_count": sample_count,
                "min_samples": min_samples,
            }
        )
    for metric, threshold in DEFAULT_THRESHOLDS.items():
        observed = float(metric_drift[metric])
        if observed > float(threshold):
            violations.append(
                {
                    "metric": metric,
                    "observed": observed,
                    "threshold": float(threshold),
                }
            )

    gate_status = "PASS" if not violations else "FAIL"
    return {
        "report_version": REPORT_VERSION,
        "generated_at": _now_iso(),
        "gate_name": "analytics_drift_gate",
        "gate_status": gate_status,
        "sample_count": sample_count,
        "metric_drift": metric_drift,
        "thresholds": DEFAULT_THRESHOLDS,
        "violations": violations,
        "window_days": window_days,
        "baseline_file": str(baseline_file) if baseline_file else None,
        "current_file": str(current_file) if current_file else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--window-days", type=int, default=7)
    parser.add_argument("--min-samples", type=int, default=1000)
    parser.add_argument("--baseline-file", type=Path, default=None)
    parser.add_argument("--current-file", type=Path, default=None)
    args = parser.parse_args()

    report = _build_report(
        window_days=args.window_days,
        min_samples=args.min_samples,
        baseline_file=args.baseline_file,
        current_file=args.current_file,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[analytics_drift_gate] {report['gate_status']} -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
