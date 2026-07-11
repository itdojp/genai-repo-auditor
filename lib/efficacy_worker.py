from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

from agent_worker import AgentWorkerProfileError, check_profile_executable, load_profile
from efficacy_benchmark import EfficacyBenchmarkError
from efficacy_corpus import EfficacyCorpusError, load_schema_object, validate_schema_object
from gralib import build_codex_exec_args


MAX_WORKER_PROMPT_BYTES = 512_000
MAX_WORKER_ARTIFACT_BYTES = 2_000_000
MAX_WORKER_RESPONSE_BYTES = 512_000
MAX_VERSION_OUTPUT_BYTES = 4_096
WORKER_POLL_SECONDS = 0.05
MINIMUM_CODEX_VERSION = (0, 135, 0)
MODEL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
EFFORT_RE = re.compile(r"^[a-z][a-z0-9-]{0,31}$")
CODEX_VERSION_RE = re.compile(rb"\bcodex-cli (\d+)\.(\d+)\.(\d+)\b")


def _worker_environment(source: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(os.environ if source is None else source)
    allowed_names = {
        "APPDATA",
        "CODEX_HOME",
        "COMSPEC",
        "HOME",
        "HTTPS_PROXY",
        "HTTP_PROXY",
        "LANG",
        "LOCALAPPDATA",
        "LOGNAME",
        "NO_PROXY",
        "OPENAI_API_KEY",
        "PATH",
        "PATHEXT",
        "SSL_CERT_DIR",
        "SSL_CERT_FILE",
        "SYSTEMROOT",
        "TEMP",
        "TMP",
        "TMPDIR",
        "USER",
        "USERPROFILE",
        "WINDIR",
        "XDG_CACHE_HOME",
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
    }
    return {key: value for key, value in env.items() if key.upper() in allowed_names or key.upper().startswith("LC_")}


def _worker_base(path: Path) -> Path:
    base = Path(os.path.abspath(os.fspath(path.expanduser())))
    cwd = Path.cwd().resolve(strict=True)
    try:
        relative = base.relative_to(cwd)
    except ValueError as exc:
        raise EfficacyBenchmarkError("--worker-dir must stay under the current working directory") from exc
    if not relative.parts:
        raise EfficacyBenchmarkError("--worker-dir must not be the current working directory")
    current = cwd
    for component in relative.parts:
        current = current / component
        if current.is_symlink():
            raise EfficacyBenchmarkError("--worker-dir must not contain symlink components")
        if not current.exists() or not current.is_dir():
            raise EfficacyBenchmarkError("--worker-dir must be an existing directory")
    return base


def _bounded_artifact(path: Path, *, maximum: int, label: str) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd: int | None = None
    try:
        path_metadata = path.lstat()
        if stat.S_ISLNK(path_metadata.st_mode):
            raise EfficacyBenchmarkError(f"{label} must be a regular non-symlink file")
        fd = os.open(path, flags)
        metadata = os.fstat(fd)
    except OSError as exc:
        raise EfficacyBenchmarkError(f"{label} is missing or unreadable") from exc
    try:
        if not stat.S_ISREG(metadata.st_mode):
            raise EfficacyBenchmarkError(f"{label} must be a regular non-symlink file")
        if (path_metadata.st_dev, path_metadata.st_ino) != (metadata.st_dev, metadata.st_ino):
            raise EfficacyBenchmarkError(f"{label} changed while it was opened")
        if metadata.st_size > maximum:
            raise EfficacyBenchmarkError(f"{label} exceeds the {maximum}-byte limit")
        chunks: list[bytes] = []
        remaining = maximum + 1
        while remaining:
            chunk = os.read(fd, min(65_536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        if len(raw) > maximum:
            raise EfficacyBenchmarkError(f"{label} exceeds the {maximum}-byte limit")
        return raw
    finally:
        if fd is not None:
            os.close(fd)


def _artifact_size(path: Path, *, label: str) -> int:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return 0
    except OSError as exc:
        raise EfficacyBenchmarkError(f"{label} is unreadable") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise EfficacyBenchmarkError(f"{label} must be a regular non-symlink file")
    return metadata.st_size


def _wait_bounded_process(
    process: subprocess.Popen[Any],
    *,
    timeout_seconds: int,
    limits: tuple[tuple[Path, int, str], ...],
) -> tuple[int, str | None]:
    started = time.monotonic()
    try:
        while process.poll() is None:
            failure: str | None = None
            if time.monotonic() - started > timeout_seconds:
                failure = "timed out"
            else:
                for path, maximum, label in limits:
                    if _artifact_size(path, label=label) > maximum:
                        failure = f"exceeded the {label} size limit"
                        break
            if failure is not None:
                process.kill()
                process.wait(timeout=10)
                return process.returncode if process.returncode is not None else -1, failure
            time.sleep(WORKER_POLL_SECONDS)
        return process.returncode if process.returncode is not None else -1, None
    except (Exception, KeyboardInterrupt):
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)
        raise


def _require_codex_cli_version(executable: Path, workspace: Path, env: dict[str, str]) -> str:
    stdout_path = workspace / "codex-version.txt"
    stderr_path = workspace / "codex-version-stderr.txt"
    try:
        with stdout_path.open("x", encoding="utf-8") as stdout, stderr_path.open(
            "x", encoding="utf-8"
        ) as stderr:
            process = subprocess.Popen(
                [str(executable), "--version"],
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                text=True,
                cwd=workspace,
                env=env,
            )
            returncode, failure = _wait_bounded_process(
                process,
                timeout_seconds=10,
                limits=(
                    (stdout_path, MAX_VERSION_OUTPUT_BYTES, "Codex version output"),
                    (stderr_path, MAX_VERSION_OUTPUT_BYTES, "Codex version stderr"),
                ),
            )
    except (OSError, subprocess.SubprocessError) as exc:
        raise EfficacyBenchmarkError("unable to probe the efficacy worker Codex CLI version") from exc
    if failure is not None:
        raise EfficacyBenchmarkError(f"efficacy worker Codex CLI version probe {failure}")
    if returncode != 0:
        raise EfficacyBenchmarkError(f"efficacy worker Codex CLI version probe exited with status {returncode}")
    raw = _bounded_artifact(
        stdout_path,
        maximum=MAX_VERSION_OUTPUT_BYTES,
        label="Codex version output",
    )
    match = CODEX_VERSION_RE.search(raw)
    if match is None:
        raise EfficacyBenchmarkError("efficacy worker executable did not report a supported codex-cli version")
    version = tuple(int(component) for component in match.groups())
    if version < MINIMUM_CODEX_VERSION:
        raise EfficacyBenchmarkError("efficacy worker requires codex-cli 0.135.0 or newer")
    return ".".join(str(component) for component in version)


def _worker_prompt(cases: list[dict[str, Any]], fixture_texts: dict[str, dict[str, str]]) -> str:
    payload = {
        "schema_version": "1",
        "task": "defensive-synthetic-fixture-classification",
        "cases": [
            {
                "case_id": case["case_id"],
                "category": case["category"],
                "fixture_files": fixture_texts[case["case_id"]],
            }
            for case in cases
        ],
    }
    instructions = """You are evaluating non-deployable public-safe synthetic security fixtures.
Do not execute commands, access a network, search the web, access GitHub, or publish anything.
Review only the JSON input below. Return one JSON object and no Markdown or prose.
The object must use schema_version \"1\" and contain exactly one cases entry per supplied case_id.
Each case entry must contain case_id, predictions, target_covered=true, and human_review_required.
Each prediction may contain only vulnerability_class, severity, and human_review_required=true.
Use bounded kebab-case vulnerability classes and Low/Medium/High/Critical severity.
Do not include fixture text, evidence, locations, exploit steps, remediation, or narratives in the response.
Negative controls should have an empty predictions array when no synthetic vulnerability is present.

INPUT:
"""
    prompt = instructions + json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n"
    if len(prompt.encode("utf-8")) > MAX_WORKER_PROMPT_BYTES:
        raise EfficacyBenchmarkError("efficacy worker prompt exceeds the size limit")
    return prompt


def _validate_worker_response(
    lab_root: Path,
    raw: bytes,
    cases: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EfficacyBenchmarkError("efficacy worker response must be strict UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise EfficacyBenchmarkError("efficacy worker response must contain a JSON object")
    try:
        schema = load_schema_object(
            lab_root,
            "templates/reports/efficacy-worker-response.schema.json",
            label="efficacy worker response schema",
        )
        validate_schema_object(value, schema, label="efficacy worker response")
    except EfficacyCorpusError as exc:
        raise EfficacyBenchmarkError("efficacy worker response failed its closed schema contract") from exc
    expected_ids = [case["case_id"] for case in cases]
    response_ids = [item["case_id"] for item in value["cases"]]
    if response_ids != expected_ids or len(response_ids) != len(set(response_ids)):
        raise EfficacyBenchmarkError("efficacy worker response case IDs must exactly match the selected order")
    analyses: dict[str, dict[str, Any]] = {}
    files_by_case = {case["case_id"]: len(case["fixture"]["files"]) for case in cases}
    for item in value["cases"]:
        predictions = item["predictions"]
        if predictions and item["human_review_required"] is not True:
            raise EfficacyBenchmarkError("efficacy worker predictions must require human review")
        analyses[item["case_id"]] = {
            "predictions": predictions,
            "target_covered": item["target_covered"],
            "rule_supported": True,
            "fixture_file_count": files_by_case[item["case_id"]],
            "human_review_required": item["human_review_required"],
        }
    return analyses


def run_worker_configuration(
    lab_root: Path,
    *,
    cases: list[dict[str, Any]],
    fixture_texts: dict[str, dict[str, str]],
    worker_dir: Path,
    profile_id: str,
    model: str | None,
    effort: str | None,
    timeout_seconds: int,
) -> dict[str, Any]:
    if timeout_seconds < 30 or timeout_seconds > 3600:
        raise EfficacyBenchmarkError("--worker-timeout must be between 30 and 3600 seconds")
    try:
        profile = load_profile(lab_root, profile_id)
    except AgentWorkerProfileError as exc:
        raise EfficacyBenchmarkError(str(exc)) from exc
    if (
        profile.id != "codex-cli"
        or profile.profile_status != "builtin"
        or profile.executable != "codex"
        or not profile.supports_exec
    ):
        raise EfficacyBenchmarkError("efficacy worker execution currently requires the built-in codex-cli profile")
    if profile.network_default is not False:
        raise EfficacyBenchmarkError("efficacy worker profile must default sandbox network access to false")
    if "read-only" not in profile.sandbox_modes:
        raise EfficacyBenchmarkError("efficacy worker profile must declare the read-only sandbox")
    availability = check_profile_executable(profile)
    if availability["available"] is not True:
        raise EfficacyBenchmarkError(f"efficacy worker executable is unavailable: {profile.executable}")
    executable = Path(str(availability["resolved_path"])).absolute()
    try:
        executable_metadata = executable.stat()
    except OSError as exc:
        raise EfficacyBenchmarkError("efficacy worker executable became unavailable") from exc
    if not stat.S_ISREG(executable_metadata.st_mode) or not os.access(executable, os.X_OK):
        raise EfficacyBenchmarkError("efficacy worker executable must resolve to an executable file")
    selected_model = model or profile.default_model
    selected_effort = effort or profile.default_effort
    if MODEL_ID_RE.fullmatch(selected_model) is None:
        raise EfficacyBenchmarkError("efficacy worker model ID is invalid")
    if EFFORT_RE.fullmatch(selected_effort) is None:
        raise EfficacyBenchmarkError("efficacy worker effort is invalid")

    base = _worker_base(worker_dir)
    workspace = base / f"run-{uuid.uuid4().hex}"
    workspace.mkdir(mode=0o700)
    worker_env = _worker_environment()
    codex_cli_version = _require_codex_cli_version(executable, workspace, worker_env)
    prompt_path = workspace / "prompt.txt"
    response_schema_path = workspace / "response-schema.json"
    output_last = workspace / "response.json"
    events_path = workspace / "events.jsonl"
    stderr_path = workspace / "stderr.txt"
    prompt_path.write_text(_worker_prompt(cases, fixture_texts), encoding="utf-8")
    try:
        response_schema = load_schema_object(
            lab_root,
            "templates/reports/efficacy-worker-response.schema.json",
            label="efficacy worker response schema",
        )
    except EfficacyCorpusError as exc:
        raise EfficacyBenchmarkError("efficacy worker response schema is invalid") from exc
    response_schema_path.write_text(
        json.dumps(response_schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    args = build_codex_exec_args(
        run_dir=Path("."),
        model=selected_model,
        effort=selected_effort,
        network=False,
        output_last=Path("response.json"),
        approval="never",
        executable=str(executable),
        sandbox="read-only",
        ephemeral=True,
        ignore_user_config=True,
        ignore_rules=True,
        output_schema=Path("response-schema.json"),
    )
    process: subprocess.Popen[str] | None = None
    try:
        with (
            prompt_path.open("r", encoding="utf-8") as stdin,
            events_path.open("x", encoding="utf-8") as stdout,
            stderr_path.open("x", encoding="utf-8") as stderr,
        ):
            process = subprocess.Popen(
                args,
                stdin=stdin,
                stdout=stdout,
                stderr=stderr,
                text=True,
                cwd=workspace,
                env=worker_env,
            )
            returncode, failure = _wait_bounded_process(
                process,
                timeout_seconds=timeout_seconds,
                limits=(
                    (events_path, MAX_WORKER_ARTIFACT_BYTES, "worker events"),
                    (stderr_path, MAX_WORKER_ARTIFACT_BYTES, "worker stderr"),
                    (output_last, MAX_WORKER_RESPONSE_BYTES, "worker response"),
                ),
            )
    except (EfficacyBenchmarkError, KeyboardInterrupt) as exc:
        if process is not None and process.poll() is None:
            process.kill()
            process.wait(timeout=10)
        if isinstance(exc, KeyboardInterrupt):
            raise EfficacyBenchmarkError("efficacy worker execution was interrupted") from exc
        raise
    except (OSError, subprocess.SubprocessError) as exc:
        if process is not None and process.poll() is None:
            process.kill()
            process.wait(timeout=10)
        raise EfficacyBenchmarkError("unable to execute the efficacy worker") from exc
    if failure is not None:
        raise EfficacyBenchmarkError(f"efficacy worker {failure}")
    _bounded_artifact(events_path, maximum=MAX_WORKER_ARTIFACT_BYTES, label="efficacy worker events")
    _bounded_artifact(stderr_path, maximum=MAX_WORKER_ARTIFACT_BYTES, label="efficacy worker stderr")
    if returncode != 0:
        raise EfficacyBenchmarkError(f"efficacy worker exited with status {returncode}")
    raw_response = _bounded_artifact(
        output_last,
        maximum=MAX_WORKER_RESPONSE_BYTES,
        label="efficacy worker response",
    )
    analyses = _validate_worker_response(lab_root, raw_response, cases)
    return {
        "profile_id": profile.id,
        "model_id": selected_model,
        "effort": selected_effort,
        "codex_cli_version": codex_cli_version,
        "analyses": analyses,
        "artifacts_dir": workspace,
        "sandbox_network_enabled": False,
    }
