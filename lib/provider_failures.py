from __future__ import annotations

import re
from typing import Any


PROVIDER_ERROR_CLASSES = (
    "rate_limit",
    "usage_limit",
    "authentication",
    "authorization",
    "service_unavailable",
    "timeout",
    "invalid_request",
    "model_unavailable",
    "response_contract",
    "unknown_provider_error",
)
PROVIDER_ERROR_SOURCE = "sanitized_stderr_classifier"
MAX_RETRY_AFTER_SECONDS = 86_400
MAX_PROVIDER_FAILURE_HISTORY_COUNT = 1_000_000

_RETRYABLE_CLASSES = {
    "rate_limit",
    "usage_limit",
    "service_unavailable",
    "timeout",
    "model_unavailable",
}
_CLASS_PATTERNS: tuple[tuple[str, tuple[re.Pattern[str], ...]], ...] = (
    ("rate_limit", (
        re.compile(r"\brate[ _-]?limit(?:ed|ing)?\b", re.IGNORECASE),
        re.compile(r"\btoo many requests\b", re.IGNORECASE),
        re.compile(r"\bhttp(?: status)?\s*429\b", re.IGNORECASE),
    )),
    ("usage_limit", (
        re.compile(r"\busage limit\b", re.IGNORECASE),
        re.compile(r"\b(?:usage )?quota (?:has been )?(?:exceeded|exhausted)\b", re.IGNORECASE),
        re.compile(r"\binsufficient[ _-]?quota\b", re.IGNORECASE),
        re.compile(r"\b(?:credit|token) (?:balance|allowance) (?:is )?(?:exhausted|depleted)\b", re.IGNORECASE),
    )),
    ("authentication", (
        re.compile(r"\bauthentication (?:failed|required|error)\b", re.IGNORECASE),
        re.compile(r"\bunauthenticated\b", re.IGNORECASE),
        re.compile(r"\b(?:invalid|missing) api key\b", re.IGNORECASE),
        re.compile(r"\bhttp(?: status)?\s*401\b", re.IGNORECASE),
    )),
    ("authorization", (
        re.compile(r"\bauthorization (?:failed|required|error)\b", re.IGNORECASE),
        re.compile(r"\bpermission denied\b", re.IGNORECASE),
        re.compile(r"\bforbidden\b", re.IGNORECASE),
        re.compile(r"\bhttp(?: status)?\s*403\b", re.IGNORECASE),
    )),
    ("model_unavailable", (
        re.compile(r"\bmodel (?:is )?(?:at capacity|unavailable|not available|not found)\b", re.IGNORECASE),
        re.compile(r"\b(?:selected )?model .{0,64}(?:does not exist|is not supported)\b", re.IGNORECASE),
    )),
    ("service_unavailable", (
        re.compile(r"\bservice (?:is )?(?:temporarily )?unavailable\b", re.IGNORECASE),
        re.compile(r"\btemporarily unavailable\b", re.IGNORECASE),
        re.compile(r"\bprovider (?:is )?(?:overloaded|at capacity)\b", re.IGNORECASE),
        re.compile(r"\bhttp(?: status)?\s*(?:502|503)\b", re.IGNORECASE),
    )),
    ("timeout", (
        re.compile(r"\brequest timed out\b", re.IGNORECASE),
        re.compile(r"\bprovider timeout\b", re.IGNORECASE),
        re.compile(r"\bdeadline exceeded\b", re.IGNORECASE),
        re.compile(r"\bhttp(?: status)?\s*504\b", re.IGNORECASE),
    )),
    ("invalid_request", (
        re.compile(r"\binvalid (?:api )?request\b", re.IGNORECASE),
        re.compile(r"\bbad request\b", re.IGNORECASE),
        re.compile(r"\bhttp(?: status)?\s*400\b", re.IGNORECASE),
    )),
    ("response_contract", (
        re.compile(r"\bresponse (?:did not|does not) match (?:the )?(?:required )?schema\b", re.IGNORECASE),
        re.compile(r"\bresponse (?:contract|schema) (?:failed|invalid|violation)\b", re.IGNORECASE),
        re.compile(r"\binvalid json response\b", re.IGNORECASE),
    )),
)
_PROVIDER_CONTEXT_PATTERNS = (
    re.compile(r"\bprovider (?:api|error|request|response|service)\b", re.IGNORECASE),
    re.compile(r"\b(?:openai|anthropic|codex) (?:api|provider|service)\b", re.IGNORECASE),
    re.compile(r"\bapi (?:request|response) failed\b", re.IGNORECASE),
    re.compile(r"\b(?:rate[ _-]?limit|too many requests|http(?: status)?\s*429)\b", re.IGNORECASE),
    re.compile(r"\b(?:usage limit|insufficient[ _-]?quota|quota (?:has been )?(?:exceeded|exhausted))\b", re.IGNORECASE),
    re.compile(r"\b(?:invalid|missing) api key\b", re.IGNORECASE),
    re.compile(r"\b(?:selected )?model .{0,64}(?:at capacity|unavailable|not available|not found|does not exist|is not supported)\b", re.IGNORECASE),
)
_RETRY_AFTER_PATTERNS = (
    re.compile(
        r"\b(?:retry(?:ing)?|try again)\s+(?:after|in)\s*[:=]?\s*(-?\d+)\s*"
        r"(seconds?|secs?|s|minutes?|mins?|m|hours?|hrs?|h)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bretry[- ]after\s*[:=]\s*(-?\d+)\s*"
        r"(seconds?|secs?|s|minutes?|mins?|m|hours?|hrs?|h)?\b",
        re.IGNORECASE,
    ),
)


