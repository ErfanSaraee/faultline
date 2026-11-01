"""Automated secret, PII, and hidden Chain-of-Thought redaction engine."""

import re
from typing import Any

SENSITIVE_KEY_NAMES: frozenset[str] = frozenset(
    {
        "api_key",
        "apikey",
        "access_token",
        "auth_token",
        "authorization",
        "Bearer",
        "client_secret",
        "credit_card",
        "cvv",
        "password",
        " passwd",
        "private_key",
        "refresh_token",
        "secret",
        "secret_key",
        "ssn",
        "token",
    }
)

COT_KEY_NAMES: frozenset[str] = frozenset(
    {
        "chain_of_thought",
        "hidden_chain_of_thought",
        "internal_monologue",
        "raw_reasoning",
        "reasoning_tokens_raw",
    }
)

# الگوهای متنی برای کشف کلیدهای API، توکن‌های Bearer، ایمیل و کدهای شناسایی در متن آزاد
SECRET_TOKEN_PATTERN = re.compile(
    r"(?:sk-[a-zA-Z0-9_\-]{12,}|Bearer\s+[a-zA-Z0-9_\-\.~+/]+=*)"
)
EMAIL_PATTERN = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)
SSN_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")


class PayloadRedactor:
    """Recursively sanitizes dictionaries, lists, and strings before persistence."""

    def sanitize_dict(self, data: dict[str, Any]) -> dict[str, Any]:
        """Return a deep-sanitized copy of a dictionary payload."""
        sanitized: dict[str, Any] = {}
        for key, value in data.items():
            normalized_key = key.strip().lower()
            if normalized_key in COT_KEY_NAMES:
                sanitized[key] = "[REDACTED_COT]"
            elif normalized_key in SENSITIVE_KEY_NAMES or normalized_key.endswith(
                ("_secret", "_token", "_password", "_api_key")
            ):
                sanitized[key] = "[REDACTED_SECRET]"
            else:
                sanitized[key] = self.sanitize_value(value)
        return sanitized

    def sanitize_value(self, value: Any) -> Any:
        """Sanitize an arbitrary value (dict, list, str, or primitive)."""
        if isinstance(value, dict):
            return self.sanitize_dict(value)
        if isinstance(value, list):
            return [self.sanitize_value(item) for item in value]
        if isinstance(value, str):
            return self.sanitize_text(value)
        return value

    def sanitize_text(self, text: str) -> str:
        """Scrub inline secrets, Bearer tokens, emails, and SSNs from a string."""
        cleaned = SECRET_TOKEN_PATTERN.sub("[REDACTED_SECRET]", text)
        cleaned = EMAIL_PATTERN.sub("[REDACTED_EMAIL]", cleaned)
        cleaned = SSN_PATTERN.sub("[REDACTED_PII]", cleaned)
        return cleaned
