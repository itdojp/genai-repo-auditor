from __future__ import annotations

import contextlib
import importlib.machinery
import importlib.util
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Iterable, Optional


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "tests" / "fixtures"
sys.path.insert(0, str(REPO_ROOT / "lib"))

from publication.github import GhCliClient, create_default_labels, ensure_custom_labels, verify_ledger_against_github  # noqa: E402
from publication.ledger import record_duplicate_decision, write_issue_ledger_snapshot  # noqa: E402
from publication.planning import build_publication_plan  # noqa: E402
from publication.plan_store import default_plan_path, load_plan, plan_hash, write_plan  # noqa: E402


def load_gra_issues_module() -> object:
    loader = importlib.machinery.SourceFileLoader("gra_issues_under_test", str(REPO_ROOT / "bin" / "gra-issues"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    if spec is None:
        raise RuntimeError("could not load gra-issues module spec")
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class RecordingGitHubClient:
    def __init__(self, existing: Optional[dict[str, str]] = None) -> None:
        self.existing = existing or {}
        self.repo_visibility_calls: list[str] = []
        self.issue_exists_calls: list[tuple[str, str]] = []
        self.label_calls: list[tuple[str, str, str, str]] = []
        self.create_issue_calls: list[dict[str, object]] = []

    def repo_visibility(self, repo: str) -> str:
        self.repo_visibility_calls.append(repo)
        return "PRIVATE"

    def issue_exists(self, repo: str, fingerprint: str) -> Optional[str]:
        self.issue_exists_calls.append((repo, fingerprint))
        return self.existing.get(fingerprint)

    def ensure_label(self, repo: str, name: str, color: str = "ededed", desc: str = "GenAI Repo Auditor label") -> None:
        self.label_calls.append((repo, name, color, desc))

    def create_issue(
        self,
        repo: str,
        *,
        title: str,
        body: str,
        labels: Iterable[str],
        assignee: Optional[str] = None,
        body_tmp_dir: Optional[Path] = None,
    ) -> str:
        self.create_issue_calls.append(
            {
                "repo": repo,
                "title": title,
                "body": body,
                "labels": list(labels),
                "assignee": assignee,
                "body_tmp_dir": str(body_tmp_dir) if body_tmp_dir else None,
            }
        )
        return "https://github.example.invalid/owner/repo/issues/1"


class CapturingGhCliClient(GhCliClient):
    def __init__(self) -> None:
        self.commands: list[tuple[list[str], bool, bool]] = []
        self.body_files_seen: list[str] = []
        self.body_contents_seen: list[str] = []

    def run(
        self,
        cmd: list[str],
        *,
        check: bool = True,
        capture: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        self.commands.append((list(cmd), check, capture))
        stdout = ""
        if cmd[:3] == ["gh", "issue", "create"]:
            body_path = Path(cmd[cmd.index("--body-file") + 1])
            self.body_files_seen.append(str(body_path))
            self.body_contents_seen.append(body_path.read_text(encoding="utf-8"))
            stdout = "https://github.example.invalid/owner/repo/issues/44\n"
        return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")


class PublicationStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_parent = REPO_ROOT / ".test-tmp"
        self.tmp_parent.mkdir(exist_ok=True)
        self.run_dir = Path(tempfile.mkdtemp(prefix=f"{self._testMethodName}-", dir=self.tmp_parent))
        (self.run_dir / "reports").mkdir(parents=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.run_dir, ignore_errors=True)
        with contextlib.suppress(OSError):
            self.tmp_parent.rmdir()

    def finding(self, **overrides: object) -> dict[str, object]:
        data: dict[str, object] = {
            "id": "SEC-001",
            "title": "Publication fixture",
            "issue_title": "[Security][High] Publication fixture",
            "severity": "High",
            "confidence": "High",
            "status": "Confirmed",
            "category": "Access Control",
            "issue_recommended": True,
            "fingerprint": "fp-sec-001",
            "affected_locations": [{"file": "src/app.py", "line": 10}],
            "entry_point": "POST /admin",
            "trust_boundary": "anonymous-to-admin",
            "call_path": "router -> handler",
            "root_cause": "Missing authorization check.",
            "evidence": "Safe summarized evidence.",
            "impact": "Unauthorized state change.",
            "minimal_remediation": "Authorize the handler.",
            "regression_test_idea": "Unauthenticated request is rejected.",
        }
        data.update(overrides)
        return data

    def test_plan_store_hashes_and_validates_publication_plans(self) -> None:
        plan_path = default_plan_path(self.run_dir)
        plan = {
            "schema_version": "1",
            "run_id": "run-1",
            "repo": "owner/repo",
            "commit": "abc123",
            "created_at": "2026-07-10T00:00:00Z",
            "visibility": "PRIVATE",
            "selected_findings": [],
        }

        write_plan(plan_path, plan)
        self.assertEqual(plan, load_plan(plan_path))
        self.assertEqual(64, len(plan_hash(plan_path)))

        plan_path.write_text(json.dumps({"selected_findings": ["not-an-object"]}) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "selected_findings\\[0\\] must be an object"):
            load_plan(plan_path)

        plan_path.write_text("[]\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "must be a JSON object"):
            load_plan(plan_path)

    def test_issue_ledger_snapshot_and_duplicate_decision_persistence_are_extracted(self) -> None:
        high = self.finding()
        low = self.finding(
            id="SEC-002",
            fingerprint="fp-sec-002",
            severity="Low",
            issue_title="[Security][Low] Low severity fixture",
        )
        plan, bodies = build_publication_plan(
            repo="owner/repo",
            run_id="run-1",
            commit="abc123",
            visibility="PRIVATE",
            findings=[high],
            run_dir=self.run_dir,
            generated_at="2026-07-10T00:00:00Z",
            advanced_artifacts={},
            novelty_entries={},
        )
        plan_path = default_plan_path(self.run_dir)
        write_plan(plan_path, plan)
        plan_sha256 = plan_hash(plan_path)

        ledger = write_issue_ledger_snapshot(
            run_dir=self.run_dir,
            repo="owner/repo",
            run_id="run-1",
            commit="abc123",
            findings=[high, low],
            selected_entries=plan["selected_findings"],
            selected_bodies=bodies,
            min_severity="High",
            statuses={"Confirmed", "Probable"},
            novelty_entries={},
            plan_path=plan_path,
            plan_sha256=plan_sha256,
            plan_written=True,
            publication_plan_status="written",
        )
        entries = {entry["finding_id"]: entry for entry in ledger["findings"]}
        self.assertEqual("pending", entries["SEC-001"]["publication_status"])
        self.assertEqual(plan_sha256, entries["SEC-001"]["plan_sha256"])
        self.assertEqual("not-selected", entries["SEC-002"]["publication_status"])
        self.assertEqual("severity below High", entries["SEC-002"]["selection_reason"])

        decision_path, decision = record_duplicate_decision(
            run_dir=self.run_dir,
            run_id="run-1",
            repo="owner/repo",
            commit="abc123",
            finding=high,
            fingerprint="fp-sec-001",
            exact_match_url="https://github.example.invalid/owner/repo/issues/9",
            exact_match_source="unit-test",
        )
        self.assertEqual("exact-duplicate", decision)
        self.assertEqual("reports/duplicate-decisions/SEC-001.json", decision_path)
        decision_data = json.loads((self.run_dir / decision_path).read_text(encoding="utf-8"))
        self.assertEqual(9, decision_data["candidate_issue_numbers"][0])
        self.assertNotIn("Safe summarized evidence.", json.dumps(decision_data, ensure_ascii=False))

    def test_github_client_boundary_supports_read_only_verification_without_mutation(self) -> None:
        ledger = {
            "findings": [
                {
                    "finding_id": "SEC-001",
                    "fingerprint": "fp-sec-001",
                    "publication_status": "published",
                    "url": "https://github.example.invalid/owner/repo/issues/1",
                },
                {
                    "finding_id": "SEC-002",
                    "fingerprint": "fp-sec-002",
                    "publication_status": "not-selected",
                    "url": None,
                },
            ]
        }
        client = RecordingGitHubClient({"fp-sec-001": "https://github.example.invalid/owner/repo/issues/1"})

        self.assertEqual([], verify_ledger_against_github("owner/repo", ledger, client))
        self.assertEqual([("owner/repo", "fp-sec-001")], client.issue_exists_calls)
        self.assertEqual([], client.repo_visibility_calls)
        self.assertEqual([], client.label_calls)
        self.assertEqual([], client.create_issue_calls)

        client = RecordingGitHubClient({"fp-sec-001": "https://github.example.invalid/owner/repo/issues/99"})
        self.assertEqual(
            [
                "SEC-001: ledger url https://github.example.invalid/owner/repo/issues/1 "
                "differs from GitHub search result https://github.example.invalid/owner/repo/issues/99"
            ],
            verify_ledger_against_github("owner/repo", ledger, client),
        )

    def test_label_helpers_call_only_label_mutations_on_injected_client(self) -> None:
        client = RecordingGitHubClient()
        defaults = {
            "security": ("d73a4a", "Security-related issue"),
            "genai-audit": ("5319e7", "Generated from local GenAI Repo Auditor"),
        }

        create_default_labels(client, "owner/repo", defaults)
        ensure_custom_labels(client, "owner/repo", ["security", "category-access-control"], defaults)

        self.assertEqual(
            [
                ("owner/repo", "security", "d73a4a", "Security-related issue"),
                ("owner/repo", "genai-audit", "5319e7", "Generated from local GenAI Repo Auditor"),
                ("owner/repo", "category-access-control", "ededed", "GenAI Repo Auditor label"),
            ],
            client.label_calls,
        )
        self.assertEqual([], client.issue_exists_calls)
        self.assertEqual([], client.create_issue_calls)

    def test_gra_issues_preview_modes_do_not_mutate_injected_github_client(self) -> None:
        module = load_gra_issues_module()
        dry_run_dir = self.run_dir / "dry-run-fixture"
        shutil.copytree(FIXTURES / "minimal-run", dry_run_dir)
        dry_run_client = RecordingGitHubClient()

        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            dry_run_status = module.main(
                [
                    "--run",
                    str(dry_run_dir),
                    "--dry-run",
                    "--min-severity",
                    "Low",
                    "--statuses",
                    "Confirmed",
                ],
                github=dry_run_client,
            )

        self.assertEqual(0, dry_run_status)
        self.assertEqual([], dry_run_client.repo_visibility_calls)
        self.assertEqual([], dry_run_client.issue_exists_calls)
        self.assertEqual([], dry_run_client.label_calls)
        self.assertEqual([], dry_run_client.create_issue_calls)

        plan_run_dir = self.run_dir / "apply-plan-preview-fixture"
        shutil.copytree(FIXTURES / "minimal-run", plan_run_dir)
        plan_client = RecordingGitHubClient()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            plan_status = module.main(
                [
                    "--run",
                    str(plan_run_dir),
                    "--plan",
                    "--min-severity",
                    "Low",
                    "--statuses",
                    "Confirmed",
                ],
                github=plan_client,
            )
        self.assertEqual(0, plan_status)
        self.assertEqual([], plan_client.repo_visibility_calls)
        self.assertEqual([], plan_client.issue_exists_calls)
        self.assertEqual([], plan_client.label_calls)
        self.assertEqual([], plan_client.create_issue_calls)

        preview_client = RecordingGitHubClient()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            preview_status = module.main(
                [
                    "--run",
                    str(plan_run_dir),
                    "--apply-plan",
                    str(default_plan_path(plan_run_dir)),
                    "--dry-run",
                ],
                github=preview_client,
            )

        self.assertEqual(0, preview_status)
        self.assertEqual([], preview_client.repo_visibility_calls)
        self.assertEqual([], preview_client.issue_exists_calls)
        self.assertEqual([], preview_client.label_calls)
        self.assertEqual([], preview_client.create_issue_calls)

    def test_gh_cli_client_mutations_use_runner_and_cleanup_temp_issue_body(self) -> None:
        client = CapturingGhCliClient()

        with self.assertRaisesRegex(ValueError, "body_tmp_dir is required"):
            client.create_issue(
                "owner/repo",
                title="[Security][High] Publication fixture",
                body="Issue body text for GitHub CLI boundary test.",
                labels=["security"],
            )

        client.ensure_label("owner/repo", "security", "d73a4a", "Security-related issue")
        issue_url = client.create_issue(
            "owner/repo",
            title="[Security][High] Publication fixture",
            body="Issue body text for GitHub CLI boundary test.",
            labels=["security", "genai-audit"],
            assignee="@me",
            body_tmp_dir=self.run_dir / "reports" / ".issue-body-tmp",
        )

        self.assertEqual("https://github.example.invalid/owner/repo/issues/44", issue_url)
        label_command, label_check, label_capture = client.commands[0]
        self.assertEqual(["gh", "label", "create", "security"], label_command[:4])
        self.assertFalse(label_check)
        self.assertFalse(label_capture)

        create_command, create_check, create_capture = client.commands[1]
        self.assertEqual(["gh", "issue", "create", "-R", "owner/repo"], create_command[:5])
        self.assertIn("--body-file", create_command)
        self.assertIn("--label", create_command)
        self.assertIn("--assignee", create_command)
        self.assertTrue(create_check)
        self.assertTrue(create_capture)
        self.assertEqual(["Issue body text for GitHub CLI boundary test."], client.body_contents_seen)
        self.assertEqual(1, len(client.body_files_seen))
        self.assertFalse(Path(client.body_files_seen[0]).exists())
        self.assertFalse((self.run_dir / "reports" / ".issue-body-tmp").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
