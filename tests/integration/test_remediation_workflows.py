from __future__ import annotations

try:
    from .support import *  # noqa: F401,F403
except ImportError:
    from support import *  # noqa: F401,F403


class RemediationWorkflowTests(CliWorkflowTestCase):
    def test_gra_adversarial_validate_finding_exec_writes_validation_artifacts(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        env, codex_log = self.env_with_codex_log(
            GRA_MOCK_FIXTURE_DIR=str(FIXTURES / "adversarial-validation-output")
        )
        cp = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-adversarial-validate",
                "--run",
                run_dir,
                "--finding",
                "SEC-001",
                "--model",
                "gpt-fixture",
                "--effort",
                "medium",
            ],
            env=env,
            check=True,
        )
        self.assertIn("Running Codex adversarial validation for SEC-001", cp.stdout)
        self.assertIn("Codex status: 0", cp.stdout)

        subjects = json.loads(
            (run_dir / "reports" / "adversarial-validation" / "sec-001.subjects.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual("SEC-001", subjects["selection"])
        self.assertEqual(["SEC-001"], [item["subject_id"] for item in subjects["subjects"]])
        self.assertEqual(["finding"], [item["subject_type"] for item in subjects["subjects"]])

        prompt = run_dir / "prompts" / "exec" / "adversarial-validate-sec-001.prompt.md"
        prompt_text = prompt.read_text(encoding="utf-8")
        self.assertIn("You must not create new findings.", prompt_text)
        self.assertIn("disprove, downgrade, confirm, or mark needs-human-review", prompt_text)
        self.assertIn("Check:\n- attacker control", prompt_text)
        self.assertIn("- config assumptions", prompt_text)
        self.assertIn("- test fixture vs production behavior", prompt_text)
        self.assertIn("- whether impact is overstated", prompt_text)
        self.assertIn("reports/adversarial-validation/sec-001.subjects.json", prompt_text)
        self.assertNotIn("{{", prompt_text)

        validation = json.loads((run_dir / "reports" / "validation.json").read_text(encoding="utf-8"))
        self.assertEqual("SEC-001", validation["validations"][0]["subject_id"])
        self.assertEqual("downgrade", validation["validations"][0]["decision"])
        self.assertEqual("Medium", validation["validations"][0]["recommended_severity"])
        self.assertEqual(1, len(json.loads((run_dir / "reports" / "findings.json").read_text(encoding="utf-8"))["findings"]))
        validation_md = (run_dir / "reports" / "VALIDATION.md").read_text(encoding="utf-8")
        self.assertIn("Adversarial Validation", validation_md)
        self.assertIn("VAL-001", validation_md)

        final_path = run_dir / "codex-adversarial-validate-sec-001-final.md"
        events_path = run_dir / "codex-adversarial-validate-sec-001-events.jsonl"
        stderr_path = run_dir / "codex-adversarial-validate-sec-001-stderr.txt"
        self.assertEqual(final_path.read_text(encoding="utf-8"), "mock codex mode=success\n")
        self.assertIn('"status": "ok"', events_path.read_text(encoding="utf-8"))
        self.assertTrue(stderr_path.exists())

        calls = self.read_codex_calls(codex_log)
        self.assertEqual(len(calls), 1, calls)
        self.assertIn(str(final_path), calls[0])
        self.assertIn('model_reasoning_effort="medium"', calls[0])
        events = self.read_command_events(run_dir)
        self.assertEqual(1, len(events), events)
        self.assert_public_command_event(
            events[0],
            command="gra-adversarial-validate",
            phase="adversarial-validate",
            subject_id="SEC-001",
        )
        self.assertIn("reports/adversarial-validation/sec-001.subjects.json", events[0]["output_artifact_refs"])
        self.assertIn("reports/validation.json", events[0]["output_artifact_refs"])

        cp_validate = self.run_cmd([REPO_ROOT / "bin" / "gra-validate-report", "--run", run_dir], check=True)
        self.assertIn("Adversarial validations: validated", cp_validate.stdout)

    def test_gra_adversarial_validate_votes_split_human_review_and_owner_route(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        repo = run_dir / "repo"
        (repo / ".github").mkdir(parents=True)
        (repo / ".github" / "CODEOWNERS").write_text("/auth/ @team/appsec\n", encoding="utf-8")
        (repo / "CODEOWNERS").write_text("/auth/ @team/wrong-root\n", encoding="utf-8")
        (repo / "auth").mkdir()
        (repo / "auth" / "login.py").write_text("def login():\n    pass\n", encoding="utf-8")
        findings_path = run_dir / "reports" / "findings.json"
        findings = json.loads(findings_path.read_text(encoding="utf-8"))
        findings["findings"][0]["affected_locations"] = [{"file": "auth/login.py", "line": 1}]
        findings_path.write_text(json.dumps(findings, indent=2) + "\n", encoding="utf-8")

        vote1 = self.write_adversarial_vote_fixture(name="vote-confirm-1", decision="confirm", summary="Confirming vote.")
        vote2 = self.write_adversarial_vote_fixture(
            name="vote-invalidate",
            decision="invalidate",
            recommended_severity="Informational",
            recommended_confidence="Low",
            summary="Invalidating vote.",
        )
        vote3 = self.write_adversarial_vote_fixture(name="vote-confirm-2", decision="confirm", summary="Second confirming vote.")
        env, codex_log = self.env_with_codex_log(
            GRA_MOCK_FIXTURE_DIR_VOTE_001=str(vote1),
            GRA_MOCK_FIXTURE_DIR_VOTE_002=str(vote2),
            GRA_MOCK_FIXTURE_DIR_VOTE_003=str(vote3),
        )
        cp = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-adversarial-validate",
                "--run",
                run_dir,
                "--finding",
                "SEC-001",
                "--votes",
                "3",
                "--policy",
                "human-review-on-split",
                "--model",
                "gpt-fixture",
            ],
            env=env,
            check=True,
        )
        self.assertIn("with 3 independent votes", cp.stdout)
        calls = self.read_codex_calls(codex_log)
        self.assertEqual(3, len(calls), calls)
        self.assertTrue(any("vote-001-final.md" in arg for arg in calls[0]))
        self.assertTrue(any("vote-002-final.md" in arg for arg in calls[1]))
        self.assertTrue(any("vote-003-final.md" in arg for arg in calls[2]))

        validation = json.loads((run_dir / "reports" / "validation.json").read_text(encoding="utf-8"))
        self.assertEqual(3, validation["requested_votes"])
        self.assertEqual("human-review-on-split", validation["vote_policy"])
        item = validation["validations"][0]
        self.assertEqual("needs-human-review", item["decision"])
        self.assertEqual(3, item["vote_count"])
        self.assertEqual(["confirm", "invalidate", "confirm"], [vote["decision"] for vote in item["votes"]])
        self.assertEqual("auth", item["component"])
        self.assertEqual("@team/appsec", item["owner_hint"])
        self.assertEqual("CODEOWNERS", item["owner_source"])

        cp_validate = self.run_cmd([REPO_ROOT / "bin" / "gra-validate-report", "--run", run_dir], check=True)
        self.assertIn("Adversarial validations: validated", cp_validate.stdout)
        cp_plan = self.run_cmd([REPO_ROOT / "bin" / "gra-issues", "--run", run_dir, "--plan"], check=True)
        self.assertIn("owner_routing: component=auth, owner_hint=@team/appsec, owner_source=CODEOWNERS", cp_plan.stdout)
        plan = json.loads((run_dir / "reports" / "issue-publication-plan.json").read_text(encoding="utf-8"))
        owner_routing = plan["selected_findings"][0]["owner_routing"]
        self.assertEqual({"component": "auth", "owner_hint": "@team/appsec", "owner_source": "CODEOWNERS"}, owner_routing)

    def test_gra_adversarial_validate_votes_majority_confirm(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        vote1 = self.write_adversarial_vote_fixture(name="majority-confirm-1", decision="confirm")
        vote2 = self.write_adversarial_vote_fixture(name="majority-confirm-2", decision="confirm")
        vote3 = self.write_adversarial_vote_fixture(
            name="majority-confirm-dissent",
            decision="invalidate",
            recommended_severity="Informational",
            recommended_confidence="Low",
        )
        env, _codex_log = self.env_with_codex_log(
            GRA_MOCK_FIXTURE_DIR_VOTE_001=str(vote1),
            GRA_MOCK_FIXTURE_DIR_VOTE_002=str(vote2),
            GRA_MOCK_FIXTURE_DIR_VOTE_003=str(vote3),
        )
        self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-adversarial-validate",
                "--run",
                run_dir,
                "--finding",
                "SEC-001",
                "--votes",
                "3",
                "--policy",
                "recall-biased",
            ],
            env=env,
            check=True,
        )
        validation = json.loads((run_dir / "reports" / "validation.json").read_text(encoding="utf-8"))
        self.assertEqual("confirm", validation["validations"][0]["decision"])
        self.assertEqual(3, len(validation["validations"][0]["votes"]))

    def test_gra_adversarial_validate_votes_majority_invalidate(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        vote1 = self.write_adversarial_vote_fixture(
            name="majority-invalidate-1",
            decision="invalidate",
            recommended_severity="Informational",
            recommended_confidence="Low",
        )
        vote2 = self.write_adversarial_vote_fixture(
            name="majority-invalidate-2",
            decision="invalidate",
            recommended_severity="Informational",
            recommended_confidence="Low",
        )
        vote3 = self.write_adversarial_vote_fixture(name="majority-invalidate-dissent", decision="confirm")
        env, _codex_log = self.env_with_codex_log(
            GRA_MOCK_FIXTURE_DIR_VOTE_001=str(vote1),
            GRA_MOCK_FIXTURE_DIR_VOTE_002=str(vote2),
            GRA_MOCK_FIXTURE_DIR_VOTE_003=str(vote3),
        )
        self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-adversarial-validate",
                "--run",
                run_dir,
                "--finding",
                "SEC-001",
                "--votes",
                "3",
                "--policy",
                "precision-biased",
            ],
            env=env,
            check=True,
        )
        validation = json.loads((run_dir / "reports" / "validation.json").read_text(encoding="utf-8"))
        self.assertEqual("invalidate", validation["validations"][0]["decision"])
        self.assertEqual(3, len(validation["validations"][0]["votes"]))

    def test_gra_adversarial_validate_all_critical_high_selects_relevant_findings(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        findings_path = run_dir / "reports" / "findings.json"
        findings = json.loads(findings_path.read_text(encoding="utf-8"))
        base = findings["findings"][0]
        findings["findings"].extend(
            [
                {**base, "id": "SEC-002", "fingerprint": "fixture-fingerprint-0002", "severity": "Low", "status": "Confirmed"},
                {**base, "id": "SEC-003", "fingerprint": "fixture-fingerprint-0003", "severity": "High", "status": "Invalid"},
                {**base, "id": "SEC-004", "fingerprint": "fixture-fingerprint-0004", "severity": "Critical", "status": "Potential"},
            ]
        )
        findings_path.write_text(json.dumps(findings, indent=2) + "\n", encoding="utf-8")

        env, codex_log = self.env_with_codex_log()
        cp = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-adversarial-validate",
                "--run",
                run_dir,
                "--all-critical-high",
                "--mode",
                "goal",
            ],
            env=env,
            check=True,
        )
        self.assertIn("Prepared supervised /goal adversarial validation run.", cp.stdout)
        subjects = json.loads(
            (run_dir / "reports" / "adversarial-validation" / "critical-high.subjects.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(["SEC-001", "SEC-004"], [item["subject_id"] for item in subjects["subjects"]])
        prompt = run_dir / "prompts" / "goal" / "adversarial-validate-critical-high.goal.md"
        self.assertTrue(prompt.read_text(encoding="utf-8").startswith("/goal "))
        self.assertIn("You must not create new findings.", prompt.read_text(encoding="utf-8"))
        self.assertEqual(self.read_codex_calls(codex_log), [])
        events = self.read_command_events(run_dir)
        self.assertEqual(1, len(events), events)
        self.assert_public_command_event(events[0], command="gra-adversarial-validate", phase="goal", subject_id="critical-high")
        self.assertIn("reports/adversarial-validation/critical-high.subjects.json", events[0]["output_artifact_refs"])
        self.assertIn("prompts/goal/adversarial-validate-critical-high.goal.md", events[0]["output_artifact_refs"])

    def test_gra_adversarial_validate_all_critical_high_requires_findings_json(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        (run_dir / "reports" / "findings.json").unlink()
        env, codex_log = self.env_with_codex_log()
        cp = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-adversarial-validate",
                "--run",
                run_dir,
                "--all-critical-high",
            ],
            env=env,
        )
        self.assertEqual(cp.returncode, 2)
        self.assertIn("findings.json not found", cp.stderr)
        self.assertEqual(self.read_codex_calls(codex_log), [])

    def test_gra_adversarial_validate_chain_goal_uses_chains_json(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        chains = {
            "run_id": "fixture-run",
            "repo": "example/demo",
            "generated_at": "2026-05-26T00:00:00Z",
            "chains": [
                {
                    "id": "CHAIN-001",
                    "title": "Fixture chain",
                    "finding_ids": ["SEC-001"],
                }
            ],
        }
        (run_dir / "reports" / "chains.json").write_text(json.dumps(chains, indent=2) + "\n", encoding="utf-8")

        env, codex_log = self.env_with_codex_log()
        cp = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-adversarial-validate",
                "--run",
                run_dir,
                "--chain",
                "CHAIN-001",
                "--mode",
                "goal",
            ],
            env=env,
            check=True,
        )
        self.assertIn("Prepared supervised /goal adversarial validation run.", cp.stdout)
        subjects = json.loads(
            (run_dir / "reports" / "adversarial-validation" / "chain-001.subjects.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(["chain"], [item["subject_type"] for item in subjects["subjects"]])
        self.assertEqual(["CHAIN-001"], [item["subject_id"] for item in subjects["subjects"]])
        self.assertEqual(self.read_codex_calls(codex_log), [])
        events = self.read_command_events(run_dir)
        self.assertEqual(1, len(events), events)
        self.assert_public_command_event(events[0], command="gra-adversarial-validate", phase="goal", subject_id="CHAIN-001")
        self.assertIn("reports/adversarial-validation/chain-001.subjects.json", events[0]["output_artifact_refs"])

    def test_gra_proofs_finding_exec_writes_safe_local_proof_artifacts(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        env, codex_log = self.env_with_codex_log(GRA_MOCK_FIXTURE_DIR=str(FIXTURES / "proof-output"))
        cp = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-proofs",
                "--run",
                run_dir,
                "--finding",
                "SEC-001",
                "--model",
                "gpt-fixture",
                "--effort",
                "medium",
            ],
            env=env,
            check=True,
        )
        self.assertIn("Running Codex safe local proof generation for SEC-001", cp.stdout)
        self.assertIn("Codex status: 0", cp.stdout)

        subjects = json.loads((run_dir / "reports" / "proofs" / "sec-001.subjects.json").read_text(encoding="utf-8"))
        self.assertEqual(["SEC-001"], [item["finding_id"] for item in subjects["subjects"]])
        prompt = run_dir / "prompts" / "exec" / "safe-proof-sec-001.prompt.md"
        prompt_text = prompt.read_text(encoding="utf-8")
        self.assertIn("No working exploit scripts.", prompt_text)
        self.assertIn("No weaponized payloads", prompt_text)
        self.assertIn("No external network requests.", prompt_text)
        self.assertIn("Do not modify files under repo/.", prompt_text)
        self.assertIn("reports/proofs.json", prompt_text)
        self.assertIn("reports/proofs/sec-001.subjects.json", prompt_text)
        self.assertNotIn("{{", prompt_text)

        proofs = json.loads((run_dir / "reports" / "proofs.json").read_text(encoding="utf-8"))
        self.assertEqual("PROOF-001", proofs["proofs"][0]["id"])
        self.assertEqual("SEC-001", proofs["proofs"][0]["finding_id"])
        self.assertIs(proofs["proofs"][0]["safe_by_design"], True)
        self.assertEqual(["reports/proofs/SEC-001-test-plan.md"], proofs["proofs"][0]["files_created"])
        command_names = [command["argv"][0] for command in proofs["proofs"][0]["commands_run"]]
        self.assertEqual(["rg", "sed", "python3"], command_names)
        self.assertTrue(all(command["read_only"] is True for command in proofs["proofs"][0]["commands_run"]))
        self.assertTrue(all(command["writes"] == [] for command in proofs["proofs"][0]["commands_run"]))
        self.assertTrue(all(command["network"] is False for command in proofs["proofs"][0]["commands_run"]))
        self.assertTrue(all(command["requires_credentials"] is False for command in proofs["proofs"][0]["commands_run"]))
        proofs_md = (run_dir / "reports" / "PROOFS.md").read_text(encoding="utf-8")
        self.assertIn("Local/private by default", proofs_md)
        self.assertIn("Commands for PROOF-001:", proofs_md)
        self.assertIn("`rg --line-number SEC-001 repo/app.py`", proofs_md)
        self.assertTrue((run_dir / "reports" / "proofs" / "SEC-001-test-plan.md").exists())

        final_path = run_dir / "codex-safe-proof-sec-001-final.md"
        events_path = run_dir / "codex-safe-proof-sec-001-events.jsonl"
        stderr_path = run_dir / "codex-safe-proof-sec-001-stderr.txt"
        self.assertEqual(final_path.read_text(encoding="utf-8"), "mock codex mode=success\n")
        self.assertIn('"status": "ok"', events_path.read_text(encoding="utf-8"))
        self.assertTrue(stderr_path.exists())
        calls = self.read_codex_calls(codex_log)
        self.assertEqual(len(calls), 1, calls)
        self.assertIn(str(final_path), calls[0])
        self.assertIn('model_reasoning_effort="medium"', calls[0])
        events = self.read_command_events(run_dir)
        self.assertEqual(1, len(events), events)
        self.assert_public_command_event(events[0], command="gra-proofs", phase="proof", subject_id="SEC-001")
        self.assertIn("reports/proofs/sec-001.subjects.json", events[0]["output_artifact_refs"])
        self.assertIn("reports/proofs.json", events[0]["output_artifact_refs"])

        cp_validate = self.run_cmd([REPO_ROOT / "bin" / "gra-validate-report", "--run", run_dir], check=True)
        self.assertIn("Proofs: validated", cp_validate.stdout)

    def test_gra_remediate_finding_exec_writes_draft_candidate_artifacts(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        env, codex_log = self.env_with_codex_log(GRA_MOCK_FIXTURE_DIR=str(FIXTURES / "remediation-output"))
        cp = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-remediate",
                "--run",
                run_dir,
                "--finding",
                "SEC-001",
                "--model",
                "gpt-fixture",
                "--effort",
                "medium",
            ],
            env=env,
            check=True,
        )
        self.assertIn("Running Codex remediation candidate generation for SEC-001", cp.stdout)
        self.assertIn("Codex status: 0", cp.stdout)

        subjects = json.loads((run_dir / "reports" / "remediation" / "sec-001.subjects.json").read_text(encoding="utf-8"))
        self.assertEqual(["SEC-001"], [item["finding_id"] for item in subjects["subjects"]])
        subject = json.loads((run_dir / "reports" / "remediation" / "SEC-001" / "subject.json").read_text(encoding="utf-8"))
        self.assertEqual("PATCH-001", subject["candidate_id"])
        self.assertEqual("reports/remediation/SEC-001/patch.diff", subject["patch_file"])

        prompt = run_dir / "prompts" / "exec" / "remediate-sec-001.prompt.md"
        prompt_text = prompt.read_text(encoding="utf-8")
        self.assertIn("draft-only remediation candidate", prompt_text)
        self.assertIn("Do not apply any patch to repo/.", prompt_text)
        self.assertIn("Do not push, create branches, create pull requests, create GitHub Issues", prompt_text)
        self.assertIn("reports/remediation/remediation-candidates.json", prompt_text)
        self.assertIn("reports/remediation/sec-001.subjects.json", prompt_text)
        self.assertNotIn("{{", prompt_text)

        candidates = json.loads((run_dir / "reports" / "remediation" / "remediation-candidates.json").read_text(encoding="utf-8"))
        candidate = candidates["candidates"][0]
        self.assertEqual("PATCH-001", candidate["id"])
        self.assertEqual("SEC-001", candidate["finding_id"])
        self.assertEqual("draft", candidate["status"])
        self.assertIs(candidate["safe_by_design"], True)
        self.assertIs(candidate["requires_human_review"], True)
        self.assertEqual("reports/remediation/SEC-001/patch.diff", candidate["patch_file"])
        self.assertTrue((run_dir / "reports" / "remediation" / "SEC-001" / "patch.diff").exists())
        self.assertIn("Local/private by default", (run_dir / "reports" / "remediation" / "REMEDIATION_CANDIDATES.md").read_text(encoding="utf-8"))

        final_path = run_dir / "codex-remediate-sec-001-final.md"
        events_path = run_dir / "codex-remediate-sec-001-events.jsonl"
        stderr_path = run_dir / "codex-remediate-sec-001-stderr.txt"
        self.assertEqual(final_path.read_text(encoding="utf-8"), "mock codex mode=success\n")
        self.assertIn('"status": "ok"', events_path.read_text(encoding="utf-8"))
        self.assertTrue(stderr_path.exists())
        calls = self.read_codex_calls(codex_log)
        self.assertEqual(len(calls), 1, calls)
        self.assertIn(str(final_path), calls[0])
        self.assertIn('model_reasoning_effort="medium"', calls[0])
        self.assertIn('sandbox_workspace_write.network_access=false', calls[0])
        events = self.read_command_events(run_dir)
        self.assertEqual(1, len(events), events)
        self.assert_public_command_event(events[0], command="gra-remediate", phase="remediate", subject_id="SEC-001")
        self.assertIn("reports/remediation/sec-001.subjects.json", events[0]["output_artifact_refs"])
        self.assertIn("reports/remediation/remediation-candidates.json", events[0]["output_artifact_refs"])

        cp_validate = self.run_cmd([REPO_ROOT / "bin" / "gra-validate-report", "--run", run_dir], check=True)
        self.assertIn("Remediation candidates: validated", cp_validate.stdout)

        cp_dashboard = self.run_cmd([REPO_ROOT / "bin" / "gra-dashboard", "--run", run_dir], check=True)
        self.assertIn("dashboard.html", cp_dashboard.stdout)
        dashboard = (run_dir / "reports" / "dashboard.html").read_text(encoding="utf-8")
        self.assertIn("Remediation candidates", dashboard)
        self.assertIn("REMEDIATION_CANDIDATES.md", dashboard)
        self.assertIn("PATCH-001", dashboard)

        cp_plan = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-issues",
                "--run",
                run_dir,
                "--plan",
                "--min-severity",
                "Low",
                "--statuses",
                "Confirmed",
            ],
            check=True,
        )
        self.assertIn("remediation_candidate:", cp_plan.stdout)
        self.assertIn("exists=True", cp_plan.stdout)
        self.assertNotIn("diff --git", cp_plan.stdout)
        plan = json.loads((run_dir / "reports" / "issue-publication-plan.json").read_text(encoding="utf-8"))
        remediation = plan["selected_findings"][0]["remediation_candidate"]
        self.assertTrue(remediation["exists"])
        self.assertEqual(["PATCH-001"], [item["id"] for item in remediation["candidates"]])
        self.assertNotIn("diff --git", json.dumps(plan))

    def test_gra_remediate_goal_prepares_prompt_without_codex_exec(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        env, codex_log = self.env_with_codex_log()
        cp = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-remediate",
                "--run",
                run_dir,
                "--finding",
                "SEC-001",
                "--mode",
                "goal",
            ],
            env=env,
            check=True,
        )
        self.assertIn("Prepared supervised /goal remediation candidate run.", cp.stdout)
        prompt = run_dir / "prompts" / "goal" / "remediate-sec-001.goal.md"
        self.assertTrue(prompt.exists())
        self.assertTrue(prompt.read_text(encoding="utf-8").startswith("/goal "))
        self.assertIn("Do not apply any patch", prompt.read_text(encoding="utf-8"))
        self.assertTrue((run_dir / "reports" / "remediation" / "SEC-001" / "subject.json").exists())
        self.assertEqual(self.read_codex_calls(codex_log), [])
        self.assertFalse((run_dir / "codex-remediate-sec-001-final.md").exists())
        events = self.read_command_events(run_dir)
        self.assertEqual(1, len(events), events)
        self.assert_public_command_event(events[0], command="gra-remediate", phase="goal", subject_id="SEC-001")
        self.assertIn("reports/remediation/sec-001.subjects.json", events[0]["output_artifact_refs"])
        self.assertIn("prompts/goal/remediate-sec-001.goal.md", events[0]["output_artifact_refs"])

    def test_gra_remediate_all_critical_high_goal_selects_relevant_findings(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        findings_path = run_dir / "reports" / "findings.json"
        findings = json.loads(findings_path.read_text(encoding="utf-8"))
        base = findings["findings"][0]
        findings["findings"].extend(
            [
                {**base, "id": "SEC-002", "fingerprint": "fixture-fingerprint-0002", "severity": "Low", "status": "Confirmed"},
                {**base, "id": "SEC-003", "fingerprint": "fixture-fingerprint-0003", "severity": "High", "status": "Invalid"},
                {**base, "id": "SEC-004", "fingerprint": "fixture-fingerprint-0004", "severity": "Critical", "status": "Potential"},
            ]
        )
        findings_path.write_text(json.dumps(findings, indent=2) + "\n", encoding="utf-8")

        env, codex_log = self.env_with_codex_log()
        cp = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-remediate",
                "--run",
                run_dir,
                "--all-critical-high",
                "--mode",
                "goal",
            ],
            env=env,
            check=True,
        )

        self.assertIn("Prepared supervised /goal remediation candidate run.", cp.stdout)
        subjects = json.loads((run_dir / "reports" / "remediation" / "critical-high.subjects.json").read_text(encoding="utf-8"))
        self.assertEqual(["SEC-001", "SEC-004"], [item["finding_id"] for item in subjects["subjects"]])
        self.assertTrue((run_dir / "reports" / "remediation" / "SEC-004" / "subject.json").exists())
        prompt = run_dir / "prompts" / "goal" / "remediate-critical-high.goal.md"
        self.assertTrue(prompt.read_text(encoding="utf-8").startswith("/goal "))
        self.assertEqual(self.read_codex_calls(codex_log), [])

    def test_gra_remediate_validate_applies_patch_in_disposable_workspace(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        self.prepare_patch_validation_run(run_dir)
        original_app = (run_dir / "repo" / "app.py").read_text(encoding="utf-8")

        cp = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-remediate",
                "--run",
                run_dir,
                "--finding",
                "SEC-001",
                "--validate",
                "--sandbox-profile",
                "local-test",
                "--build-command",
                "python3 -m py_compile repo/app.py",
                "--test-command",
                "python3 -m py_compile repo/app.py",
            ],
            env=self.env_without_credentials(),
            check=True,
        )
        self.assertIn("Patch validation results:", cp.stdout)
        self.assertIn("final_status=validated", cp.stdout)

        validation_path = run_dir / "reports" / "remediation" / "SEC-001" / "patch-validation.json"
        report = json.loads(validation_path.read_text(encoding="utf-8"))
        self.assertEqual("PATCH-001", report["patch_id"])
        self.assertEqual("SEC-001", report["finding_id"])
        self.assertEqual("local-test", report["sandbox_profile"])
        self.assertFalse(report["network_allowed"])
        self.assertTrue(report["patch_applied"])
        self.assertEqual("passed", report["build_status"])
        self.assertEqual("passed", report["test_status"])
        self.assertEqual("bounded", report["diff_scope_status"])
        self.assertEqual("validated", report["final_status"])
        self.assertTrue(report["validation_workspace"]["disposed"])
        self.assertFalse((run_dir / report["validation_workspace"]["path"]).exists())
        self.assertEqual(original_app, (run_dir / "repo" / "app.py").read_text(encoding="utf-8"))
        self.assertNotIn("expected-fixture", (run_dir / "repo" / "app.py").read_text(encoding="utf-8"))
        self.assertTrue((run_dir / "reports" / "remediation" / "SEC-001" / "patch-validation.md").exists())
        events = self.read_command_events(run_dir)
        self.assertEqual(1, len(events), events)
        self.assert_public_command_event(events[0], command="gra-remediate", phase="patch-validate", subject_id="SEC-001")
        self.assertEqual("best-effort-host-python-guard", events[0]["sandbox_profile"])
        self.assertIsNone(events[0]["network_allowed"])
        self.assertIn("reports/remediation/SEC-001/patch-validation.json", events[0]["output_artifact_refs"])

        cp_validate = self.run_cmd([REPO_ROOT / "bin" / "gra-validate-report", "--run", run_dir], check=True)
        self.assertIn("Patch validations: validated", cp_validate.stdout)

        cp_plan = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-issues",
                "--run",
                run_dir,
                "--plan",
            ],
            check=True,
        )
        self.assertIn("patch_validation_statuses=['validated']", cp_plan.stdout)
        plan = json.loads((run_dir / "reports" / "issue-publication-plan.json").read_text(encoding="utf-8"))
        remediation = plan["selected_findings"][0]["remediation_candidate"]
        patch_validation = remediation["candidates"][0]["patch_validation"]
        self.assertTrue(patch_validation["exists"])
        self.assertEqual("validated", patch_validation["results"][0]["final_status"])

    def test_gra_remediate_validate_failed_patch_records_reason_without_modifying_repo(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        self.prepare_patch_validation_run(run_dir)
        original_app = (run_dir / "repo" / "app.py").read_text(encoding="utf-8")
        (run_dir / "reports" / "remediation" / "SEC-001" / "patch.diff").write_text(
            "diff --git a/repo/app.py b/repo/app.py\n"
            "index 969d3b9..0132fa1 100644\n"
            "--- a/repo/app.py\n"
            "+++ b/repo/app.py\n"
            "@@ -1,2 +1,4 @@\n"
            " def handle(value):\n"
            "+    if value:\n"
            "+        return (\n"
            "     return value\n",
            encoding="utf-8",
        )

        cp = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-remediate",
                "--run",
                run_dir,
                "--finding",
                "SEC-001",
                "--validate",
                "--sandbox-profile",
                "local-test",
                "--build-command",
                "python3 -m py_compile repo/app.py",
            ],
            env=self.env_without_credentials(),
        )
        self.assertEqual(1, cp.returncode, cp.stdout + cp.stderr)
        self.assertIn("final_status=failed", cp.stdout)

        report = json.loads((run_dir / "reports" / "remediation" / "SEC-001" / "patch-validation.json").read_text(encoding="utf-8"))
        self.assertTrue(report["patch_applied"])
        self.assertEqual("failed", report["build_status"])
        self.assertEqual("failed", report["final_status"])
        self.assertTrue(any("build command failed" in check["message"] for check in report["checks"]))
        self.assertEqual(original_app, (run_dir / "repo" / "app.py").read_text(encoding="utf-8"))
        cp_validate = self.run_cmd([REPO_ROOT / "bin" / "gra-validate-report", "--run", run_dir], check=True)
        self.assertIn("Patch validations: validated", cp_validate.stdout)

    def test_gra_remediate_validate_rejects_unsafe_operator_command(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        self.prepare_patch_validation_run(run_dir)

        cp = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-remediate",
                "--run",
                run_dir,
                "--finding",
                "SEC-001",
                "--validate",
                "--sandbox-profile",
                "local-test",
                "--build-command",
                "pip install unsafe-package",
            ],
            env=self.env_without_credentials(),
        )
        self.assertEqual(1, cp.returncode, cp.stdout + cp.stderr)
        report = json.loads((run_dir / "reports" / "remediation" / "SEC-001" / "patch-validation.json").read_text(encoding="utf-8"))
        self.assertEqual("failed", report["build_status"])
        self.assertEqual("failed", report["final_status"])
        self.assertEqual("rejected", report["commands_run"][0]["status"])
        self.assertTrue(any("not allowed by default" in check["message"] for check in report["checks"]))

    def test_gra_remediate_validate_rejects_network_operator_command(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        self.prepare_patch_validation_run(run_dir)
        dynamic_import_network_command = 'python3 -c "__import__(\'urllib.request\').request.urlopen(\'https://example.invalid\')"'

        cp = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-remediate",
                "--run",
                run_dir,
                "--finding",
                "SEC-001",
                "--validate",
                "--sandbox-profile",
                "local-test",
                "--build-command",
                dynamic_import_network_command,
            ],
            env=self.env_without_credentials(),
        )
        self.assertEqual(1, cp.returncode, cp.stdout + cp.stderr)
        report = json.loads((run_dir / "reports" / "remediation" / "SEC-001" / "patch-validation.json").read_text(encoding="utf-8"))
        self.assertEqual("failed", report["build_status"])
        self.assertEqual("failed", report["final_status"])
        self.assertEqual("rejected", report["commands_run"][0]["status"])
        self.assertTrue(any("network-capable arguments" in check["message"] for check in report["checks"]))

    def test_gra_remediate_validate_blocks_python_network_at_runtime(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        self.prepare_patch_validation_run(run_dir)
        network_check = run_dir / "repo" / "network_check.py"
        network_check.write_text(
            "import socket\n"
            "socket.socket()\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "-C", str(run_dir / "repo"), "add", "network_check.py"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(run_dir / "repo"),
                "-c",
                "user.name=Fixture",
                "-c",
                "user.email=fixture@example.invalid",
                "commit",
                "-m",
                "add network check",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )

        cp = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-remediate",
                "--run",
                run_dir,
                "--finding",
                "SEC-001",
                "--validate",
                "--sandbox-profile",
                "local-test",
                "--build-command",
                "python3 repo/network_check.py",
            ],
            env=self.env_without_credentials(),
        )
        self.assertEqual(1, cp.returncode, cp.stdout + cp.stderr)
        report = json.loads((run_dir / "reports" / "remediation" / "SEC-001" / "patch-validation.json").read_text(encoding="utf-8"))
        self.assertEqual("failed", report["build_status"])
        self.assertEqual("failed", report["final_status"])
        self.assertEqual(["python3", "repo/network_check.py"], report["commands_run"][0]["argv"])

    def test_gra_remediate_validate_blocks_python_subprocess_network_tools(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        self.prepare_patch_validation_run(run_dir)
        subprocess_check = run_dir / "repo" / "subprocess_check.py"
        subprocess_check.write_text(
            "import subprocess\n"
            "import sys\n"
            "\n"
            "commands = [\n"
            "    ['curl', '--version'],\n"
            "    ['python3', '-S', '-c', 'print(1)'],\n"
            "]\n"
            "for command in commands:\n"
            "    try:\n"
            "        subprocess.run(command, check=False)\n"
            "    except OSError as exc:\n"
            "        if 'disabled by GenAI Repo Auditor patch validation' in str(exc) or 'Python guard bypass flags are disabled' in str(exc):\n"
            "            continue\n"
            "        raise\n"
            "    raise SystemExit(9)\n"
            "import os\n"
            "exec_commands = [\n"
            "    (sys.executable, [sys.executable, '-S', '-c', 'raise SystemExit(9)'], None),\n"
            "    (sys.executable, [sys.executable, '-c', 'raise SystemExit(9)'], {}),\n"
            "]\n"
            "for path, argv, env in exec_commands:\n"
            "    try:\n"
            "        if env is None:\n"
            "            os.execv(path, argv)\n"
            "        else:\n"
            "            os.execve(path, argv, env)\n"
            "    except OSError as exc:\n"
            "        if 'Python guard bypass flags are disabled' in str(exc) or 'Python guard environment is required' in str(exc):\n"
            "            continue\n"
            "        raise\n"
            "    raise SystemExit(9)\n"
            "for name in ['posix_spawn', 'posix_spawnp']:\n"
            "    if not hasattr(os, name):\n"
            "        continue\n"
            "    try:\n"
            "        pid = getattr(os, name)(sys.executable, [sys.executable, '-S', '-c', 'raise SystemExit(9)'], {})\n"
            "    except OSError as exc:\n"
            "        if 'Python guard bypass flags are disabled' in str(exc) or 'Python guard environment is required' in str(exc):\n"
            "            continue\n"
            "        raise\n"
            "    else:\n"
            "        os.waitpid(pid, 0)\n"
            "        raise SystemExit(9)\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "-C", str(run_dir / "repo"), "add", "subprocess_check.py"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(run_dir / "repo"),
                "-c",
                "user.name=Fixture",
                "-c",
                "user.email=fixture@example.invalid",
                "commit",
                "-m",
                "add subprocess check",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )

        cp = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-remediate",
                "--run",
                run_dir,
                "--finding",
                "SEC-001",
                "--validate",
                "--sandbox-profile",
                "local-test",
                "--build-command",
                "python3 repo/subprocess_check.py",
                "--test-command",
                "python3 repo/subprocess_check.py",
            ],
            env=self.env_without_credentials(),
            check=True,
        )
        self.assertIn("final_status=validated", cp.stdout)
        report = json.loads((run_dir / "reports" / "remediation" / "SEC-001" / "patch-validation.json").read_text(encoding="utf-8"))
        self.assertEqual("passed", report["build_status"])
        self.assertEqual("passed", report["test_status"])
        self.assertEqual("validated", report["final_status"])

    def test_gra_remediate_validate_without_commands_needs_human_review(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        self.prepare_patch_validation_run(run_dir)

        cp = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-remediate",
                "--run",
                run_dir,
                "--finding",
                "SEC-001",
                "--validate",
                "--sandbox-profile",
                "local-test",
            ],
            env=self.env_without_credentials(),
            check=True,
        )
        self.assertIn("final_status=needs-human-review", cp.stdout)
        report = json.loads((run_dir / "reports" / "remediation" / "SEC-001" / "patch-validation.json").read_text(encoding="utf-8"))
        self.assertEqual("not-run", report["build_status"])
        self.assertEqual("not-run", report["test_status"])
        self.assertEqual("needs-human-review", report["final_status"])

    def test_gra_remediate_validate_fails_closed_when_sandbox_not_ready(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        self.prepare_patch_validation_run(run_dir)
        (run_dir / "repo" / "dirty.txt").write_text("uncommitted change\n", encoding="utf-8")

        cp = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-remediate",
                "--run",
                run_dir,
                "--finding",
                "SEC-001",
                "--validate",
                "--sandbox-profile",
                "local-test",
                "--build-command",
                "python3 -m py_compile repo/app.py",
            ],
            env=self.env_without_credentials(),
        )
        self.assertEqual(1, cp.returncode, cp.stdout + cp.stderr)
        report = json.loads((run_dir / "reports" / "remediation" / "SEC-001" / "patch-validation.json").read_text(encoding="utf-8"))
        self.assertFalse(report["patch_applied"])
        self.assertEqual("failed", report["final_status"])
        self.assertTrue(any(check["id"] == "sandbox-readiness" and check["status"] == "fail" for check in report["checks"]))

    def test_validate_report_rejects_invalid_remediation_candidate_contract(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        remediation_dir = run_dir / "reports" / "remediation" / "SEC-001"
        remediation_dir.mkdir(parents=True)
        (remediation_dir / "patch.txt").write_text("not a diff\n", encoding="utf-8")
        invalid = {
            "schema_version": "1",
            "run_id": "fixture-run",
            "repo": "example/demo",
            "generated_at": "2026-06-21T00:00:00Z",
            "candidates": [
                {
                    "id": "PATCH-001",
                    "finding_id": "SEC-404",
                    "status": "applied",
                    "safe_by_design": False,
                    "patch_file": "reports/remediation/SEC-001/patch.txt",
                    "summary": "",
                    "files_touched": ["../repo/app.py"],
                    "expected_validation": [123],
                    "limitations": [],
                    "requires_human_review": False,
                }
            ],
        }
        (run_dir / "reports" / "remediation" / "remediation-candidates.json").write_text(
            json.dumps(invalid, indent=2) + "\n",
            encoding="utf-8",
        )

        cp = self.run_cmd([REPO_ROOT / "bin" / "gra-validate-report", "--run", run_dir])

        self.assertNotEqual(cp.returncode, 0)
        self.assertIn("finding 'SEC-404' is not present", cp.stderr)
        self.assertIn("status: remediation candidates must remain draft", cp.stderr)
        self.assertIn("safe_by_design: must be true", cp.stderr)
        self.assertIn("requires_human_review: must be true", cp.stderr)
        self.assertIn("files_touched[0]", cp.stderr)
        self.assertIn("expected_validation[0]", cp.stderr)
        self.assertIn("patch_file: remediation artifact path must end with .diff", cp.stderr)

    def test_gra_proofs_all_critical_high_goal_selects_relevant_findings(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        findings_path = run_dir / "reports" / "findings.json"
        findings = json.loads(findings_path.read_text(encoding="utf-8"))
        base = findings["findings"][0]
        findings["findings"].extend(
            [
                {**base, "id": "SEC-002", "fingerprint": "fixture-fingerprint-0002", "severity": "Low", "status": "Confirmed"},
                {**base, "id": "SEC-003", "fingerprint": "fixture-fingerprint-0003", "severity": "High", "status": "Invalid"},
                {**base, "id": "SEC-004", "fingerprint": "fixture-fingerprint-0004", "severity": "Critical", "status": "Potential"},
            ]
        )
        findings_path.write_text(json.dumps(findings, indent=2) + "\n", encoding="utf-8")

        env, codex_log = self.env_with_codex_log()
        cp = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-proofs",
                "--run",
                run_dir,
                "--all-critical-high",
                "--mode",
                "goal",
            ],
            env=env,
            check=True,
        )
        self.assertIn("Prepared supervised /goal safe local proof run.", cp.stdout)
        subjects = json.loads((run_dir / "reports" / "proofs" / "critical-high.subjects.json").read_text(encoding="utf-8"))
        self.assertEqual(["SEC-001", "SEC-004"], [item["finding_id"] for item in subjects["subjects"]])
        prompt = run_dir / "prompts" / "goal" / "safe-proof-critical-high.goal.md"
        prompt_text = prompt.read_text(encoding="utf-8")
        self.assertTrue(prompt_text.startswith("/goal "))
        self.assertIn("No working exploit scripts.", prompt_text)
        self.assertIn("Do not modify files under repo/.", prompt_text)
        self.assertIn("Every proof must set safe_by_design to true.", prompt_text)
        self.assertEqual(self.read_codex_calls(codex_log), [])
        events = self.read_command_events(run_dir)
        self.assertEqual(1, len(events), events)
        self.assert_public_command_event(events[0], command="gra-proofs", phase="goal", subject_id="critical-high")
        self.assertIn("reports/proofs/critical-high.subjects.json", events[0]["output_artifact_refs"])
        self.assertIn("prompts/goal/safe-proof-critical-high.goal.md", events[0]["output_artifact_refs"])

    def test_gra_proofs_all_critical_high_requires_findings_json(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        (run_dir / "reports" / "findings.json").unlink()
        env, codex_log = self.env_with_codex_log()
        cp = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-proofs",
                "--run",
                run_dir,
                "--all-critical-high",
            ],
            env=env,
        )
        self.assertEqual(cp.returncode, 2)
        self.assertIn("findings.json not found", cp.stderr)
        self.assertEqual(self.read_codex_calls(codex_log), [])

    def test_gra_chains_exec_renders_prompt_and_writes_chain_artifacts(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        env, codex_log = self.env_with_codex_log(GRA_MOCK_FIXTURE_DIR=str(FIXTURES / "chain-output"))
        cp = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-chains",
                "--run",
                run_dir,
                "--model",
                "gpt-fixture",
                "--effort",
                "medium",
            ],
            env=env,
            check=True,
        )
        self.assertIn("Running Codex defensive chain synthesis for example/demo", cp.stdout)
        self.assertIn("Codex status: 0", cp.stdout)

        prompt = run_dir / "prompts" / "exec" / "synthesize-chains.prompt.md"
        prompt_text = prompt.read_text(encoding="utf-8")
        self.assertIn("Do not implement exploit generation.", prompt_text)
        self.assertIn("No exploit code.", prompt_text)
        self.assertIn("No exploit payloads.", prompt_text)
        self.assertIn("safe validation plan", prompt_text)
        self.assertIn("reports/chains.json", prompt_text)
        self.assertIn("reports/ATTACK_CHAINS.md", prompt_text)
        self.assertNotIn("{{", prompt_text)

        chains = json.loads((run_dir / "reports" / "chains.json").read_text(encoding="utf-8"))
        self.assertEqual("CHAIN-001", chains["chains"][0]["id"])
        self.assertEqual(["SEC-001"], chains["chains"][0]["findings"])
        self.assertEqual(["TGT-001"], chains["chains"][0]["targets"])
        attack_chains = (run_dir / "reports" / "ATTACK_CHAINS.md").read_text(encoding="utf-8")
        self.assertIn("Non-public by default", attack_chains)
        self.assertIn("CHAIN-001", attack_chains)

        final_path = run_dir / "codex-chains-final.md"
        events_path = run_dir / "codex-chains-events.jsonl"
        stderr_path = run_dir / "codex-chains-stderr.txt"
        self.assertEqual(final_path.read_text(encoding="utf-8"), "mock codex mode=success\n")
        self.assertIn('"status": "ok"', events_path.read_text(encoding="utf-8"))
        self.assertTrue(stderr_path.exists())
        calls = self.read_codex_calls(codex_log)
        self.assertEqual(len(calls), 1, calls)
        self.assertIn(str(final_path), calls[0])
        self.assertIn('model_reasoning_effort="medium"', calls[0])
        events = self.read_command_events(run_dir)
        self.assertEqual(1, len(events), events)
        self.assert_public_command_event(events[0], command="gra-chains", phase="chain")
        self.assertIn("reports/chains.json", events[0]["output_artifact_refs"])
        self.assertIn("codex-chains-final.md", events[0]["output_artifact_refs"])

        cp_validate = self.run_cmd([REPO_ROOT / "bin" / "gra-validate-report", "--run", run_dir], check=True)
        self.assertIn("Chains: validated", cp_validate.stdout)

    def test_gra_chains_goal_prepares_prompt_without_codex_exec(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        env, codex_log = self.env_with_codex_log()
        cp = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-chains",
                "--run",
                run_dir,
                "--mode",
                "goal",
            ],
            env=env,
            check=True,
        )
        self.assertIn("Prepared supervised /goal chain synthesis run.", cp.stdout)
        prompt = run_dir / "prompts" / "goal" / "synthesize-chains.goal.md"
        prompt_text = prompt.read_text(encoding="utf-8")
        self.assertTrue(prompt_text.startswith("/goal "))
        self.assertIn("No exploit code.", prompt_text)
        self.assertIn("No exploit payloads.", prompt_text)
        self.assertIn("safe validation plan", prompt_text)
        self.assertEqual(self.read_codex_calls(codex_log), [])
        self.assertFalse((run_dir / "codex-chains-final.md").exists())
        events = self.read_command_events(run_dir)
        self.assertEqual(1, len(events), events)
        self.assert_public_command_event(events[0], command="gra-chains", phase="goal")
        self.assertIn("prompts/goal/synthesize-chains.goal.md", events[0]["output_artifact_refs"])

    def test_advanced_chain_proof_validation_workflow_fixture(self) -> None:
        run_dir = self.copy_fixture_run("advanced-workflow-run")
        env, codex_log = self.env_with_codex_log(GRA_MOCK_FIXTURE_DIR=str(FIXTURES / "advanced-workflow-output"))

        cp_chains = self.run_cmd([REPO_ROOT / "bin" / "gra-chains", "--run", run_dir], env=env, check=True)
        self.assertIn("Running Codex defensive chain synthesis for example/advanced-workflow", cp_chains.stdout)

        cp_proofs = self.run_cmd(
            [REPO_ROOT / "bin" / "gra-proofs", "--run", run_dir, "--all-critical-high"],
            env=env,
            check=True,
        )
        self.assertIn("Running Codex safe local proof generation for critical-high", cp_proofs.stdout)

        cp_validation = self.run_cmd(
            [REPO_ROOT / "bin" / "gra-adversarial-validate", "--run", run_dir, "--all-critical-high"],
            env=env,
            check=True,
        )
        self.assertIn("Running Codex adversarial validation for critical-high", cp_validation.stdout)

        chains = json.loads((run_dir / "reports" / "chains.json").read_text(encoding="utf-8"))
        self.assertEqual(["SEC-101", "SEC-102"], chains["chains"][0]["findings"])
        self.assertEqual(["TGT-101", "TGT-102"], chains["chains"][0]["targets"])
        self.assertIn("reports/scanner-results/normalized/semgrep.normalized.json", chains["chains"][0]["scanner_refs"])

        proofs = json.loads((run_dir / "reports" / "proofs.json").read_text(encoding="utf-8"))
        self.assertEqual(["SEC-101", "SEC-102"], [proof["finding_id"] for proof in proofs["proofs"]])
        self.assertTrue((run_dir / "reports" / "proofs" / "SEC-101-test-plan.md").exists())
        self.assertTrue((run_dir / "reports" / "proofs" / "SEC-102-static-trace.md").exists())

        validations = json.loads((run_dir / "reports" / "validation.json").read_text(encoding="utf-8"))
        self.assertEqual(["SEC-101", "SEC-102"], [item["subject_id"] for item in validations["validations"]])
        self.assertEqual(["confirm", "downgrade"], [item["decision"] for item in validations["validations"]])

        proof_subjects = json.loads(
            (run_dir / "reports" / "proofs" / "critical-high.subjects.json").read_text(encoding="utf-8")
        )
        self.assertEqual(["SEC-101", "SEC-102"], [item["finding_id"] for item in proof_subjects["subjects"]])
        validation_subjects = json.loads(
            (run_dir / "reports" / "adversarial-validation" / "critical-high.subjects.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(["SEC-101", "SEC-102"], [item["subject_id"] for item in validation_subjects["subjects"]])

        cp_validate = self.run_cmd([REPO_ROOT / "bin" / "gra-validate-report", "--run", run_dir], check=True)
        for expected in [
            "Findings: 3",
            "Targets: validated",
            "Scanner index: validated",
            "Chains: validated",
            "Adversarial validations: validated",
            "Proofs: validated",
        ]:
            self.assertIn(expected, cp_validate.stdout)

        cp_dashboard = self.run_cmd([REPO_ROOT / "bin" / "gra-dashboard", "--run", run_dir], check=True)
        self.assertIn("dashboard.html", cp_dashboard.stdout)
        dashboard = (run_dir / "reports" / "dashboard.html").read_text(encoding="utf-8")
        self.assertIn("Fixture upload input reaches report renderer", dashboard)
        self.assertIn("Finding assessment dimensions", dashboard)

        cp_sarif = self.run_cmd([REPO_ROOT / "bin" / "gra-sarif", "--run", run_dir], check=True)
        self.assertIn("findings.sarif", cp_sarif.stdout)
        sarif = json.loads((run_dir / "reports" / "findings.sarif").read_text(encoding="utf-8"))
        self.assertEqual({"SEC-101", "SEC-102", "SEC-103"}, {result["ruleId"] for result in sarif["runs"][0]["results"]})

        calls = self.read_codex_calls(codex_log)
        self.assertEqual(3, len(calls), calls)
        for call in calls:
            self.assertIn("sandbox_workspace_write.network_access=false", call)
