from __future__ import annotations

import hashlib
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from cogito_agent.tools.base import Tool

SENSITIVE_KEYS = ("api_key", "access_token", "password", "secret", "private_key")
BEARER_PATTERN = re.compile(r"Bearer\s+[A-Za-z0-9_\-\.]+", re.IGNORECASE)
SK_PATTERN = re.compile(r"sk-[A-Za-z0-9_\-]{8,}")
API_KEY_ASSIGNMENT_PATTERN = re.compile(r'api_key\s*=\s*"[^"]+"', re.IGNORECASE)


def redact_text(value: str) -> str:
    redacted = BEARER_PATTERN.sub("Bearer [REDACTED]", value)
    redacted = API_KEY_ASSIGNMENT_PATTERN.sub('api_key = "[REDACTED]"', redacted)
    redacted = SK_PATTERN.sub("[REDACTED]", redacted)
    return redacted


def redact_value(value: Any) -> Any:
    if isinstance(value, dict):
        return redact_mapping(value)
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


def redact_mapping(value: dict) -> dict:
    redacted = {}
    for key, item in value.items():
        if any(s in key.lower() for s in SENSITIVE_KEYS):
            redacted[key] = "[REDACTED]"
        else:
            redacted[key] = redact_value(item)
    return redacted


def _truncate_or_hash(text: str, max_chars: int, store_hash: bool = False, always_preview: bool = False) -> str:
    if not always_preview and len(text) <= max_chars:
        return text
    preview = text[:max_chars]
    if store_hash:
        h = hashlib.sha256(text.encode()).hexdigest()[:16]
        return f"{preview}... (len={len(text)}, sha256={h})"
    return f"{preview}... (len={len(text)})"


def sanitize_tool_arguments(tool: Tool, arguments: dict[str, Any]) -> dict[str, Any]:
    """Sanitize tool arguments for trace logging using the tool's trace_policy."""
    policy = tool.trace_policy
    sensitive = set(policy.get("sensitive_args", []))
    preview = set(policy.get("preview_args", []))
    max_chars = int(policy.get("max_preview_chars", 500))
    store_hash = bool(policy.get("store_hash", False))

    sanitized: dict[str, Any] = {}
    for key, value in arguments.items():
        if isinstance(value, str):
            value = redact_text(value)
        if key in sensitive:
            if isinstance(value, str):
                safe_chars = min(max_chars, 120)
                sanitized[key] = _truncate_or_hash(value, max_chars=safe_chars, store_hash=store_hash, always_preview=True)
            else:
                sanitized[key] = "[REDACTED]"
        elif key in preview:
            if isinstance(value, str):
                sanitized[key] = _truncate_or_hash(value, max_chars, store_hash=False, always_preview=False)
            else:
                sanitized[key] = str(value)[:max_chars] if value else str(value)
        else:
            sanitized[key] = redact_value(value)
    return sanitized


def sanitize_tool_result(tool: Tool, result_content: str) -> dict[str, Any]:
    """Sanitize tool result content for trace logging."""
    policy = tool.trace_policy
    max_chars = int(policy.get("max_preview_chars", 500))
    store_hash = bool(policy.get("store_hash", False))
    safe = _truncate_or_hash(result_content, max_chars, store_hash)
    return {"content": safe, "full_length": len(result_content)}
