"""Run offline intent-boundary evaluation for the three-tool runtime surface."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

try:
    from app.agents.native_agent_runner import _classify_query_intent as classify_query_intent
except Exception:  # pragma: no cover - fallback keeps script runnable in minimal envs.
    CASUAL_KEYWORDS = ("你好", "在吗", "哈喽", "闲聊", "聊天", "hello", "hi")
    DOMAIN_KEYWORDS = (
        "创业",
        "创新",
        "商业模式",
        "融资",
        "用户访谈",
        "市场",
        "路演",
        "bp",
        "mvp",
    )
    CONTEXT_KEYWORDS = (
        "知识库",
        "题库",
        "课程",
        "课件",
        "课上",
        "这门课",
        "老师",
        "文档",
        "项目",
        "代码",
        "agent",
        "逻辑",
        "app",
        "日志",
        "报错",
    )
    MATH_KEYWORDS = ("计算", "算一下", "公式", "比例", "增长率", "利润率", "roi", "npv", "irr")
    MATH_RE = re.compile(r"^[\d\s\+\-\*\/\(\)\.\%\^=]+$")

    def _normalize(text: str) -> str:
        return " ".join(str(text or "").strip().lower().split())

    def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
        for keyword in keywords:
            lowered = keyword.lower()
            if _is_ascii_keyword(lowered):
                pattern = r"(?<![a-z0-9])" + re.escape(lowered) + r"(?![a-z0-9])"
                if re.search(pattern, text):
                    return True
                continue
            if lowered in text:
                return True
        return False

    def _is_ascii_keyword(keyword: str) -> bool:
        allowed = set("abcdefghijklmnopqrstuvwxyz0123456789 -")
        return bool(keyword) and all(char in allowed for char in keyword)

    def _is_math(text: str) -> bool:
        if _contains_any(text, MATH_KEYWORDS):
            return True
        compact = text.replace(" ", "")
        return any(char.isdigit() for char in compact) and bool(MATH_RE.fullmatch(compact))

    def classify_query_intent(query: str) -> dict[str, str | bool]:
        normalized = _normalize(query)
        if not normalized:
            return {"short_circuit": True, "reason": "out_of_scope", "message": ""}
        if _is_math(normalized):
            return {"short_circuit": False, "reason": "math", "message": ""}
        if _contains_any(normalized, DOMAIN_KEYWORDS) or _contains_any(normalized, CONTEXT_KEYWORDS):
            return {"short_circuit": False, "reason": "domain", "message": ""}
        if _contains_any(normalized, CASUAL_KEYWORDS):
            return {"short_circuit": True, "reason": "casual_chat", "message": ""}
        return {"short_circuit": True, "reason": "out_of_scope", "message": ""}


DEFAULT_FIXTURE = Path("app/tests/fixtures/rag_boundary_eval_cases.json")


def load_case_files(paths: list[Path]) -> list[dict]:
    cases: list[dict] = []
    for path in paths:
        if not path.exists():
            raise FileNotFoundError(f"Fixture not found: {path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError(f"Fixture must contain a JSON array: {path}")
        for item in payload:
            if isinstance(item, dict):
                cases.append(item)
    return cases


def _predict(case: dict) -> dict:
    expected_use_kb = bool(case.get("expected_use_kb", False))
    query = str(case.get("query", ""))
    decision = classify_query_intent(query)
    short_circuit = bool(decision.get("short_circuit", False))
    reason_code = str(decision.get("reason", "unknown"))

    if short_circuit:
        recommended_action = "guidance"
        route_mode = "short_circuit"
        predicted_use_kb = False
    elif reason_code == "math":
        recommended_action = "math_calculator"
        route_mode = "tool_math"
        predicted_use_kb = False
    else:
        recommended_action = "knowledge_retrieval"
        route_mode = "retrieval_first"
        predicted_use_kb = True

    return {
        "id": str(case.get("id", "")),
        "category": str(case.get("category", "uncategorized")),
        "query": query,
        "expected_use_kb": expected_use_kb,
        "predicted_use_kb": predicted_use_kb,
        "route_mode": route_mode,
        "recommended_action": recommended_action,
        "reason_code": reason_code,
        "matched": expected_use_kb == predicted_use_kb,
    }


def evaluate_cases(cases: list[dict]) -> dict:
    predictions = [_predict(case) for case in cases]
    true_positive = sum(1 for item in predictions if item["expected_use_kb"] and item["predicted_use_kb"])
    true_negative = sum(1 for item in predictions if not item["expected_use_kb"] and not item["predicted_use_kb"])
    false_positive = sum(1 for item in predictions if not item["expected_use_kb"] and item["predicted_use_kb"])
    false_negative = sum(1 for item in predictions if item["expected_use_kb"] and not item["predicted_use_kb"])

    positive_denominator = true_positive + false_positive
    recall_denominator = true_positive + false_negative
    total = len(predictions)

    by_category: dict[str, dict[str, int]] = {}
    for item in predictions:
        bucket = by_category.setdefault(
            str(item["category"]),
            {"total": 0, "matched": 0, "expected_use_kb": 0, "predicted_use_kb": 0},
        )
        bucket["total"] += 1
        bucket["matched"] += int(bool(item["matched"]))
        bucket["expected_use_kb"] += int(bool(item["expected_use_kb"]))
        bucket["predicted_use_kb"] += int(bool(item["predicted_use_kb"]))

    return {
        "case_count": total,
        "precision": round(true_positive / positive_denominator, 4) if positive_denominator else 0.0,
        "recall": round(true_positive / recall_denominator, 4) if recall_denominator else 0.0,
        "accuracy": round((true_positive + true_negative) / total, 4) if total else 0.0,
        "confusion_matrix": {
            "true_positive": true_positive,
            "true_negative": true_negative,
            "false_positive": false_positive,
            "false_negative": false_negative,
        },
        "by_category": by_category,
        "predictions": predictions,
    }


def _build_summary(payload: dict, fixtures: list[Path]) -> str:
    matrix = payload["confusion_matrix"]
    lines = [
        "Fixtures:",
        *[f"- {path}" for path in fixtures],
        f"Cases: {payload['case_count']}",
        f"Precision: {payload['precision']}",
        f"Recall: {payload['recall']}",
        f"Accuracy: {payload['accuracy']}",
        (
            "Confusion Matrix: "
            f"TP={matrix['true_positive']} "
            f"TN={matrix['true_negative']} "
            f"FP={matrix['false_positive']} "
            f"FN={matrix['false_negative']}"
        ),
        "Policy: domain -> knowledge_retrieval, math -> math_calculator, casual/out-of-scope -> guidance",
        "",
        "Per-category:",
    ]
    for category, stats in sorted(payload["by_category"].items()):
        lines.append(
            f"- {category}: total={stats['total']} matched={stats['matched']} "
            f"expected_use_kb={stats['expected_use_kb']} predicted_use_kb={stats['predicted_use_kb']}"
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--extra-fixture", type=Path, action="append", default=[])
    parser.add_argument("--output-json", type=Path, default=None)
    parser.add_argument("--show-cases", action="store_true")
    args = parser.parse_args()

    fixture_paths = [args.fixture, *args.extra_fixture]
    cases = load_case_files(fixture_paths)
    payload = evaluate_cases(cases)

    if args.output_json:
        args.output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(_build_summary(payload, fixture_paths))
    if args.show_cases:
        print("\nPredictions:")
        for item in payload["predictions"]:
            print(
                f"- {item['id']}: expected_use_kb={item['expected_use_kb']} "
                f"predicted_use_kb={item['predicted_use_kb']} "
                f"route={item['route_mode']} "
                f"action={item['recommended_action']} reason={item['reason_code']}"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
