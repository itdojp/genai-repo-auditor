#!/usr/bin/env python3
"""Validate the repository-local single-maintainer release control profile."""

from __future__ import annotations

import argparse
import json
from typing import Any


REQUIRED_REVIEWER = "ootakazuhiko"
REQUIRED_DEPLOYMENT_PATTERN = "v*"
REQUIRED_TAG_REF_PATTERN = "refs/tags/v*"
REQUIRED_TAG_RULES = {"update", "deletion", "non_fast_forward"}


class ReleaseControlError(ValueError):
    """Raised when external release controls do not satisfy repository policy."""


def _require_dict(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ReleaseControlError(f"{label} must be a JSON object")
    return value


def _require_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ReleaseControlError(f"{label} must be a JSON array")
    return value


def _load_json_argument(value: str, label: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise ReleaseControlError(f"{label} is not valid JSON: {exc.msg}") from exc


def _deployment_policies(payload: Any) -> list[dict[str, Any]]:
    pages = payload if isinstance(payload, list) else [payload]
    policies: list[dict[str, Any]] = []
    total_count = 0
    for index, page_value in enumerate(pages):
        page = _require_dict(page_value, f"deployment policy page {index}")
        page_policies = _require_list(
            page.get("branch_policies"), f"deployment policy page {index}.branch_policies"
        )
        policies.extend(
            _require_dict(policy, "deployment policy") for policy in page_policies
        )
        count = page.get("total_count")
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise ReleaseControlError(
                "deployment policy total_count must be a non-negative integer"
            )
        total_count = max(total_count, count)
    if total_count != len(policies):
        raise ReleaseControlError("deployment policy response is incomplete or inconsistent")
    return policies


def validate_environment(environment_payload: Any, deployment_policy_payload: Any) -> bool:
    """Validate reviewer, timer, and deployment-source controls.

    Returns true when a human UI check is required to prove that the sole
    deployment policy is a tag policy because the API omitted its ``type``.
    """

    environment = _require_dict(environment_payload, "environment")
    if environment.get("name") != "release":
        raise ReleaseControlError("environment name must be release")

    branch_policy = _require_dict(
        environment.get("deployment_branch_policy"), "environment.deployment_branch_policy"
    )
    if branch_policy.get("protected_branches") is not False:
        raise ReleaseControlError("protected_branches must be false")
    if branch_policy.get("custom_branch_policies") is not True:
        raise ReleaseControlError("custom_branch_policies must be true")

    protection_rules = _require_list(
        environment.get("protection_rules"), "environment.protection_rules"
    )
    reviewer_rules = [
        _require_dict(rule, "protection rule")
        for rule in protection_rules
        if isinstance(rule, dict) and rule.get("type") == "required_reviewers"
    ]
    if len(reviewer_rules) != 1:
        raise ReleaseControlError("exactly one required_reviewers rule is required")
    reviewer_rule = reviewer_rules[0]
    if reviewer_rule.get("prevent_self_review") is not False:
        raise ReleaseControlError("prevent_self_review must be false")
    reviewers = _require_list(reviewer_rule.get("reviewers"), "required reviewers")
    if len(reviewers) != 1:
        raise ReleaseControlError("exactly one required reviewer is required")
    reviewer = _require_dict(reviewers[0], "required reviewer")
    reviewer_identity = _require_dict(
        reviewer.get("reviewer"), "required reviewer identity"
    )
    if (
        reviewer.get("type") != "User"
        or reviewer_identity.get("login") != REQUIRED_REVIEWER
    ):
        raise ReleaseControlError(f"required reviewer must be user {REQUIRED_REVIEWER}")

    wait_rules = [
        _require_dict(rule, "protection rule")
        for rule in protection_rules
        if isinstance(rule, dict) and rule.get("type") == "wait_timer"
    ]
    if len(wait_rules) != 1:
        raise ReleaseControlError("exactly one wait_timer rule is required")
    wait_timer = wait_rules[0].get("wait_timer")
    if (
        not isinstance(wait_timer, int)
        or isinstance(wait_timer, bool)
        or wait_timer < 30
    ):
        raise ReleaseControlError("wait_timer must be an integer of at least 30 minutes")

    policies = _deployment_policies(deployment_policy_payload)
    if len(policies) != 1 or policies[0].get("name") != REQUIRED_DEPLOYMENT_PATTERN:
        raise ReleaseControlError("the only deployment policy must be v*")
    policy_type = policies[0].get("type")
    if policy_type not in (None, "tag"):
        raise ReleaseControlError("the v* deployment policy must target tags")
    return policy_type is None


def validate_immutable_releases(payload: Any) -> None:
    immutable = _require_dict(payload, "immutable releases")
    if immutable.get("enabled") is not True:
        raise ReleaseControlError("immutable releases must be enabled")


def validate_tag_rulesets(payload: Any) -> None:
    rulesets = _require_list(payload, "rulesets")
    matching_rulesets = []
    for ruleset_value in rulesets:
        ruleset = _require_dict(ruleset_value, "ruleset")
        if ruleset.get("target") != "tag" or ruleset.get("enforcement") != "active":
            continue
        conditions = _require_dict(ruleset.get("conditions"), "ruleset.conditions")
        ref_name = _require_dict(conditions.get("ref_name"), "ruleset.conditions.ref_name")
        if (
            ref_name.get("include") != [REQUIRED_TAG_REF_PATTERN]
            or ref_name.get("exclude") != []
        ):
            continue
        if "bypass_actors" not in ruleset or ruleset.get("bypass_actors") not in (
            None,
            [],
        ):
            raise ReleaseControlError("the v* tag ruleset must not have bypass actors")
        rules = _require_list(ruleset.get("rules"), "ruleset.rules")
        rule_types = {
            _require_dict(rule, "ruleset rule").get("type") for rule in rules
        }
        if "creation" in rule_types:
            raise ReleaseControlError("the v* tag ruleset must allow initial tag creation")
        if not REQUIRED_TAG_RULES.issubset(rule_types):
            raise ReleaseControlError(
                "the v* tag ruleset must restrict updates/deletions and block force pushes"
            )
        matching_rulesets.append(ruleset)
    if not matching_rulesets:
        raise ReleaseControlError("no active v* tag protection ruleset satisfies policy")


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate the single-maintainer GitHub release control profile."
    )
    parser.add_argument("--environment-json", required=True)
    parser.add_argument("--deployment-policies-json", required=True)
    parser.add_argument("--immutable-releases-json", required=True)
    parser.add_argument("--rulesets-json", required=True)
    return parser


def main() -> int:
    args = create_parser().parse_args()
    try:
        deployment_type_ui_check = validate_environment(
            _load_json_argument(args.environment_json, "environment JSON"),
            _load_json_argument(args.deployment_policies_json, "deployment policies JSON"),
        )
        validate_immutable_releases(
            _load_json_argument(args.immutable_releases_json, "immutable releases JSON")
        )
        validate_tag_rulesets(_load_json_argument(args.rulesets_json, "rulesets JSON"))
    except ReleaseControlError as exc:
        raise SystemExit(f"release control validation failed: {exc}") from exc

    manual_checks = ["administrator bypass disabled"]
    if deployment_type_ui_check:
        manual_checks.append("v* deployment policy type is tag")
    print(
        json.dumps(
            {
                "manual_checks_required": manual_checks,
                "status": "validated",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
