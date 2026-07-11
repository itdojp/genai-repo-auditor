from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "lib"))

import run_events  # noqa: E402

EventValidationError = run_events.EventValidationError
EventWriteError = run_events.EventWriteError
COMMAND_EVENT_PRODUCERS = run_events.COMMAND_EVENT_PRODUCERS
append_command_event = run_events.append_command_event
build_command_event = run_events.build_command_event
load_command_events = run_events.load_command_events
preflight_command_event = run_events.preflight_command_event
start_command_event = run_events.start_command_event
validate_command_event_payload = run_events.validate_command_event_payload


class RunEventsTests(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        self.tmp_parent = REPO_ROOT / ".test-tmp"
        self.tmp_parent.mkdir(exist_ok=True)
        self.work_dir = Path(tempfile.mkdtemp(prefix=f"{self._testMethodName}-", dir=self.tmp_parent))

    def tearDown(self) -> None:
        shutil.rmtree(self.work_dir, ignore_errors=True)
        with contextlib.suppress(OSError):
            self.tmp_parent.rmdir()

    def make_run(self) -> Path:
        run_dir = self.work_dir / "run"
        (run_dir / "reports").mkdir(parents=True)
        (run_dir / "context.json").write_text(
            json.dumps({"run_id": "fixture-run", "repo": "example/demo", "reports_dir": "reports"}) + "\n",
            encoding="utf-8",
        )
        return run_dir

    def test_append_command_event_writes_v2_safe_metadata(self) -> None:
        run_dir = self.make_run()
        (run_dir / "reports" / "input.json").write_text("{}\n", encoding="utf-8")
        started_at, started_perf = start_command_event()

        path = append_command_event(
            run_dir,
            command="gra-research",
            phase="exec",
            target_id="TGT-001",
            started_at=started_at,
            started_perf=started_perf,
            exit_code=0,
            worker_profile="profiles/codex-cli.json",
            model="gpt-5.5",
            effort="xhigh",
            sandbox_profile="danger-full-access",
            network_allowed=False,
            prompt_hash="sha256:" + "a" * 64,
            input_artifact_paths=["reports/input.json"],
            output_artifact_paths=[run_dir / "reports" / "target-research" / "TGT-001.md"],
            redaction_count=2,
        )

        self.assertEqual(run_dir / "reports" / "command-events.jsonl", path)
        events = load_command_events(run_dir)
        self.assertEqual(1, len(events))
        event = events[0]
        self.assertEqual("2", event["schema_version"])
        self.assertRegex(event["event_id"], r"^[0-9a-f-]{36}$")
        self.assertEqual("fixture-run", event["run_id"])
        self.assertEqual("example/demo", event["repo"])
        self.assertEqual("succeeded", event["status"])
        self.assertEqual(1, event["attempt"])
        self.assertEqual(["reports/input.json"], event["input_artifact_refs"])
        self.assertEqual(["reports/target-research/TGT-001.md"], event["output_artifact_refs"])
        self.assertEqual(event["output_artifact_refs"], event["artifact_paths"])
        self.assertFalse(event["network_allowed"])
        validate_command_event_payload(event)

    def test_reader_accepts_existing_v1_and_new_v2_records(self) -> None:
        run_dir = self.make_run()
        v1 = {
            "schema_version": "1",
            "run_id": "fixture-run",
            "repo": "example/demo",
            "command": "gra-gapfill",
            "phase": "list",
            "target_id": None,
            "started_at": "2026-05-16T00:00:00Z",
            "ended_at": "2026-05-16T00:00:01Z",
            "duration_ms": 1000,
            "exit_code": 0,
            "model": None,
            "effort": None,
            "artifact_paths": ["reports/COVERAGE.md"],
            "source": "genai-repo-auditor",
        }
        validate_command_event_payload(v1)
        started_at, started_perf = start_command_event()
        v2 = build_command_event(
            run_dir,
            command="gra-validate-report",
            phase="validate",
            started_at=started_at,
            started_perf=started_perf,
            exit_code=1,
            status="failed",
            attempt=2,
            retry_of="11111111-2222-3333-4444-555555555555",
            error_category="schema_validation",
        )
        events_path = run_dir / "reports" / "command-events.jsonl"
        events_path.write_text(json.dumps(v1, sort_keys=True) + "\n" + json.dumps(v2, sort_keys=True) + "\n", encoding="utf-8")

        events = load_command_events(run_dir)
        self.assertEqual(["1", "2"], [event["schema_version"] for event in events])
        self.assertEqual("failed", events[1]["status"])
        self.assertEqual(2, events[1]["attempt"])
        validate_command_event_payload(events[1])

    def test_concurrent_append_writes_complete_unique_json_lines(self) -> None:
        run_dir = self.make_run()
        errors: list[Exception] = []
        real_write = os.write

        def partial_write(fd: int, data: bytes) -> int:
            chunk = data[: max(1, min(23, len(data)))]
            return real_write(fd, chunk)

        def worker(index: int) -> None:
            try:
                started_at, started_perf = start_command_event()
                append_command_event(
                    run_dir,
                    command="gra-research",
                    phase="exec",
                    target_id=f"TGT-{index + 1:03d}",
                    started_at=started_at,
                    started_perf=started_perf,
                    exit_code=0,
                )
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(index,)) for index in range(32)]
        original_write = run_events.os.write
        try:
            run_events.os.write = partial_write
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
        finally:
            run_events.os.write = original_write

        self.assertEqual([], errors)
        raw_lines = (run_dir / "reports" / "command-events.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(32, len(raw_lines))
        events = [json.loads(line) for line in raw_lines]
        self.assertEqual(32, len({event["event_id"] for event in events}))
        self.assertEqual(32, len(load_command_events(run_dir)))

    def test_unsafe_artifact_paths_and_forbidden_payloads_are_rejected(self) -> None:
        run_dir = self.make_run()
        started_at, started_perf = start_command_event()
        with self.assertRaises(EventWriteError):
            append_command_event(
                run_dir,
                command="gra-research",
                phase="exec",
                target_id="TGT-001",
                started_at=started_at,
                started_perf=started_perf,
                exit_code=0,
                artifact_paths=[self.work_dir / "outside.txt"],
            )

        event = build_command_event(
            run_dir,
            command="gra-research",
            phase="exec",
            target_id="TGT-001",
            started_at=started_at,
            started_perf=started_perf,
            exit_code=0,
        )
        event["raw_prompt"] = "review the target"
        with self.assertRaisesRegex(EventValidationError, "raw_prompt"):
            validate_command_event_payload(event)
        event.pop("raw_prompt")
        event["prompt hash"] = "b" * 64
        with self.assertRaisesRegex(EventValidationError, "prompt hash"):
            validate_command_event_payload(event)
        event.pop("prompt hash")
        event["model"] = "ghp_" + "1" * 36
        with self.assertRaisesRegex(EventValidationError, "secret-like"):
            validate_command_event_payload(event)
        event.pop("model")
        # Alias-style keys must be rejected; only canonical snake_case keys are allowed.
        event["prompt hash"] = "sha256:" + "a" * 64
        with self.assertRaisesRegex(EventValidationError, "prompt hash"):
            validate_command_event_payload(event)


    def test_leaf_symlink_event_file_is_rejected(self) -> None:
        run_dir = self.make_run()
        outside = self.work_dir / "outside-events.jsonl"
        event_path = run_dir / "reports" / "command-events.jsonl"
        try:
            event_path.symlink_to(outside)
        except (NotImplementedError, OSError) as exc:
            self.skipTest(f"symlink not available: {exc}")
        started_at, started_perf = start_command_event()

        with self.assertRaises(EventWriteError):
            append_command_event(
                run_dir,
                command="gra-research",
                phase="exec",
                target_id="TGT-001",
                started_at=started_at,
                started_perf=started_perf,
                exit_code=0,
            )
        self.assertFalse(outside.exists())

    def test_short_writes_are_retried_and_zero_write_fails_closed(self) -> None:
        run_dir = self.make_run()
        real_write = os.write
        calls = {"count": 0}

        def partial_write(fd: int, data: bytes) -> int:
            calls["count"] += 1
            chunk = data[: max(1, min(17, len(data)))]
            return real_write(fd, chunk)

        started_at, started_perf = start_command_event()
        original_write = run_events.os.write
        try:
            run_events.os.write = partial_write
            append_command_event(
                run_dir,
                command="gra-validate-report",
                phase="validate",
                started_at=started_at,
                started_perf=started_perf,
                exit_code=0,
            )
        finally:
            run_events.os.write = original_write
        self.assertGreater(calls["count"], 1)
        self.assertEqual(1, len(load_command_events(run_dir)))

        def zero_write(fd: int, data: bytes) -> int:
            return 0

        started_at, started_perf = start_command_event()
        try:
            run_events.os.write = zero_write
            with self.assertRaises(EventWriteError):
                append_command_event(
                    run_dir,
                    command="gra-validate-report",
                    phase="validate",
                    started_at=started_at,
                    started_perf=started_perf,
                    exit_code=0,
                )
        finally:
            run_events.os.write = original_write

    def test_write_failure_modes_are_explicit(self) -> None:
        run_dir = self.make_run()
        events_path = run_dir / "reports" / "command-events.jsonl"
        events_path.mkdir()
        started_at, started_perf = start_command_event()

        with self.assertRaises(EventWriteError):
            append_command_event(
                run_dir,
                command="gra-validate-report",
                phase="validate",
                started_at=started_at,
                started_perf=started_perf,
                exit_code=0,
            )

        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            result = append_command_event(
                run_dir,
                command="gra-validate-report",
                phase="validate",
                started_at=started_at,
                started_perf=started_perf,
                exit_code=0,
                failure_mode="warn",
            )
        self.assertIsNone(result)
        self.assertIn("WARNING: command event was not written", stderr.getvalue())

    def test_preflight_reserves_safe_event_path_and_rejects_unsafe_refs(self) -> None:
        run_dir = self.make_run()
        path = preflight_command_event(
            run_dir,
            input_artifact_paths=[run_dir / "context.json"],
            output_artifact_paths=[run_dir / "reports" / "result.json"],
        )
        self.assertTrue(path.is_file())
        self.assertEqual(b"", path.read_bytes())

        path.unlink()
        non_reserved_path = preflight_command_event(
            run_dir,
            input_artifact_paths=[run_dir / "context.json"],
            reserve_file=False,
        )
        self.assertEqual(path, non_reserved_path)
        self.assertFalse(path.exists())

        # Existing logs are never removed by the non-reserving reporting mode.
        path.write_text("existing\n", encoding="utf-8")
        preflight_command_event(run_dir, reserve_file=False)
        self.assertEqual("existing\n", path.read_text(encoding="utf-8"))

        with self.assertRaises(EventWriteError):
            preflight_command_event(run_dir, output_artifact_paths=[self.work_dir / "outside.json"])

        path.unlink()
        path.symlink_to(self.work_dir / "outside-events.jsonl")
        with self.assertRaises(EventWriteError):
            preflight_command_event(run_dir)

    def test_declared_event_producers_have_instrumented_entry_points(self) -> None:
        expected_producers = {
            "gra-adversarial-validate",
            "gra-audit",
            "gra-benchmark",
            "gra-chains",
            "gra-dashboard",
            "gra-evidence-graph",
            "gra-gapfill",
            "gra-import-findings",
            "gra-ingest",
            "gra-issues",
            "gra-metrics",
            "gra-proofs",
            "gra-recon",
            "gra-remediate",
            "gra-research",
            "gra-sarif",
            "gra-scan",
            "gra-scanner-triage",
            "gra-store",
            "gra-targets",
            "gra-trace",
            "gra-validate-report",
            "gra-variant",
        }
        self.assertEqual(expected_producers, set(COMMAND_EVENT_PRODUCERS))
        for command in COMMAND_EVENT_PRODUCERS:
            entry_point = REPO_ROOT / "bin" / command
            self.assertTrue(entry_point.is_file(), command)
            self.assertIn("append_command_event", entry_point.read_text(encoding="utf-8"), command)

    def test_non_reserving_preflight_does_not_delete_a_concurrent_append(self) -> None:
        run_dir = self.make_run()
        preflight_waiting = threading.Event()
        append_finished = threading.Event()
        real_acquire = run_events._acquire_event_append_lock
        main_thread = threading.current_thread()

        def delayed_acquire(path: Path, *, timeout_seconds: float = 10.0) -> Path:
            if threading.current_thread() is main_thread:
                preflight_waiting.set()
                self.assertTrue(append_finished.wait(timeout=5))
            return real_acquire(path, timeout_seconds=timeout_seconds)

        def append_worker() -> None:
            self.assertTrue(preflight_waiting.wait(timeout=5))
            started_at, started_perf = start_command_event()
            append_command_event(
                run_dir,
                command="gra-research",
                phase="exec",
                target_id="TGT-001",
                started_at=started_at,
                started_perf=started_perf,
                exit_code=0,
            )
            append_finished.set()

        worker = threading.Thread(target=append_worker)
        original_acquire = run_events._acquire_event_append_lock
        try:
            run_events._acquire_event_append_lock = delayed_acquire
            worker.start()
            preflight_command_event(run_dir, reserve_file=False)
            worker.join(timeout=5)
        finally:
            run_events._acquire_event_append_lock = original_acquire

        self.assertFalse(worker.is_alive())
        events = load_command_events(run_dir)
        self.assertEqual(1, len(events))
        self.assertEqual("gra-research", events[0]["command"])

    def test_full_event_preflight_rejects_invalid_context_before_reserving_file(self) -> None:
        run_dir = self.make_run()
        context_path = run_dir / "context.json"
        context = json.loads(context_path.read_text(encoding="utf-8"))
        context["repo"] = "invalid repo with spaces"
        context_path.write_text(json.dumps(context) + "\n", encoding="utf-8")
        started_at, started_perf = start_command_event()

        with self.assertRaisesRegex(EventWriteError, "event.repo"):
            preflight_command_event(
                run_dir,
                input_artifact_paths=[context_path],
                event_fields={
                    "command": "gra-store",
                    "phase": "store",
                    "started_at": started_at,
                    "started_perf": started_perf,
                    "exit_code": 0,
                },
                reserve_file=False,
            )

        self.assertFalse((run_dir / "reports" / "command-events.jsonl").exists())

    def test_broken_symlink_artifact_component_is_rejected(self) -> None:
        run_dir = self.make_run()
        broken_link = run_dir / "reports" / "broken-link"
        try:
            broken_link.symlink_to("/nonexistent/target")
        except (NotImplementedError, OSError) as exc:
            self.skipTest(f"symlink not available: {exc}")

        started_at, started_perf = start_command_event()
        with self.assertRaises(EventWriteError):
            append_command_event(
                run_dir,
                command="gra-research",
                phase="exec",
                started_at=started_at,
                started_perf=started_perf,
                exit_code=0,
                output_artifact_paths=[broken_link],
            )


if __name__ == "__main__":
    unittest.main()
