from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import time
from fnmatch import fnmatchcase
from contextlib import ExitStack, contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence

from gralib import utc_now, write_run_artifact_json
from run_events import reports_dir
from version import auditor_version

SOURCE = "genai-repo-auditor"
SCHEMA_VERSION = "1"
FRESHNESS_FILE = "report-freshness.json"
MAX_RECORDS = 7
MAX_DEPENDENCIES = 128
MAX_OUTPUT_REFS = 4
MAX_REF_LENGTH = 240
MAX_COMMAND_LENGTH = 240
MAX_INPUT_BYTES = 16 * 1024 * 1024
MAX_DISCOVERY_ENTRIES = 512
MAX_DISCOVERY_DIRECTORIES = 128
STATUSES = ("fresh", "stale", "missing_dependency", "not_applicable")
MODES = ("content", "presence")
REQUIREMENTS = ("required", "optional")

_SAFE_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_SAFE_VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.+-]{0,63}$")
_SECRET_REF_RE = re.compile(
    r"(?:ghp_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|glpat-[A-Za-z0-9_-]{20,}|"
    r"sk-[A-Za-z0-9_-]{20,}|xox[baprs]-[A-Za-z0-9-]{20,})"
)
_FORBIDDEN_REF_SEGMENTS = {
    "chain-of-thought",
    "chain_of_thought",
    "private-reasoning",
    "private_reasoning",
    "prompt",
    "prompts",
    "raw-prompt",
    "raw_prompt",
}
_WINDOWS_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


class FreshnessError(ValueError):
    """Raised when freshness metadata or an input path is unsafe or invalid."""


@dataclass(frozen=True)
class ArtifactDefinition:
    artifact_id: str
    output_names: tuple[str, ...]
    producer: str
    artifact_schema: str
    artifact_schema_version: str
    regeneration_command: str


ARTIFACT_CATALOG: dict[str, ArtifactDefinition] = {
    "sarif": ArtifactDefinition(
        "sarif", ("findings.sarif",), "gra-sarif", "sarif", "2.1.0", "gra-sarif --run <run_dir>"
    ),
    "store_import_state": ArtifactDefinition(
        "store_import_state",
        ("store-import-state.json",),
        "gra-store",
        "store-import-state",
        "1",
        "gra-store --run <run_dir> --db <local_db_path>",
    ),
    "issue_publication_plan": ArtifactDefinition(
        "issue_publication_plan",
        ("issue-publication-plan.json",),
        "gra-issues",
        "issue-publication-plan",
        "1",
        "gra-issues --run <run_dir> --plan",
    ),
    "metrics": ArtifactDefinition(
        "metrics", ("metrics.json", "METRICS.md"), "gra-metrics", "metrics", "1", "gra-metrics --run <run_dir>"
    ),
    "benchmark": ArtifactDefinition(
        "benchmark",
        ("benchmark.json", "BENCHMARK.md"),
        "gra-benchmark",
        "benchmark",
        "1",
        "gra-benchmark --run <run_dir>",
    ),
    "evidence_graph": ArtifactDefinition(
        "evidence_graph",
        ("evidence-graph.json", "EVIDENCE_GRAPH.md"),
        "gra-evidence-graph",
        "evidence-graph",
        "1",
        "gra-evidence-graph --run <run_dir>",
    ),
    "dashboard": ArtifactDefinition(
        "dashboard",
        ("dashboard.html",),
        "gra-dashboard",
        "dashboard",
        "1",
        "gra-dashboard --run <run_dir>",
    ),
}

# Peer report dependencies use presence mode to avoid a non-converging digest
# cycle. The final metrics pass observes benchmark/evidence-graph presence, while
# their own records observe metrics presence. Source artifacts remain content
# fingerprinted by producer integrations.
REGENERATION_ORDER = (
    "gra-sarif --run <run_dir>",
    "gra-issues --run <run_dir> --plan",
    "gra-store --run <run_dir> --db <local_db_path>",
    "gra-metrics --run <run_dir>",
    "gra-evidence-graph --run <run_dir>",
    "gra-dashboard --run <run_dir>",
    "gra-benchmark --run <run_dir>",
    "gra-metrics --run <run_dir>",
    "gra-dashboard --run <run_dir>",
)


def dependency(ref: str | Path, *, required: bool = False, mode: str = "content") -> dict[str, str]:
    """Declare one run-relative producer input without reading it yet."""

    return {
        "artifact_ref": _normalize_ref(ref, "dependency.artifact_ref"),
        "requirement": "required" if required else "optional",
        "mode": mode,
    }


def report_ref(run_dir: Path, name: str) -> str:
    """Return a configured reports-directory file as a run-relative reference."""

    report_path = reports_dir(run_dir)
    try:
        relative_dir = report_path.relative_to(run_dir)
    except ValueError as exc:
        raise FreshnessError("configured reports directory must stay under the run directory") from exc
    return _normalize_ref(relative_dir / name, "report_ref")


def expected_output_refs(run_dir: Path, artifact_id: str) -> list[str]:
    definition = _definition(artifact_id)
    if artifact_id == "issue_publication_plan":
        return [_normalize_ref(Path("reports") / name, "output_ref") for name in definition.output_names]
    return [report_ref(run_dir, name) for name in definition.output_names]


