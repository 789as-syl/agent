"""Agent math tool."""

from __future__ import annotations

import ast
import math
from typing import Any

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from app.core.log_config import get_logger
from app.tools.result_protocol import build_tool_result

logger = get_logger(__name__)


class MathCalculatorInput(BaseModel):
    expression: str = Field(
        description=(
            "Required. Math expression to evaluate. Supports numbers, + - * / // % **, parentheses, "
            "and abs/round/min/max/sqrt/sin/cos/tan/log/exp/pi/e."
        ),
        examples=["(48000-30000)/48000", "(120+80)/5"],
    )


ALLOWED_BINARY_OPS: dict[type[ast.operator], Any] = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
    ast.FloorDiv: lambda a, b: a // b,
    ast.Mod: lambda a, b: a % b,
    ast.Pow: lambda a, b: a**b,
}

ALLOWED_UNARY_OPS: dict[type[ast.unaryop], Any] = {
    ast.UAdd: lambda a: +a,
    ast.USub: lambda a: -a,
}

ALLOWED_FUNCTIONS: dict[str, Any] = {
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "sqrt": math.sqrt,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "log": math.log,
    "exp": math.exp,
    "pi": math.pi,
    "e": math.e,
}


def _safe_eval(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.BinOp) and type(node.op) in ALLOWED_BINARY_OPS:
        return float(ALLOWED_BINARY_OPS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right)))
    if isinstance(node, ast.UnaryOp) and type(node.op) in ALLOWED_UNARY_OPS:
        return float(ALLOWED_UNARY_OPS[type(node.op)](_safe_eval(node.operand)))
    if isinstance(node, ast.Name) and node.id in {"pi", "e"}:
        return float(ALLOWED_FUNCTIONS[node.id])
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ALLOWED_FUNCTIONS:
        func = ALLOWED_FUNCTIONS[node.func.id]
        args = [_safe_eval(arg) for arg in node.args]
        return float(func(*args))
    raise ValueError("unsupported expression")


def create_math_tool() -> Any:
    """Create calculator tool for LangGraph ToolNode."""

    @tool(
        "math_calculator",
        args_schema=MathCalculatorInput,
        description=(
            "Purpose: perform deterministic math evaluation.\n"
            "Call when: the user request contains an explicit numeric expression or a concrete numeric solve request.\n"
            "Do not call when: the task is small talk, a concept explanation, factual retrieval, "
            "or a non-numeric open-ended discussion.\n"
            "Input: expression(string, required).\n"
            "Output: JSON with success, result, and message.\n"
            'Example input: {"expression":"(48000-30000)/48000"}.'
        ),
    )
    async def math_calculator(expression: str) -> dict[str, Any]:
        try:
            tree = ast.parse(expression, mode="eval")
            value = _safe_eval(tree)
            return build_tool_result(
                success=True,
                tool="math_calculator",
                message=f"calculation succeeded: {value}",
                result_count=1,
                expression=expression,
                result=value,
            )
        except Exception as exc:
            logger.warning("math calculator failed: %s", exc)
            return build_tool_result(
                success=False,
                tool="math_calculator",
                message="calculation failed",
                result_count=0,
                expression=expression,
                result=None,
                error=str(exc),
            )

    return math_calculator