class ProviderFailureError(ValueError):
    """Raised when bounded provider failure metadata violates its contract."""


def validate_provider_failure_history(value: Any, *, allow_none: bool = False) -> None:
    if value is None and allow_none:
        return
    if not isinstance(value, dict) or set(value) != {
        "count",
        "retryable_count",
        "resume_recommended_count",
        "by_class",
        "last_error",
        "recovered",
    }:
        raise ProviderFailureError("provider failure history fields are invalid")
    for field in ("count", "retryable_count", "resume_recommended_count"):
        count = value.get(field)
        if (
            not isinstance(count, int)
            or isinstance(count, bool)
            or not 0 <= count <= MAX_PROVIDER_FAILURE_HISTORY_COUNT
        ):
            raise ProviderFailureError("provider failure history count is invalid")
    if value["count"] < 1:
        raise ProviderFailureError("provider failure history count must be positive")
    if value["retryable_count"] > value["count"] or value["resume_recommended_count"] > value["count"]:
        raise ProviderFailureError("provider failure history guidance counts are inconsistent")
    by_class = value.get("by_class")
    if (
        not isinstance(by_class, dict)
        or not by_class
        or set(by_class) - set(PROVIDER_ERROR_CLASSES)
        or any(
            not isinstance(count, int)
            or isinstance(count, bool)
            or not 1 <= count <= MAX_PROVIDER_FAILURE_HISTORY_COUNT
            for count in by_class.values()
        )
        or sum(by_class.values()) != value["count"]
    ):
        raise ProviderFailureError("provider failure history class counts are invalid")
    validate_provider_error(value.get("last_error"))
    if value["last_error"]["class"] not in by_class:
        raise ProviderFailureError("provider failure history last class is inconsistent")
    if type(value.get("recovered")) is not bool:
        raise ProviderFailureError("provider failure recovery flag is invalid")


