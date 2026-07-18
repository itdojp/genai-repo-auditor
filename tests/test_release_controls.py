from __future__ import annotations

import copy
import unittest

from scripts import validate_release_controls as controls


def valid_environment() -> dict:
    return {
        "name": "release",
        "deployment_branch_policy": {
            "protected_branches": False,
            "custom_branch_policies": True,
        },
        "protection_rules": [
            {
                "type": "required_reviewers",
                "prevent_self_review": False,
                "reviewers": [
                    {
                        "type": "User",
                        "reviewer": {"login": "ootakazuhiko"},
                    }
                ],
            },
            {"type": "wait_timer", "wait_timer": 30},
        ],
    }


def valid_deployment_policies(*, include_type: bool = True) -> dict:
    policy = {"id": 1, "name": "v*"}
    if include_type:
        policy["type"] = "tag"
    return {"total_count": 1, "branch_policies": [policy]}


def valid_rulesets() -> list[dict]:
    return [
        {
            "target": "tag",
            "enforcement": "active",
            "bypass_actors": [],
            "conditions": {
                "ref_name": {"include": ["refs/tags/v*"], "exclude": []}
            },
            "rules": [
                {"type": "update"},
                {"type": "deletion"},
                {"type": "non_fast_forward"},
            ],
        }
    ]


class ReleaseControlTests(unittest.TestCase):
    def test_valid_single_maintainer_profile_is_accepted(self) -> None:
        self.assertFalse(
            controls.validate_environment(valid_environment(), valid_deployment_policies())
        )
        controls.validate_immutable_releases({"enabled": True})
        controls.validate_tag_rulesets(valid_rulesets())

    def test_missing_policy_type_requires_fail_closed_ui_confirmation(self) -> None:
        self.assertTrue(
            controls.validate_environment(
                valid_environment(), valid_deployment_policies(include_type=False)
            )
        )

    def test_environment_rejects_legacy_or_weak_profiles(self) -> None:
        mutations = [
            (
                "self review prevention",
                lambda value: value["protection_rules"][0].update(
                    prevent_self_review=True
                ),
            ),
            (
                "wrong reviewer",
                lambda value: value["protection_rules"][0]["reviewers"][0][
                    "reviewer"
                ].update(login="other"),
            ),
            (
                "additional reviewer",
                lambda value: value["protection_rules"][0]["reviewers"].append(
                    {"type": "User", "reviewer": {"login": "other"}}
                ),
            ),
            (
                "short wait",
                lambda value: value["protection_rules"][1].update(wait_timer=29),
            ),
            ("missing wait", lambda value: value["protection_rules"].pop()),
            (
                "protected branches",
                lambda value: value["deployment_branch_policy"].update(
                    protected_branches=True, custom_branch_policies=False
                ),
            ),
        ]
        for label, mutate in mutations:
            with self.subTest(label=label):
                environment = valid_environment()
                mutate(environment)
                with self.assertRaises(controls.ReleaseControlError):
                    controls.validate_environment(environment, valid_deployment_policies())

    def test_environment_rejects_wrong_or_incomplete_deployment_policy(self) -> None:
        weak_policies = [
            {"total_count": 0, "branch_policies": []},
            {"total_count": 1, "branch_policies": [{"name": "main", "type": "branch"}]},
            {"total_count": 1, "branch_policies": [{"name": "v*", "type": "branch"}]},
            {
                "total_count": 2,
                "branch_policies": [
                    {"name": "v*", "type": "tag"},
                    {"name": "main", "type": "branch"},
                ],
            },
            {"total_count": 2, "branch_policies": [{"name": "v*", "type": "tag"}]},
        ]
        for policy in weak_policies:
            with self.subTest(policy=policy):
                with self.assertRaises(controls.ReleaseControlError):
                    controls.validate_environment(valid_environment(), policy)

    def test_immutable_releases_must_be_explicitly_enabled(self) -> None:
        for payload in ({"enabled": False}, {}, None):
            with self.subTest(payload=payload):
                with self.assertRaises(controls.ReleaseControlError):
                    controls.validate_immutable_releases(payload)

    def test_tag_ruleset_rejects_fail_open_variants(self) -> None:
        mutations = [
            ("not active", lambda value: value[0].update(enforcement="disabled")),
            ("wrong target", lambda value: value[0].update(target="branch")),
            (
                "bypass actor",
                lambda value: value[0].update(
                    bypass_actors=[{"actor_type": "RepositoryRole"}]
                ),
            ),
            (
                "wrong include",
                lambda value: value[0]["conditions"]["ref_name"].update(
                    include=["refs/tags/v0.5.0"]
                ),
            ),
            (
                "exclude",
                lambda value: value[0]["conditions"]["ref_name"].update(
                    exclude=["refs/tags/v0.5.0"]
                ),
            ),
            ("missing update", lambda value: value[0]["rules"].pop(0)),
            ("missing deletion", lambda value: value[0]["rules"].pop(1)),
            ("missing force protection", lambda value: value[0]["rules"].pop(2)),
            (
                "creation blocked",
                lambda value: value[0]["rules"].append({"type": "creation"}),
            ),
        ]
        for label, mutate in mutations:
            with self.subTest(label=label):
                rulesets = copy.deepcopy(valid_rulesets())
                mutate(rulesets)
                with self.assertRaises(controls.ReleaseControlError):
                    controls.validate_tag_rulesets(rulesets)

    def test_tag_ruleset_accepts_null_bypass_list_from_read_api(self) -> None:
        rulesets = valid_rulesets()
        rulesets[0]["bypass_actors"] = None
        controls.validate_tag_rulesets(rulesets)


if __name__ == "__main__":
    unittest.main(verbosity=2)