def artifact_dependencies(run_dir: Path, artifact_id: str) -> list[dict[str, str]]:
    """Return the closed, producer-specific dependency declaration.

    Dynamic report collections are enumerated deterministically and remain
    subject to the global dependency-count and input-size bounds when recorded.
    """

    run_dir = _validated_run_dir(run_dir)
    report = lambda name, **kwargs: dependency(report_ref(run_dir, name), **kwargs)
    context = dependency("context.json", required=True)
    publication_findings_ref = "reports/findings.json"
    if not (run_dir / publication_findings_ref).exists() and (
        run_dir / "repo" / ".genai-audit" / "reports" / "findings.json"
    ).exists():
        publication_findings_ref = "repo/.genai-audit/reports/findings.json"
    definitions: dict[str, list[dict[str, str]]] = {
        "sarif": [context, report("findings.json", required=True)],
        "store_import_state": [
            context,
            report("targets.json"),
            report("findings.json", required=True),
            report("scanner-results/scanner-index.json"),
            report("issue-ledger.json"),
            dependency("issues-created.json"),
            report("agent-surface.json"),
            report("supply-chain-posture.json"),
            report("provenance-posture.json"),
            report("dependencies.json"),
            dependency("run-manifest.json"),
        ],
        "issue_publication_plan": [
            dependency("context.json"),
            dependency(publication_findings_ref, required=True),
            dependency("reports/chains.json"),
            dependency("reports/proofs.json"),
            dependency("reports/validation.json"),
            dependency("reports/traces.json"),
            dependency("reports/known-findings.json"),
            dependency("reports/remediation/remediation-candidates.json"),
        ],
        "metrics": [
            context,
            report("findings.json", required=True),
            report("targets.json"),
            report("validation.json"),
            report("chains.json"),
            report("proofs.json"),
            report("traces.json"),
            report("gapfill-targets.json"),
            report("COVERAGE.md", mode="presence"),
            report("issue-publication-plan.json"),
            report("issue-ledger.json"),
            report("workflow-profile.json"),
            report("workflow-execution.json"),
            report("evidence-graph.json", mode="presence"),
            report("benchmark.json", mode="presence"),
            report("scanner-results/scanner-index.json"),
            report("scanner-runs.json"),
            report("command-events.jsonl", mode="presence"),
            report("taxonomy-normalizations.jsonl"),
            dependency("run-manifest.json"),
        ],
        "benchmark": [
            context,
            report("metrics.json", mode="presence"),
            report("findings.json", required=True),
            report("proofs.json"),
            report("issue-ledger.json"),
            report("issues-created.json"),
            report("evidence-graph.json", mode="presence"),
            report("dashboard.html", mode="presence"),
            report("findings.sarif", mode="presence"),
            report("command-events.jsonl", mode="presence"),
        ],
        "evidence_graph": [
            context,
            report("findings.json", required=True),
            report("targets.json"),
            report("scanner-results/scanner-index.json"),
            report("scanner-runs.json"),
            report("chains.json"),
            report("proofs.json"),
            report("validation.json"),
            report("traces.json"),
            report("remediation/remediation-candidates.json"),
            report("issue-publication-plan.json"),
            report("metrics.json", mode="presence"),
            report("workflow-profile.json"),
            report("workflow-execution.json"),
        ],
        "dashboard": [
            context,
            report("findings.json", required=True),
            report("targets.json"),
            report("scanner-results/scanner-index.json"),
            report("supply-chain-posture.json"),
            report("dependencies.json"),
            report("metrics.json"),
            report("benchmark.json"),
            report("evidence-graph.json"),
            report("gapfill-targets.json"),
            report("remediation/remediation-candidates.json"),
            report("imported-findings.json"),
            report("known-findings.json"),
        ],
    }
    _definition(artifact_id)
    declared = list(definitions[artifact_id])
    if artifact_id == "metrics":
        declared.extend(_dynamic_report_dependencies(run_dir, "scanner-readiness", "*.json"))
        declared.extend(_dynamic_report_dependencies(run_dir, "duplicate-decisions", "*.json"))
    elif artifact_id == "benchmark":
        declared.extend(_benchmark_report_dependencies(run_dir))
        declared.extend(_dynamic_report_dependencies(run_dir, "remediation", "**/patch-validation.json"))
    elif artifact_id in {"evidence_graph", "issue_publication_plan"}:
        if artifact_id == "issue_publication_plan":
            declared.extend(_dynamic_run_dependencies(run_dir, "reports/remediation", "**/patch-validation.json"))
        else:
            declared.extend(_dynamic_report_dependencies(run_dir, "remediation", "**/patch-validation.json"))
        if artifact_id == "issue_publication_plan":
            declared.extend(_dynamic_run_dependencies(run_dir, "reports/issue-drafts", "*.md"))
    return _deduplicate_declarations(declared)


