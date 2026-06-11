from __future__ import annotations

import re
from typing import Any

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
