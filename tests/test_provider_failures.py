from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "lib"))

from provider_failures import (  # noqa: E402
    MAX_RETRY_AFTER_SECONDS,
    ProviderFailureError,
    classify_provider_failure,
    mark_provider_failure_recovered,
    record_provider_failure,
    validate_provider_error,
    validate_provider_failure_history,
)


class ProviderFailureTests(unittest.TestCase):
    def test_known_classes_are_provider_neutral_and_bounded(self) -> None:
        fixtures = {
            "rate_limit": "Provider API rate limit reached; retry after 30 seconds.",
            "usage_limit": "Usage limit reached; try again in 30 minutes.",
            "authentication": "Provider API authentication failed: invalid API key.",
            "authorization": "Provider API returned HTTP status 403 forbidden.",
            "service_unavailable": "Provider service temporarily unavailable (HTTP status 503).",
            "timeout": "Provider request timed out because its deadline exceeded.",
            "invalid_request": "Provider API rejected an invalid request with HTTP status 400.",
            "model_unavailable": "Selected model is at capacity; try again in 2 hours.",
            "response_contract": "Provider response did not match the required schema.",
            "unknown_provider_error": "Provider API error code PX-17.",
        }
        for expected, raw in fixtures.items():
            with self.subTest(expected=expected):
                result = classify_provider_failure(raw)
                self.assertIsNotNone(result)
                self.assertEqual(expected, result["class"])
                self.assertEqual("sanitized_stderr_classifier", result["source"])
                self.assertNotIn(raw, str(result))
                validate_provider_error(result)
        self.assertEqual(30, classify_provider_failure(fixtures["rate_limit"])["retry_after_seconds"])
        self.assertEqual(1800, classify_provider_failure(fixtures["usage_limit"])["retry_after_seconds"])
        self.assertEqual(7200, classify_provider_failure(fixtures["model_unavailable"])["retry_after_seconds"])
        self.assertEqual(
            "model_unavailable",
            classify_provider_failure(
                "Model gpt-example is not supported when using Codex with this account."
            )["class"],
        )

    def test_unknown_text_falls_back_without_copying_text(self) -> None:
        for raw in (
            "stage exited after a local validation failure",
            "permission denied opening reports/targets.json",
            "bad request while validating a local fixture",
            "deadline exceeded while waiting for subprocess completion",
            "HTTP status 400 from a local preview server",
            "service temporarily unavailable on a local socket",
        ):
            with self.subTest(raw=raw):
                self.assertIsNone(classify_provider_failure(raw))
        self.assertIsNone(classify_provider_failure(""))
        self.assertIsNone(classify_provider_failure(None))

    def test_retry_after_malformed_negative_and_excessive_values_are_omitted(self) -> None:
        for raw in (
            "Provider API rate limit; retry after -1 seconds.",
            "Provider API rate limit; retry after never seconds.",
            f"Provider API rate limit; retry after {MAX_RETRY_AFTER_SECONDS + 1} seconds.",
            "Provider API rate limit; retry after 25 days.",
        ):
            with self.subTest(raw=raw):
                result = classify_provider_failure(raw)
                self.assertEqual("rate_limit", result["class"])
                self.assertIsNone(result["retry_after_seconds"])

    def test_validator_rejects_open_inconsistent_and_out_of_range_metadata(self) -> None:
        valid = classify_provider_failure("Provider API rate limit; retry after 10 seconds.")
        mutations = [dict(valid, retry_after_seconds=value) for value in (-1, 0, MAX_RETRY_AFTER_SECONDS + 1, True, "10")]
        mutations.extend((
            dict(valid, **{"class": "not_supported"}),
            dict(valid, retryable=False),
            dict(valid, resume_recommended=False),
            dict(valid, source="raw_stderr"),
            {**valid, "message": "raw provider body"},
        ))
        for candidate in mutations:
            with self.subTest(candidate=candidate), self.assertRaises(ProviderFailureError):
                validate_provider_error(candidate)

    def test_provider_failure_history_is_bounded_and_records_recovery(self) -> None:
        rate = classify_provider_failure("Provider API rate limit; retry after 10 seconds.")
        usage = classify_provider_failure("Usage limit reached; try again in 30 minutes.")
        history = record_provider_failure(None, rate)
        history = record_provider_failure(history, usage)

        self.assertEqual(2, history["count"])
        self.assertEqual(2, history["retryable_count"])
        self.assertEqual({"rate_limit": 1, "usage_limit": 1}, history["by_class"])
        self.assertEqual(usage, history["last_error"])
        self.assertFalse(history["recovered"])
        recovered = mark_provider_failure_recovered(history, recovered=True)
        self.assertTrue(recovered["recovered"])
        validate_provider_failure_history(recovered)

        invalid = {**history, "count": 3}
        with self.assertRaises(ProviderFailureError):
            validate_provider_failure_history(invalid)


if __name__ == "__main__":
    unittest.main()