def public_summary(summary: Mapping[str, Any]) -> dict[str, Any]:
    """Copy only the bounded display contract from an assessed summary."""

    if not isinstance(summary, Mapping) or set(summary) != {
        "overall_status",
        "counts",
        "artifacts",
        "regeneration_order",
    }:
        raise FreshnessError("freshness summary has unsupported fields")
    if summary.get("overall_status") not in STATUSES or not isinstance(summary.get("counts"), Mapping):
        raise FreshnessError("freshness summary has an invalid status contract")
    if set(summary["counts"]) != set(STATUSES):
        raise FreshnessError("freshness summary counts must contain exactly the supported statuses")
    counts: dict[str, int] = {}
    for status in STATUSES:
        count = summary["counts"].get(status)
        if not isinstance(count, int) or isinstance(count, bool) or not 0 <= count <= MAX_RECORDS:
            raise FreshnessError("freshness summary count must be a bounded non-negative integer")
        counts[status] = count
    artifacts_raw = summary.get("artifacts")
    if not isinstance(artifacts_raw, list) or len(artifacts_raw) > MAX_RECORDS:
        raise FreshnessError("freshness summary has an invalid artifact list")
    artifacts: list[dict[str, Any]] = []
    if len(artifacts_raw) != len(ARTIFACT_CATALOG):
        raise FreshnessError("freshness summary must cover the closed artifact catalog")
    for expected_id, item in zip(ARTIFACT_CATALOG, artifacts_raw):
        if not isinstance(item, Mapping) or set(item) != {
            "artifact_id",
            "output_refs",
            "status",
            "producer",
            "regeneration_command",
            "stale_dependency_refs",
            "missing_dependency_refs",
        }:
            raise FreshnessError("freshness summary artifact must be an object")
        definition = _definition(item.get("artifact_id"))
        if definition.artifact_id != expected_id:
            raise FreshnessError("freshness summary artifacts must use catalog order")
        status = item.get("status")
        if status not in STATUSES:
            raise FreshnessError("freshness summary artifact has an invalid status")
        artifacts.append(
            {
                "artifact_id": definition.artifact_id,
                "status": status,
                "producer": definition.producer,
                "regeneration_command": definition.regeneration_command,
            }
        )
    if summary.get("regeneration_order") != list(REGENERATION_ORDER):
        raise FreshnessError("freshness summary has an unsupported regeneration order")
    result = {
        "overall_status": summary["overall_status"],
        "counts": counts,
        "artifacts": artifacts,
        "regeneration_order": list(REGENERATION_ORDER),
    }
    if sum(counts.values()) != len(artifacts):
        raise FreshnessError("freshness summary counts do not match artifact statuses")
    return validate_public_summary(result)


def validate_public_summary(value: Any) -> dict[str, Any]:
    """Validate an embedded freshness summary without reading report inputs."""

    if not isinstance(value, dict) or set(value) != {
        "overall_status",
        "counts",
        "artifacts",
        "regeneration_order",
    }:
        raise FreshnessError("embedded freshness summary has unsupported fields")
    if value.get("overall_status") not in STATUSES:
        raise FreshnessError("embedded freshness summary has an invalid overall status")
    counts = value.get("counts")
    if not isinstance(counts, dict) or set(counts) != set(STATUSES):
        raise FreshnessError("embedded freshness counts have an invalid status contract")
    if any(
        not isinstance(count, int) or isinstance(count, bool) or not 0 <= count <= MAX_RECORDS
        for count in counts.values()
    ):
        raise FreshnessError("embedded freshness counts must be bounded non-negative integers")
    artifacts = value.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != len(ARTIFACT_CATALOG):
        raise FreshnessError("embedded freshness artifacts must cover the closed catalog")
    for expected_id, item in zip(ARTIFACT_CATALOG, artifacts):
        if not isinstance(item, dict) or set(item) != {
            "artifact_id",
            "status",
            "producer",
            "regeneration_command",
        }:
            raise FreshnessError("embedded freshness artifact has unsupported fields")
        definition = _definition(item.get("artifact_id"))
        if definition.artifact_id != expected_id:
            raise FreshnessError("embedded freshness artifacts must use catalog order")
        if item.get("status") not in STATUSES:
            raise FreshnessError("embedded freshness artifact has an invalid status")
        if item.get("producer") != definition.producer:
            raise FreshnessError("embedded freshness producer does not match the closed catalog")
        if item.get("regeneration_command") != definition.regeneration_command:
            raise FreshnessError("embedded freshness command does not match the closed catalog")
    if value.get("regeneration_order") != list(REGENERATION_ORDER):
        raise FreshnessError("embedded freshness regeneration order does not match the closed catalog")
    if sum(counts.values()) != len(artifacts):
        raise FreshnessError("embedded freshness counts do not match artifact statuses")
    actual_counts = {status: 0 for status in STATUSES}
    for item in artifacts:
        actual_counts[item["status"]] += 1
    if counts != actual_counts:
        raise FreshnessError("embedded freshness counts do not match artifact status values")
    if counts["missing_dependency"]:
        expected_overall = "missing_dependency"
    elif counts["stale"]:
        expected_overall = "stale"
    elif counts["fresh"]:
        expected_overall = "fresh"
    else:
        expected_overall = "not_applicable"
    if value["overall_status"] != expected_overall:
        raise FreshnessError("embedded freshness overall status does not match artifact status values")
    return json.loads(json.dumps(value))


def freshness_path(run_dir: Path) -> Path:
    return reports_dir(run_dir) / FRESHNESS_FILE


