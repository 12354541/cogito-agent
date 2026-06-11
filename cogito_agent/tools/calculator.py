from __future__ import annotations

import ast
import operator
from typing import Any

from cogito_agent.tools.base import Tool, ToolResult

_OPERATORS: dict[type[ast.operator], Any] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY: dict[type[ast.unaryop], Any] = {ast.UAdd: operator.pos, ast.USub: operator.neg}


class CalculatorTool(Tool):
    name = "calculator"
    description = "Evaluate a safe arithmetic expression."
    parameters = {
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "Arithmetic expression, for example: 128 * 37 + 42",
            }
        },
        "required": ["expression"],
        "additionalProperties": False,
    }
    risk_level = "read-only"

    async def execute(self, **kwargs: Any) -> ToolResult:
        expression = str(kwargs["expression"])
        try:
            value = _eval_expression(expression)
        except Exception as exc:
            return ToolResult(content="", success=False, error=f"Invalid expression: {exc}")
        return ToolResult(content=str(value), success=True, metadata={"expression": expression})


def _eval_expression(expression: str) -> int | float:
    node = ast.parse(expression, mode="eval")
    return _eval_node(node.body)


def _eval_node(node: ast.AST) -> int | float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPERATORS:
        return _OPERATORS[type(node.op)](_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _UNARY[type(node.op)](_eval_node(node.operand))
    raise ValueError(f"unsupported syntax: {ast.dump(node, include_attributes=False)}")