def record_provider_failure(
    history: dict[str, Any] | None,
    provider_error: dict[str, Any],
) -> dict[str, Any]:
    validate_provider_error(provider_error)
    validate_provider_failure_history(history, allow_none=True)
    if history is None:
        by_class: dict[str, int] = {}
        count = retryable_count = resume_recommended_count = 0
    else:
        by_class = dict(history["by_class"])
        count = history["count"]
        retryable_count = history["retryable_count"]
        resume_recommended_count = history["resume_recommended_count"]
    if count >= MAX_PROVIDER_FAILURE_HISTORY_COUNT:
        raise ProviderFailureError("provider failure history count limit was reached")
    error_class = provider_error["class"]
    by_class[error_class] = by_class.get(error_class, 0) + 1
    result = {
        "count": count + 1,
        "retryable_count": retryable_count + int(provider_error["retryable"]),
        "resume_recommended_count": resume_recommended_count + int(provider_error["resume_recommended"]),
        "by_class": {
            candidate: by_class[candidate]
            for candidate in PROVIDER_ERROR_CLASSES
            if candidate in by_class
        },
        "last_error": dict(provider_error),
        "recovered": False,
    }
    validate_provider_failure_history(result)
    return result


def mark_provider_failure_recovered(
    history: dict[str, Any] | None,
    *,
    recovered: bool,
) -> dict[str, Any] | None:
    validate_provider_failure_history(history, allow_none=True)
    if history is None:
        return None
    result = {**history, "recovered": recovered}
    validate_provider_failure_history(result)
    return result


def _retry_after_seconds(text: str) -> int | None:
    multipliers = {
        "s": 1, "sec": 1, "secs": 1, "second": 1, "seconds": 1,
        "m": 60, "min": 60, "mins": 60, "minute": 60, "minutes": 60,
        "h": 3600, "hr": 3600, "hrs": 3600, "hour": 3600, "hours": 3600,
    }
    for pattern in _RETRY_AFTER_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        try:
            value = int(match.group(1))
            unit = (match.group(2) or "seconds").lower()
            seconds = value * multipliers[unit]
        except (KeyError, OverflowError, TypeError, ValueError):
            return None
        return seconds if 1 <= seconds <= MAX_RETRY_AFTER_SECONDS else None
    return None


def classify_provider_failure(text: Any) -> dict[str, Any] | None:
    """Return fixed provider-neutral metadata without retaining input text."""

    if not isinstance(text, str) or not text:
        return None
    if not any(pattern.search(text) for pattern in _PROVIDER_CONTEXT_PATTERNS):
        return None
    error_class: str | None = None
    for candidate, patterns in _CLASS_PATTERNS:
        if any(pattern.search(text) for pattern in patterns):
            error_class = candidate
            break
    if error_class is None:
        error_class = "unknown_provider_error"
    if error_class is None:
        return None
    retryable = error_class in _RETRYABLE_CLASSES
    result = {
        "class": error_class,
        "retryable": retryable,
        "retry_after_seconds": _retry_after_seconds(text),
        "resume_recommended": retryable,
        "source": PROVIDER_ERROR_SOURCE,
    }
    validate_provider_error(result)
    return result


def validate_provider_error(value: Any, *, allow_none: bool = False) -> None:
    if value is None and allow_none:
        return
    if not isinstance(value, dict) or set(value) != {
        "class", "retryable", "retry_after_seconds", "resume_recommended", "source",
    }:
        raise ProviderFailureError("provider error fields are invalid")
    error_class = value.get("class")
    if error_class not in PROVIDER_ERROR_CLASSES:
        raise ProviderFailureError("provider error class is invalid")
    if type(value.get("retryable")) is not bool or type(value.get("resume_recommended")) is not bool:
        raise ProviderFailureError("provider error guidance flags are invalid")
    retry_after = value.get("retry_after_seconds")
    if retry_after is not None and (
        not isinstance(retry_after, int)
        or isinstance(retry_after, bool)
        or not 1 <= retry_after <= MAX_RETRY_AFTER_SECONDS
    ):
        raise ProviderFailureError("provider error retry-after value is invalid")
    expected_retryable = error_class in _RETRYABLE_CLASSES
    if value["retryable"] != expected_retryable or value["resume_recommended"] != expected_retryable:
        raise ProviderFailureError("provider error guidance is inconsistent with its class")
    if value.get("source") != PROVIDER_ERROR_SOURCE:
        raise ProviderFailureError("provider error source is invalid")