def initialize_freshness(run_dir: Path) -> None:
    """Create an empty sidecar before a producer enumerates report files."""

    run_dir = _validated_run_dir(run_dir)
    path = freshness_path(run_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _sidecar_lock(path):
        if load_freshness(run_dir) is not None:
            return
        data = {
            "schema_version": SCHEMA_VERSION,
            "generated_at": utc_now(),
            "source": SOURCE,
            "records": [],
        }
        _validate_sidecar(run_dir, data)
        write_run_artifact_json(run_dir, path, data)


def record_artifact(
    run_dir: Path,
    artifact_id: str,
    dependencies: Iterable[Mapping[str, Any]],
    *,
    producer_version: str | None = None,
) -> dict[str, Any]:
    """Capture bounded dependency state for one derived report.

    Required dependencies and every declared output must exist as regular,
    non-symlink files. Optional dependencies record an explicit absent state.
    The sidecar update is serialized so concurrent report producers do not lose
    one another's records.
    """

    run_dir = _validated_run_dir(run_dir)
    definition = _definition(artifact_id)
    supplied = [dict(item) for item in dependencies]
    captured_flags = ["captured_state" in item for item in supplied]
    if any(captured_flags) and not all(captured_flags):
        raise FreshnessError("record.dependencies: declarations and captured snapshots must not be mixed")
    if captured_flags and all(captured_flags):
        captured = _validate_preflight_snapshot(run_dir, artifact_id, supplied)
    else:
        captured = preflight_artifact_dependencies(run_dir, artifact_id, supplied)

    output_refs = expected_output_refs(run_dir, artifact_id)
    for ref in output_refs:
        state = _current_state(run_dir, ref, mode="presence")
        if state["captured_state"] != "present":
            raise FreshnessError(f"record.output_refs: required output is missing: {ref}")

    record = {
        "artifact_id": definition.artifact_id,
        "output_refs": output_refs,
        "producer": definition.producer,
        "producer_version": producer_version or auditor_version(),
        "artifact_schema": definition.artifact_schema,
        "artifact_schema_version": definition.artifact_schema_version,
        "dependencies": captured,
        "regeneration_command": definition.regeneration_command,
    }
    _validate_record(run_dir, record, "record")
    _update_sidecar(run_dir, record)
    return record


def preflight_artifact_dependencies(
    run_dir: Path,
    artifact_id: str,
    dependencies: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Validate producer declarations and current inputs before output mutation."""

    run_dir = _validated_run_dir(run_dir)
    _definition(artifact_id)
    declared = [dict(item) for item in dependencies]
    if len(declared) > MAX_DEPENDENCIES:
        raise FreshnessError(f"record.dependencies: exceeds {MAX_DEPENDENCIES} entries")
    output_refs = expected_output_refs(run_dir, artifact_id)
    normalized_values: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(declared):
        normalized = _normalize_dependency_declaration(item, f"record.dependencies[{index}]")
        ref = normalized["artifact_ref"]
        if ref in seen:
            raise FreshnessError("record.dependencies: duplicate artifact_ref")
        if any(_refs_overlap(ref, existing) for existing in seen):
            raise FreshnessError("record.dependencies: dependency references must not overlap")
        if any(_refs_overlap(ref, output_ref) for output_ref in output_refs):
            raise FreshnessError("record.dependencies: dependency and output references must not overlap")
        state = _current_state(run_dir, ref, mode=normalized["mode"])
        if normalized["requirement"] == "required" and state["captured_state"] != "present":
            raise FreshnessError(f"record.dependencies: required dependency is missing: {ref}")
        seen.add(ref)
        normalized_values.append({**normalized, **state})
    return normalized_values


def _validate_preflight_snapshot(
    run_dir: Path,
    artifact_id: str,
    supplied: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    if len(supplied) > MAX_DEPENDENCIES:
        raise FreshnessError(f"record.dependencies: exceeds {MAX_DEPENDENCIES} entries")
    output_refs = expected_output_refs(run_dir, artifact_id)
    captured: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(supplied):
        normalized = _validate_captured_dependency(dict(item), f"record.dependencies[{index}]")
        ref = normalized["artifact_ref"]
        if ref in seen:
            raise FreshnessError("record.dependencies: duplicate artifact_ref")
        if any(_refs_overlap(ref, existing) for existing in seen):
            raise FreshnessError("record.dependencies: dependency references must not overlap")
        if any(_refs_overlap(ref, output_ref) for output_ref in output_refs):
            raise FreshnessError("record.dependencies: dependency and output references must not overlap")
        if normalized["requirement"] == "required" and normalized["captured_state"] != "present":
            raise FreshnessError(f"record.dependencies: required dependency is missing: {ref}")
        current = _current_state(run_dir, ref, mode=normalized["mode"])
        expected_state = {key: item[key] for key in ("captured_state", "size_bytes", "sha256") if key in item}
        if current != expected_state:
            raise FreshnessError(f"record.dependencies: dependency changed during report generation: {ref}")
        seen.add(ref)
        captured.append(dict(item))
    return captured


def load_freshness(run_dir: Path) -> dict[str, Any] | None:
    """Load and validate the sidecar; legacy runs without one return ``None``."""

    run_dir = _validated_run_dir(run_dir)
    path = freshness_path(run_dir)
    raw = _read_bounded_file(run_dir, _relative_ref(run_dir, path), allow_missing=True)
    if raw is None:
        return None
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FreshnessError("report freshness sidecar must be valid UTF-8 JSON") from exc
    _validate_sidecar(run_dir, data)
    return data


def load_bounded_json_artifact(
    run_dir: Path,
    ref: str | Path,
    *,
    max_bytes: int = MAX_INPUT_BYTES,
) -> Any:
    """Load one run-relative JSON artifact through the no-follow bounded reader."""

    run_dir = _validated_run_dir(run_dir)
    if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or not 1 <= max_bytes <= MAX_INPUT_BYTES:
        raise FreshnessError("bounded JSON limit must be a positive supported integer")
    normalized = _normalize_ref(ref, "artifact_ref")
    raw = _read_bounded_file(run_dir, normalized, allow_missing=False, max_bytes=max_bytes)
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FreshnessError("run artifact must be valid bounded UTF-8 JSON") from exc


def assess_freshness(run_dir: Path) -> dict[str, Any]:
    """Return bounded current status for every catalogued report."""

    run_dir = _validated_run_dir(run_dir)
    data = load_freshness(run_dir)
    records = {item["artifact_id"]: item for item in (data or {}).get("records", [])}
    artifacts: list[dict[str, Any]] = []

    for artifact_id, definition in ARTIFACT_CATALOG.items():
        record = records.get(artifact_id)
        if record is None:
            artifacts.append(
                {
                    "artifact_id": artifact_id,
                    "output_refs": expected_output_refs(run_dir, artifact_id),
                    "status": "not_applicable",
                    "producer": definition.producer,
                    "regeneration_command": definition.regeneration_command,
                    "stale_dependency_refs": [],
                    "missing_dependency_refs": [],
                }
            )
            continue
        artifacts.append(_assess_record(run_dir, record))

    counts = {status: 0 for status in STATUSES}
    for artifact in artifacts:
        counts[artifact["status"]] += 1
    if counts["missing_dependency"]:
        overall = "missing_dependency"
    elif counts["stale"]:
        overall = "stale"
    elif counts["fresh"]:
        overall = "fresh"
    else:
        overall = "not_applicable"
    return {
        "overall_status": overall,
        "counts": counts,
        "artifacts": artifacts,
        "regeneration_order": list(REGENERATION_ORDER),
    }


def stale_or_missing(summary: Mapping[str, Any]) -> list[dict[str, Any]]:
    artifacts = summary.get("artifacts")
    if not isinstance(artifacts, list):
        raise FreshnessError("freshness summary artifacts must be a list")
    return [
        dict(item)
        for item in artifacts
        if isinstance(item, Mapping) and item.get("status") in {"stale", "missing_dependency"}
    ]


def _assess_record(run_dir: Path, record: Mapping[str, Any]) -> dict[str, Any]:
    stale_refs: list[str] = []
    missing_refs: list[str] = []
    for ref in record["output_refs"]:
        state = _current_state(run_dir, ref, mode="presence")
        if state["captured_state"] != "present":
            missing_refs.append(ref)

    for item in record["dependencies"]:
        ref = item["artifact_ref"]
        current = _current_state(run_dir, ref, mode=item["mode"])
        captured_state = item["captured_state"]
        current_state = current["captured_state"]
        if current_state == "absent":
            if captured_state == "present":
                missing_refs.append(ref)
            elif item["requirement"] == "required":
                missing_refs.append(ref)
            continue
        if captured_state == "absent":
            stale_refs.append(ref)
        elif item["mode"] == "content" and (
            current.get("sha256") != item.get("sha256") or current.get("size_bytes") != item.get("size_bytes")
        ):
            stale_refs.append(ref)

    if missing_refs:
        status = "missing_dependency"
    elif stale_refs:
        status = "stale"
    else:
        status = "fresh"
    return {
        "artifact_id": record["artifact_id"],
        "output_refs": list(record["output_refs"]),
        "status": status,
        "producer": record["producer"],
        "regeneration_command": record["regeneration_command"],
        "stale_dependency_refs": stale_refs,
        "missing_dependency_refs": missing_refs,
    }


def _update_sidecar(run_dir: Path, record: Mapping[str, Any]) -> None:
    path = freshness_path(run_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _sidecar_lock(path):
        current = load_freshness(run_dir)
        records = {item["artifact_id"]: item for item in (current or {}).get("records", [])}
        records[str(record["artifact_id"])] = dict(record)
        ordered = [records[key] for key in ARTIFACT_CATALOG if key in records]
        data = {
            "schema_version": SCHEMA_VERSION,
            "generated_at": utc_now(),
            "source": SOURCE,
            "records": ordered,
        }
        _validate_sidecar(run_dir, data)
        write_run_artifact_json(run_dir, path, data)


@contextmanager
def _sidecar_lock(path: Path, *, timeout_seconds: float = 10.0):
    lock_path = path.with_name(f".{path.name}.lock")
    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            os.mkdir(lock_path, 0o700)
            break
        except FileExistsError as exc:
            if time.monotonic() >= deadline:
                raise FreshnessError("timed out waiting for report freshness update lock") from exc
            time.sleep(0.01)
    try:
        yield
    finally:
        with suppress(FileNotFoundError):
            os.rmdir(lock_path)


def _validate_sidecar(run_dir: Path, data: Any) -> None:
    if not isinstance(data, dict) or set(data) != {"schema_version", "generated_at", "source", "records"}:
        raise FreshnessError("report freshness sidecar has unsupported fields")
    if data.get("schema_version") != SCHEMA_VERSION or data.get("source") != SOURCE:
        raise FreshnessError("report freshness sidecar has an unsupported contract version or source")
    if not isinstance(data.get("generated_at"), str) or not data["generated_at"] or len(data["generated_at"]) > 64:
        raise FreshnessError("report freshness generated_at must be a bounded string")
    records = data.get("records")
    if not isinstance(records, list) or len(records) > MAX_RECORDS:
        raise FreshnessError(f"report freshness records must contain at most {MAX_RECORDS} entries")
    seen: set[str] = set()
    catalog_order = list(ARTIFACT_CATALOG)
    previous_index = -1
    for index, record in enumerate(records):
        _validate_record(run_dir, record, f"records[{index}]")
        artifact_id = record["artifact_id"]
        if artifact_id in seen:
            raise FreshnessError("report freshness records contain a duplicate artifact_id")
        seen.add(artifact_id)
        order_index = catalog_order.index(artifact_id)
        if order_index <= previous_index:
            raise FreshnessError("report freshness records must use catalog order")
        previous_index = order_index


def _validate_record(run_dir: Path, record: Any, field: str) -> None:
    keys = {
        "artifact_id",
        "output_refs",
        "producer",
        "producer_version",
        "artifact_schema",
        "artifact_schema_version",
        "dependencies",
        "regeneration_command",
    }
    if not isinstance(record, dict) or set(record) != keys:
        raise FreshnessError(f"{field}: record has unsupported fields")
    artifact_id = record.get("artifact_id")
    definition = _definition(artifact_id)
    if record.get("producer") != definition.producer:
        raise FreshnessError(f"{field}.producer: does not match the closed catalog")
    if record.get("artifact_schema") != definition.artifact_schema:
        raise FreshnessError(f"{field}.artifact_schema: does not match the closed catalog")
    if record.get("artifact_schema_version") != definition.artifact_schema_version:
        raise FreshnessError(f"{field}.artifact_schema_version: does not match the closed catalog")
    if record.get("regeneration_command") != definition.regeneration_command:
        raise FreshnessError(f"{field}.regeneration_command: does not match the closed catalog")
    version = record.get("producer_version")
    if not isinstance(version, str) or not _SAFE_VERSION_RE.fullmatch(version):
        raise FreshnessError(f"{field}.producer_version: invalid bounded version")
    output_refs = record.get("output_refs")
    if not isinstance(output_refs, list) or not output_refs or len(output_refs) > MAX_OUTPUT_REFS:
        raise FreshnessError(f"{field}.output_refs: invalid bounded list")
    normalized_outputs = [_normalize_ref(ref, f"{field}.output_refs") for ref in output_refs]
    if normalized_outputs != expected_output_refs(run_dir, artifact_id):
        raise FreshnessError(f"{field}.output_refs: do not match the closed catalog")
    if len(set(normalized_outputs)) != len(normalized_outputs):
        raise FreshnessError(f"{field}.output_refs: duplicate reference")
    dependencies = record.get("dependencies")
    if not isinstance(dependencies, list) or len(dependencies) > MAX_DEPENDENCIES:
        raise FreshnessError(f"{field}.dependencies: invalid bounded list")
    seen: set[str] = set()
    for index, item in enumerate(dependencies):
        dep_field = f"{field}.dependencies[{index}]"
        normalized = _validate_captured_dependency(item, dep_field)
        ref = normalized["artifact_ref"]
        if normalized["requirement"] == "required" and normalized["captured_state"] != "present":
            raise FreshnessError(f"{dep_field}: required dependency cannot have an absent captured state")
        if ref in seen:
            raise FreshnessError(f"{field}.dependencies: duplicate artifact_ref")
        if any(_refs_overlap(ref, existing) for existing in seen):
            raise FreshnessError(f"{field}.dependencies: dependency references overlap")
        seen.add(ref)
        if any(_refs_overlap(ref, output_ref) for output_ref in normalized_outputs):
            raise FreshnessError(f"{field}.dependencies: dependency and output references overlap")
        _validate_ref_path(run_dir, ref, allow_missing=True)


def _normalize_dependency_declaration(item: Mapping[str, Any], field: str) -> dict[str, str]:
    if not isinstance(item, Mapping) or set(item) != {"artifact_ref", "requirement", "mode"}:
        raise FreshnessError(f"{field}: dependency declaration has unsupported fields")
    ref = _normalize_ref(item.get("artifact_ref"), f"{field}.artifact_ref")
    requirement = item.get("requirement")
    mode = item.get("mode")
    if requirement not in REQUIREMENTS or mode not in MODES:
        raise FreshnessError(f"{field}: invalid requirement or mode")
    return {"artifact_ref": ref, "requirement": requirement, "mode": mode}


def _validate_captured_dependency(item: Any, field: str) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise FreshnessError(f"{field}: dependency must be an object")
    base = _normalize_dependency_declaration(
        {key: item.get(key) for key in ("artifact_ref", "requirement", "mode")}, field
    )
    captured_state = item.get("captured_state")
    if captured_state not in {"present", "absent"}:
        raise FreshnessError(f"{field}.captured_state: invalid state")
    expected_keys = {"artifact_ref", "requirement", "mode", "captured_state"}
    if captured_state == "present" and base["mode"] == "content":
        expected_keys.update({"size_bytes", "sha256"})
        size = item.get("size_bytes")
        digest = item.get("sha256")
        if not isinstance(size, int) or isinstance(size, bool) or not 0 <= size <= MAX_INPUT_BYTES:
            raise FreshnessError(f"{field}.size_bytes: invalid bounded size")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise FreshnessError(f"{field}.sha256: invalid digest")
    if set(item) != expected_keys:
        raise FreshnessError(f"{field}: captured dependency has unsupported fields")
    return {**base, "captured_state": captured_state}


def _current_state(run_dir: Path, ref: str, *, mode: str) -> dict[str, Any]:
    if mode not in MODES:
        raise FreshnessError("dependency mode is unsupported")
    if mode == "presence":
        fd = _open_ref_fd(run_dir, ref, allow_missing=True)
        if fd is None:
            return {"captured_state": "absent"}
        os.close(fd)
        return {"captured_state": "present"}
    payload = _read_bounded_file(run_dir, ref, allow_missing=True)
    if payload is None:
        return {"captured_state": "absent"}
    return {
        "captured_state": "present",
        "size_bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def _dynamic_report_dependencies(
    run_dir: Path,
    directory_name: str,
    pattern: str,
) -> list[dict[str, str]]:
    return _dynamic_run_dependencies(run_dir, report_ref(run_dir, directory_name), pattern)


def _dynamic_run_dependencies(
    run_dir: Path,
    root_ref: str,
    pattern: str,
) -> list[dict[str, str]]:
    root_ref = _normalize_ref(root_ref, "dynamic_dependency_root")
    root = run_dir / PurePosixPath(root_ref)
    if root.is_symlink():
        raise FreshnessError(f"dynamic dependency directory must not be a symlink: {root_ref}")
    if not root.exists():
        return []
    if not root.is_dir():
        raise FreshnessError(f"dynamic dependency root must be a directory: {root_ref}")
    if pattern == "*.json" or pattern == "*.md":
        paths = [path for path in _bounded_tree_entries(root, recursive=False) if fnmatchcase(path.name, pattern)]
    elif pattern == "**/patch-validation.json":
        paths = [
            path
            for path in _bounded_tree_entries(root, recursive=True)
            if path.name == "patch-validation.json"
        ]
    else:
        raise FreshnessError("dynamic dependency pattern is not part of the closed catalog")
    if len(paths) > MAX_DEPENDENCIES:
        raise FreshnessError(f"dynamic dependency collection exceeds {MAX_DEPENDENCIES} entries")
    result: list[dict[str, str]] = []
    for path in sorted(paths, key=lambda item: item.as_posix()):
        ref = _relative_ref(run_dir, path)
        # The capture step emits the definitive regular-file/symlink diagnostic.
        result.append(dependency(ref))
    return result


def _benchmark_report_dependencies(run_dir: Path) -> list[dict[str, str]]:
    """Declare files consumed by benchmark's bounded all-report secret scan."""

    root = reports_dir(run_dir)
    if root.is_symlink() or not root.is_dir():
        raise FreshnessError("benchmark report dependency root must be a non-symlink directory")
    peer_refs = {
        report_ref(run_dir, name)
        for name in (
            FRESHNESS_FILE,
            "metrics.json",
            "METRICS.md",
            "evidence-graph.json",
            "EVIDENCE_GRAPH.md",
            "dashboard.html",
            "findings.sarif",
            "store-import-state.json",
            "issue-publication-plan.json",
            "command-events.jsonl",
        )
    }
    own_refs = set(expected_output_refs(run_dir, "benchmark"))
    result: list[dict[str, str]] = []
    for path in sorted(_bounded_tree_entries(root, recursive=True), key=lambda item: item.as_posix()):
        try:
            path_info = path.stat(follow_symlinks=False)
        except OSError as exc:
            raise FreshnessError("unable to inspect benchmark report dependency") from exc
        if stat.S_ISLNK(path_info.st_mode) or not stat.S_ISREG(path_info.st_mode):
            continue
        ref = _relative_ref(run_dir, path)
        if ref in own_refs:
            continue
        # Peer outputs and append-only events use presence identity to avoid
        # digest cycles. Benchmark skips report files above 2 MiB during its
        # secret-pattern scan, so only their presence affects its output.
        large = path_info.st_size > 2 * 1024 * 1024
        mode = "presence" if ref in peer_refs or large else "content"
        result.append(dependency(ref, mode=mode))
        if len(result) > MAX_DEPENDENCIES:
            raise FreshnessError(f"benchmark report dependency collection exceeds {MAX_DEPENDENCIES} entries")
    return result


def _bounded_tree_entries(root: Path, *, recursive: bool) -> list[Path]:
    """Discover a bounded file-tree snapshot before deterministic sorting.

    Every directory entry counts toward the limit, including unrelated files,
    directories, and symlinks. Directory symlinks are never followed.
    """

    pending = [root]
    discovered: list[Path] = []
    entry_count = 0
    directory_count = 1
    while pending:
        directory = pending.pop()
        try:
            with os.scandir(directory) as iterator:
                entries: list[os.DirEntry[str]] = []
                for entry in iterator:
                    entry_count += 1
                    if entry_count > MAX_DISCOVERY_ENTRIES:
                        raise FreshnessError(
                            f"dynamic report discovery exceeds {MAX_DISCOVERY_ENTRIES} entries"
                        )
                    entries.append(entry)
        except OSError as exc:
            raise FreshnessError("unable to enumerate dynamic report dependencies safely") from exc
        for entry in entries:
            path = Path(entry.path)
            try:
                is_directory = entry.is_dir(follow_symlinks=False)
            except OSError as exc:
                raise FreshnessError("unable to inspect dynamic report dependency") from exc
            discovered.append(path)
            if is_directory:
                if recursive:
                    directory_count += 1
                    if directory_count > MAX_DISCOVERY_DIRECTORIES:
                        raise FreshnessError(
                            f"dynamic report discovery exceeds {MAX_DISCOVERY_DIRECTORIES} directories"
                        )
                    pending.append(path)
                continue
    return discovered


def _deduplicate_declarations(values: Sequence[Mapping[str, str]]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for value in values:
        ref = str(value["artifact_ref"])
        if ref in seen:
            continue
        seen.add(ref)
        result.append(dict(value))
    if len(result) > MAX_DEPENDENCIES:
        raise FreshnessError(f"artifact dependency declaration exceeds {MAX_DEPENDENCIES} entries")
    return result


def _read_bounded_file(
    run_dir: Path,
    ref: str,
    *,
    allow_missing: bool,
    max_bytes: int = MAX_INPUT_BYTES,
) -> bytes | None:
    fd = _open_ref_fd(run_dir, ref, allow_missing=allow_missing)
    if fd is None:
        return None
    try:
        info_before = os.fstat(fd)
        if not stat.S_ISREG(info_before.st_mode):
            raise FreshnessError("report dependency must be a regular file")
        if info_before.st_size > max_bytes:
            raise FreshnessError(f"report dependency exceeds {max_bytes} bytes")
        chunks: list[bytes] = []
        remaining = max_bytes + 1
        while remaining:
            chunk = os.read(fd, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        if len(payload) > max_bytes:
            raise FreshnessError(f"report dependency exceeds {max_bytes} bytes")
        info_after = os.fstat(fd)
        identity_before = (
            info_before.st_dev,
            info_before.st_ino,
            info_before.st_size,
            info_before.st_mtime_ns,
        )
        identity_after = (
            info_after.st_dev,
            info_after.st_ino,
            info_after.st_size,
            info_after.st_mtime_ns,
        )
        if identity_before != identity_after:
            raise FreshnessError("report dependency changed while its fingerprint was captured")
        return payload
    finally:
        os.close(fd)


def _validate_ref_path(run_dir: Path, ref: str, *, allow_missing: bool) -> Path | None:
    normalized = _normalize_ref(ref, "artifact_ref")
    fd = _open_ref_fd(run_dir, normalized, allow_missing=allow_missing)
    if fd is None:
        return None
    os.close(fd)
    return run_dir / PurePosixPath(normalized)


def _open_ref_fd(run_dir: Path, ref: str, *, allow_missing: bool) -> int | None:
    """Open a regular input without following leaf or parent symlinks.

    POSIX platforms use an identity-pinned ``dir_fd`` walk. Platforms without
    ``dir_fd`` support retain the explicit lstat component checks before an
    ``O_NOFOLLOW`` leaf open.
    """

    normalized = _normalize_ref(ref, "artifact_ref")
    parts = PurePosixPath(normalized).parts
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    leaf_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    if os.open in getattr(os, "supports_dir_fd", set()) and getattr(os, "O_DIRECTORY", 0):
        with ExitStack() as stack:
            root_fd = os.open(run_dir, directory_flags)
            stack.callback(os.close, root_fd)
            parent_fd = root_fd
            for part in parts[:-1]:
                try:
                    next_fd = os.open(part, directory_flags, dir_fd=parent_fd)
                    stack.callback(os.close, next_fd)
                except FileNotFoundError:
                    if allow_missing:
                        return None
                    raise FreshnessError("required report dependency is missing")
                except OSError as exc:
                    raise FreshnessError(f"artifact_ref must not traverse a symlink or non-directory: {normalized}") from exc
                parent_fd = next_fd
            try:
                fd = os.open(parts[-1], leaf_flags, dir_fd=parent_fd)
            except FileNotFoundError:
                if allow_missing:
                    return None
                raise FreshnessError("required report dependency is missing")
            except OSError as exc:
                raise FreshnessError(f"artifact_ref must identify a regular non-symlink file: {normalized}") from exc
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                os.close(fd)
                raise FreshnessError(f"artifact_ref must identify a regular file: {normalized}")
            return fd

    # Cross-platform fallback for runtimes without openat/dir_fd support.
    current = run_dir
    for index, part in enumerate(parts):
        current = current / part
        try:
            info = current.lstat()
            mode = info.st_mode
        except FileNotFoundError:
            if allow_missing:
                return None
            raise FreshnessError("required report dependency is missing")
        if stat.S_ISLNK(mode) or getattr(info, "st_file_attributes", 0) & _WINDOWS_REPARSE_POINT:
            raise FreshnessError(f"artifact_ref must not traverse a symlink: {normalized}")
        if index < len(parts) - 1 and not stat.S_ISDIR(mode):
            raise FreshnessError(f"artifact_ref parent must be a directory: {normalized}")
        if index == len(parts) - 1 and not stat.S_ISREG(mode):
            raise FreshnessError(f"artifact_ref must identify a regular file: {normalized}")
    try:
        fd = os.open(current, leaf_flags)
    except FileNotFoundError:
        if allow_missing:
            return None
        raise FreshnessError("required report dependency is missing")
    except OSError as exc:
        raise FreshnessError(f"artifact_ref must identify a regular non-symlink file: {normalized}") from exc
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        raise FreshnessError(f"artifact_ref must identify a regular file: {normalized}")
    return fd


def _normalize_ref(value: Any, field: str) -> str:
    if isinstance(value, Path):
        value = value.as_posix()
    if not isinstance(value, str) or not value or len(value) > MAX_REF_LENGTH:
        raise FreshnessError(f"{field}: must be a non-empty bounded string")
    if (
        "\\" in value
        or value.startswith("/")
        or "//" in value
        or re.match(r"^[A-Za-z]:", value)
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise FreshnessError(f"{field}: must be a normalized run-relative POSIX path")
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise FreshnessError(f"{field}: must be a normalized run-relative POSIX path")
    normalized = path.as_posix()
    if normalized != value:
        raise FreshnessError(f"{field}: must use canonical path spelling")
    if _SECRET_REF_RE.search(normalized):
        raise FreshnessError(f"{field}: secret-like values are not allowed in artifact references")
    if any(part.lower() in _FORBIDDEN_REF_SEGMENTS for part in path.parts):
        raise FreshnessError(f"{field}: prompt or private-reasoning references are not allowed")
    return normalized


def _relative_ref(run_dir: Path, path: Path) -> str:
    try:
        return _normalize_ref(path.relative_to(run_dir).as_posix(), "artifact_ref")
    except ValueError as exc:
        raise FreshnessError("artifact path must stay under the run directory") from exc


def _refs_overlap(left: str, right: str) -> bool:
    left_parts = PurePosixPath(left).parts
    right_parts = PurePosixPath(right).parts
    shortest = min(len(left_parts), len(right_parts))
    return left_parts[:shortest] == right_parts[:shortest]


def _definition(artifact_id: Any) -> ArtifactDefinition:
    if not isinstance(artifact_id, str) or not _SAFE_ID_RE.fullmatch(artifact_id):
        raise FreshnessError("artifact_id is invalid")
    try:
        return ARTIFACT_CATALOG[artifact_id]
    except KeyError as exc:
        raise FreshnessError("artifact_id is not part of the closed catalog") from exc


def _validated_run_dir(run_dir: Path) -> Path:
    run_dir = Path(run_dir)
    try:
        info = run_dir.lstat()
        mode = info.st_mode
    except FileNotFoundError as exc:
        raise FreshnessError("run directory does not exist") from exc
    if (
        stat.S_ISLNK(mode)
        or getattr(info, "st_file_attributes", 0) & _WINDOWS_REPARSE_POINT
        or not stat.S_ISDIR(mode)
    ):
        raise FreshnessError("run directory must be a non-symlink directory")
    return run_dir
