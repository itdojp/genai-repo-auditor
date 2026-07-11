from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from typing import Any

from gralib import load_context, load_json, utc_now, write_json
from scanner_reporting import ScannerReportError, validate_scanner_runs_for_run
from workflow_profile import summarize_workflow_profile

NODE_TYPES = {
    "target",
    "scanner_run",
    "scanner_lead",
    "finding",
    "chain",
    "proof",
    "validation",
    "trace",
    "remediation_candidate",
    "patch_validation",
    "issue_plan_entry",
    "metric",
    "workflow_profile",
    "workflow_stage",
}
EDGE_TYPES = {
    "produced",
    "supports",
    "challenges",
    "invalidates",
    "depends_on",
    "member_of",
    "validated_by",
    "publication_candidate",
    "not_applicable",
}
HIGH_CRITICAL = {"Critical", "High"}


class EvidenceGraphSafetyError(RuntimeError):
    """Raised when evidence graph inputs would escape the local run directory."""


def path_under(path: Path, base: Path) -> bool:
    try:
        rel = path.relative_to(base)
    except ValueError:
        return False
    if ".." in rel.parts:
        return False
    existing = path
    while existing != base and not existing.exists() and not existing.is_symlink():
        existing = existing.parent
    try:
        existing.resolve(strict=True).relative_to(base.resolve(strict=True))
        return True
    except (FileNotFoundError, ValueError):
        return False


def reject_symlink_components_under(path: Path, base: Path, label: str) -> None:
    try:
        rel = path.relative_to(base)
    except ValueError as exc:
        raise EvidenceGraphSafetyError(f"{label} must stay under run directory: {path}") from exc
    current = base
    for part in rel.parts:
        current = current / part
        if current.is_symlink():
            raise EvidenceGraphSafetyError(f"{label} must not contain symlink components: {current}")


def ensure_under_run(path: Path, run_dir: Path, label: str) -> Path:
    if not path_under(path, run_dir):
        raise EvidenceGraphSafetyError(f"{label} must stay under run directory: {path}")
    reject_symlink_components_under(path, run_dir, label)
    return path


def safe_relative_context_dir(run_dir: Path, key: str, default: str, label: str) -> Path:
    ctx = load_context(run_dir)
    raw = Path(str(ctx.get(key, default) or default))
    if raw.is_absolute():
        raise EvidenceGraphSafetyError(f"{label} must be relative under run directory: {raw}")
    if ".." in raw.parts:
        raise EvidenceGraphSafetyError(f"{label} must not contain path traversal: {raw}")
    return ensure_under_run(run_dir / raw, run_dir, label)


def reports_dir(run_dir: Path) -> Path:
    return safe_relative_context_dir(run_dir, "reports_dir", "reports", "reports_dir")


def rel_to_run(run_dir: Path, path: Path) -> str:
    try:
        return path.relative_to(run_dir).as_posix()
    except ValueError:
        return str(path)


def json_pointer(base: str, key: str, index: int) -> str:
    return f"{base}#/{key}/{index}"


def short_text(value: Any, *, max_len: int = 160) -> str:
    text = " ".join(str(value or "").split())
    if len(text) > max_len:
        return text[: max_len - 1].rstrip() + "…"
    return text


def nonnegative_int(value: Any) -> int:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return 0


def list_strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str) and str(item).strip()]


def affected_files(finding: dict[str, Any]) -> set[str]:
    files: set[str] = set()
    for location in finding.get("affected_locations") or []:
        if isinstance(location, dict) and isinstance(location.get("file"), str):
            files.add(location["file"])
    return files


def target_matches_finding(target: dict[str, Any], finding: dict[str, Any]) -> bool:
    if str(target.get("category") or "") and str(target.get("category") or "") == str(finding.get("category") or ""):
        return True
    scope = str(target.get("scope") or "")
    if scope and scope in affected_files(finding):
        return True
    target_entries = set(list_strings(target.get("entry_points")))
    finding_entry = str(finding.get("entry_point") or "")
    return bool(finding_entry and finding_entry in target_entries)


def has_missing_evidence(record: dict[str, Any]) -> bool:
    missing = record.get("missing_evidence")
    return isinstance(missing, list) and any(isinstance(item, str) and item.strip() for item in missing)


class EvidenceGraphBuilder:
    def __init__(self, run_dir: Path) -> None:
        self.run_dir = run_dir
        self.ctx = load_context(run_dir)
        self.reports = reports_dir(run_dir)
        self.nodes: dict[str, dict[str, Any]] = {}
        self.edges: dict[tuple[str, str, str], dict[str, Any]] = {}
        self.missing_optional_artifacts: list[str] = []
        self.findings: list[dict[str, Any]] = []
        self.targets: list[dict[str, Any]] = []
        self.scanner_leads: list[dict[str, Any]] = []
        self.scanner_runs: list[dict[str, Any]] = []
        self.chains: list[dict[str, Any]] = []
        self.proofs: list[dict[str, Any]] = []
        self.validations: list[dict[str, Any]] = []
        self.traces: list[dict[str, Any]] = []
        self.remediation_candidates: list[dict[str, Any]] = []
        self.patch_validations: list[dict[str, Any]] = []
        self.issue_plan_entries: list[dict[str, Any]] = []
        self.metrics: dict[str, Any] = {}
        self.workflow_profile: dict[str, Any] = {}

    def report_artifact(self, rel: str) -> Path:
        return self.reports / rel

    def report_rel(self, rel: str) -> str:
        return rel_to_run(self.run_dir, self.report_artifact(rel))

    def load_report_array(self, rel: str, key: str) -> list[dict[str, Any]]:
        path = self.report_artifact(rel)
        if not path.exists():
            self.missing_optional_artifacts.append(rel_to_run(self.run_dir, path))
            return []
        data = load_json(path, {}) or {}
        records = data.get(key) if isinstance(data, dict) else []
        return [record for record in records if isinstance(record, dict)]

    def collect_patch_validation_files(self, remediation_root: Path) -> list[Path]:
        paths: list[Path] = []
        pending = [remediation_root]
        while pending:
            current = pending.pop()
            for entry in sorted(current.iterdir(), key=lambda item: item.name):
                if entry.is_symlink():
                    continue
                if entry.is_dir():
                    pending.append(ensure_under_run(entry, self.run_dir, "remediation directory"))
                    continue
                if entry.name == "patch-validation.json":
                    paths.append(ensure_under_run(entry, self.run_dir, "patch validation artifact"))
        return sorted(paths)

    def add_node(self, node: dict[str, Any]) -> None:
        node_id = str(node.get("id") or "")
        node_type = str(node.get("type") or "")
        if not node_id or node_type not in NODE_TYPES:
            return
        node.setdefault("label", node_id)
        node.setdefault("path", "")
        node.setdefault("summary", "")
        self.nodes[node_id] = node

    def add_edge(self, source: str, target: str, edge_type: str, *, reason: str = "", path: str = "") -> None:
        if edge_type not in EDGE_TYPES or source not in self.nodes or target not in self.nodes:
            return
        key = (source, target, edge_type)
        self.edges[key] = {
            "source": source,
            "target": target,
            "type": edge_type,
            "reason": short_text(reason),
            "path": path,
        }

    def load_artifacts(self) -> None:
        self.findings = self.load_report_array("findings.json", "findings")
        self.targets = self.load_report_array("targets.json", "targets")
        scanner_path = self.reports / "scanner-results" / "scanner-index.json"
        if scanner_path.exists():
            scanner_index = load_json(scanner_path, {}) or {}
            self.scanner_leads = [item for item in scanner_index.get("results") or [] if isinstance(item, dict)]
        else:
            self.missing_optional_artifacts.append(rel_to_run(self.run_dir, scanner_path))
        scanner_runs_path = self.reports / "scanner-runs.json"
        if scanner_runs_path.exists():
            try:
                scanner_runs = load_json(scanner_runs_path, {}) or {}
                validate_scanner_runs_for_run(self.run_dir, scanner_runs)
            except (OSError, json.JSONDecodeError, ScannerReportError) as exc:
                raise EvidenceGraphSafetyError(f"scanner-runs.json is not public-safe: {exc}") from exc
            self.scanner_runs = list(scanner_runs["runs"])
        self.chains = self.load_report_array("chains.json", "chains")
        self.proofs = self.load_report_array("proofs.json", "proofs")
        self.validations = self.load_report_array("validation.json", "validations")
        self.traces = self.load_report_array("traces.json", "traces")
        self.remediation_candidates = self.load_report_array("remediation/remediation-candidates.json", "candidates")
        issue_plan_path = self.reports / "issue-publication-plan.json"
        if issue_plan_path.exists():
            issue_plan = load_json(issue_plan_path, {}) or {}
            self.issue_plan_entries = [item for item in issue_plan.get("selected_findings") or [] if isinstance(item, dict)]
        else:
            self.missing_optional_artifacts.append(rel_to_run(self.run_dir, issue_plan_path))
        metrics_path = self.reports / "metrics.json"
        if metrics_path.exists():
            metrics = load_json(metrics_path, {}) or {}
            self.metrics = metrics if isinstance(metrics, dict) else {}
        else:
            self.missing_optional_artifacts.append(rel_to_run(self.run_dir, metrics_path))
        workflow_profile_path = self.reports / "workflow-profile.json"
        if workflow_profile_path.exists():
            profile = load_json(workflow_profile_path, {}) or {}
            self.workflow_profile = profile if isinstance(profile, dict) else {}
        remediation_root = self.reports / "remediation"
        safe_remediation_root = ensure_under_run(remediation_root, self.run_dir, "remediation directory")
        if safe_remediation_root.exists():
            for path in self.collect_patch_validation_files(safe_remediation_root):
                data = load_json(path, {}) or {}
                if isinstance(data, dict):
                    data = dict(data)
                    data.setdefault("report_file", rel_to_run(self.run_dir, path))
                    self.patch_validations.append(data)

    def add_artifact_nodes(self) -> None:
        for index, finding in enumerate(self.findings):
            finding_id = str(finding.get("id") or f"index-{index}")
            self.add_node({
                "id": f"finding:{finding_id}",
                "type": "finding",
                "ref_id": finding_id,
                "label": str(finding.get("title") or finding_id),
                "severity": str(finding.get("severity") or "Unknown"),
                "status": str(finding.get("status") or "Unknown"),
                "path": json_pointer(self.report_rel("findings.json"), "findings", index),
                "summary": short_text(finding.get("title") or finding_id),
            })
        for index, target in enumerate(self.targets):
            target_id = str(target.get("id") or f"index-{index}")
            self.add_node({
                "id": f"target:{target_id}",
                "type": "target",
                "ref_id": target_id,
                "label": str(target.get("title") or target_id),
                "severity": str(target.get("risk") or "unknown"),
                "status": str(target.get("status") or "unknown"),
                "path": json_pointer(self.report_rel("targets.json"), "targets", index),
                "summary": short_text(target.get("title") or target_id),
            })
        for index, lead in enumerate(self.scanner_leads):
            ref = str(lead.get("normalized_path") or lead.get("path") or f"scanner-{index + 1}")
            self.add_node({
                "id": f"scanner_lead:{ref}",
                "type": "scanner_lead",
                "ref_id": ref,
                "label": str(lead.get("tool") or ref),
                "severity": "Unknown",
                "status": str(lead.get("format") or "unknown"),
                "path": ref,
                "summary": short_text(f"{lead.get('tool', 'scanner')} lead {ref}"),
            })
        for index, scanner_run in enumerate(self.scanner_runs):
            run_id = str(scanner_run.get("id") or f"index-{index}")
            self.add_node({
                "id": f"scanner_run:{run_id}",
                "type": "scanner_run",
                "ref_id": run_id,
                "label": str(scanner_run.get("adapter_id") or run_id),
                "severity": "Unknown",
                "status": str(scanner_run.get("status") or "unknown"),
                "path": json_pointer(self.report_rel("scanner-runs.json"), "runs", index),
                "summary": short_text(
                    f"{scanner_run.get('adapter_id', 'scanner')} {scanner_run.get('scanner_status', 'unknown')} "
                    f"in {scanner_run.get('duration_ms', 0)} ms"
                ),
                "duration_ms": nonnegative_int(scanner_run.get("duration_ms")),
                "result_count": nonnegative_int(scanner_run.get("result_count")),
                "normalized_leads_count": nonnegative_int(scanner_run.get("normalized_leads_count")),
            })
        for index, chain in enumerate(self.chains):
            chain_id = str(chain.get("id") or f"index-{index}")
            self.add_node({
                "id": f"chain:{chain_id}",
                "type": "chain",
                "ref_id": chain_id,
                "label": str(chain.get("title") or chain_id),
                "severity": str(chain.get("severity") or "Unknown"),
                "status": str(chain.get("status") or "Unknown"),
                "path": json_pointer(self.report_rel("chains.json"), "chains", index),
                "summary": short_text(chain.get("title") or chain_id),
            })
        for index, proof in enumerate(self.proofs):
            proof_id = str(proof.get("id") or f"index-{index}")
            self.add_node({
                "id": f"proof:{proof_id}",
                "type": "proof",
                "ref_id": proof_id,
                "label": proof_id,
                "severity": "Unknown",
                "status": str(proof.get("status") or "unknown"),
                "path": json_pointer(self.report_rel("proofs.json"), "proofs", index),
                "summary": short_text(proof.get("proof_type") or proof_id),
            })
        for index, validation in enumerate(self.validations):
            validation_id = str(validation.get("id") or f"index-{index}")
            self.add_node({
                "id": f"validation:{validation_id}",
                "type": "validation",
                "ref_id": validation_id,
                "label": validation_id,
                "severity": str(validation.get("recommended_severity") or "Unknown"),
                "status": str(validation.get("decision") or "unknown"),
                "path": json_pointer(self.report_rel("validation.json"), "validations", index),
                "summary": short_text(f"{validation.get('decision', 'validation')} {validation.get('subject_type', '')}:{validation.get('subject_id', '')}"),
            })
        for index, trace in enumerate(self.traces):
            trace_id = str(trace.get("id") or f"index-{index}")
            self.add_node({
                "id": f"trace:{trace_id}",
                "type": "trace",
                "ref_id": trace_id,
                "label": trace_id,
                "severity": "Unknown",
                "status": str(trace.get("status") or "unknown"),
                "path": json_pointer(self.report_rel("traces.json"), "traces", index),
                "summary": short_text(f"{trace.get('producer_repo', '')} -> {trace.get('consumer_repo', '')}"),
            })
        for index, candidate in enumerate(self.remediation_candidates):
            candidate_id = str(candidate.get("id") or f"index-{index}")
            self.add_node({
                "id": f"remediation_candidate:{candidate_id}",
                "type": "remediation_candidate",
                "ref_id": candidate_id,
                "label": candidate_id,
                "severity": "Unknown",
                "status": str(candidate.get("status") or "unknown"),
                "path": json_pointer(self.report_rel("remediation/remediation-candidates.json"), "candidates", index),
                "summary": short_text(f"remediation candidate {candidate_id} status {candidate.get('status', 'unknown')}"),
            })
        for index, validation in enumerate(self.patch_validations):
            patch_id = str(validation.get("patch_id") or validation.get("id") or f"index-{index}")
            self.add_node({
                "id": f"patch_validation:{patch_id}",
                "type": "patch_validation",
                "ref_id": patch_id,
                "label": patch_id,
                "severity": "Unknown",
                "status": str(validation.get("final_status") or "unknown"),
                "path": str(validation.get("report_file") or ""),
                "summary": short_text(f"patch validation {validation.get('final_status', 'unknown')}"),
            })
        for index, entry in enumerate(self.issue_plan_entries):
            finding_id = str(entry.get("id") or f"index-{index}")
            node_id = f"issue_plan_entry:{finding_id}"
            self.add_node({
                "id": node_id,
                "type": "issue_plan_entry",
                "ref_id": finding_id,
                "label": str(entry.get("title") or finding_id),
                "severity": "Unknown",
                "status": "planned",
                "path": json_pointer(self.report_rel("issue-publication-plan.json"), "selected_findings", index),
                "summary": short_text(entry.get("title") or finding_id),
            })
        if self.metrics:
            self.add_node({
                "id": "metric:run",
                "type": "metric",
                "ref_id": "run",
                "label": "Run metrics",
                "severity": "Unknown",
                "status": "present",
                "path": self.report_rel("metrics.json"),
                "summary": "Run-level aggregate metrics",
            })
        if self.workflow_profile:
            profile_name = str(self.workflow_profile.get("profile") or "unknown")
            self.add_node({
                "id": "workflow_profile:run",
                "type": "workflow_profile",
                "ref_id": profile_name,
                "label": f"Workflow profile: {profile_name}",
                "severity": "Unknown",
                "status": profile_name,
                "path": self.report_rel("workflow-profile.json"),
                "summary": short_text(f"Workflow profile {profile_name}"),
            })
            for index, stage in enumerate(self.workflow_profile.get("stages") or []):
                if not isinstance(stage, dict):
                    continue
                stage_id = str(stage.get("id") or f"index-{index}")
                self.add_node({
                    "id": f"workflow_stage:{stage_id}",
                    "type": "workflow_stage",
                    "ref_id": stage_id,
                    "label": str(stage.get("title") or stage_id),
                    "severity": "Unknown",
                    "status": str(stage.get("status") or "unknown"),
                    "path": json_pointer(self.report_rel("workflow-profile.json"), "stages", index),
                    "summary": short_text(stage.get("reason") or stage_id),
                })

    def add_edges(self) -> None:
        scanner_lead_ids = {
            str(lead.get("normalized_path") or lead.get("path") or ""): f"scanner_lead:{str(lead.get('normalized_path') or lead.get('path') or '')}"
            for lead in self.scanner_leads
        }
        for scanner_run in self.scanner_runs:
            scanner_run_id = str(scanner_run.get("id") or "")
            normalized_ref = str(scanner_run.get("normalized_result_ref") or "")
            lead_node = scanner_lead_ids.get(normalized_ref)
            if scanner_run_id and lead_node:
                self.add_edge(
                    f"scanner_run:{scanner_run_id}",
                    lead_node,
                    "produced",
                    reason="scanner execution produced normalized review-only leads",
                )
        for target in self.targets:
            target_id = str(target.get("id") or "")
            for finding in self.findings:
                finding_id = str(finding.get("id") or "")
                if target_id and finding_id and target_matches_finding(target, finding):
                    self.add_edge(f"target:{target_id}", f"finding:{finding_id}", "supports", reason="target category, scope, or entry point overlaps finding")
        for chain in self.chains:
            chain_id = str(chain.get("id") or "")
            for finding_id in list_strings(chain.get("findings")):
                self.add_edge(f"finding:{finding_id}", f"chain:{chain_id}", "member_of", reason="finding is listed in chain")
                self.add_edge(f"chain:{chain_id}", f"finding:{finding_id}", "supports", reason="chain includes finding as a member")
            for target_id in list_strings(chain.get("targets")):
                self.add_edge(f"target:{target_id}", f"chain:{chain_id}", "supports", reason="target is listed in chain")
            for scanner_ref in list_strings(chain.get("scanner_refs")):
                self.add_edge(f"scanner_lead:{scanner_ref}", f"chain:{chain_id}", "supports", reason="scanner lead is listed in chain")
        for finding in self.findings:
            finding_id = str(finding.get("id") or "")
            for chain_id in list_strings(finding.get("chain_membership")):
                self.add_edge(f"finding:{finding_id}", f"chain:{chain_id}", "member_of", reason="finding declares chain membership")
        for proof in self.proofs:
            proof_id = str(proof.get("id") or "")
            finding_id = str(proof.get("finding_id") or "")
            status = str(proof.get("status") or "")
            edge_type = "not_applicable" if status == "not-applicable" else "validated_by"
            self.add_edge(f"finding:{finding_id}", f"proof:{proof_id}", edge_type, reason=f"proof status {status or 'unknown'}")
            if status in {"confirmed", "passed"}:
                self.add_edge(f"proof:{proof_id}", f"finding:{finding_id}", "supports", reason="proof supports finding")
            elif status in {"failed", "needs-human-review"}:
                self.add_edge(f"proof:{proof_id}", f"finding:{finding_id}", "challenges", reason=f"proof status {status}")
        for validation in self.validations:
            validation_id = str(validation.get("id") or "")
            subject_type = str(validation.get("subject_type") or "")
            subject_id = str(validation.get("subject_id") or "")
            decision = str(validation.get("decision") or "")
            target_node = f"{subject_type}:{subject_id}"
            if subject_type == "chain":
                target_node = f"chain:{subject_id}"
            edge_type = "supports" if decision == "confirm" else "invalidates" if decision == "invalidate" else "challenges"
            self.add_edge(f"validation:{validation_id}", target_node, edge_type, reason=f"adversarial validation decision {decision or 'unknown'}")
            if has_missing_evidence(validation):
                self.add_edge(f"validation:{validation_id}", target_node, "challenges", reason="validation records missing evidence")
            self.add_edge(target_node, f"validation:{validation_id}", "validated_by", reason="subject has adversarial validation")
        for trace in self.traces:
            trace_id = str(trace.get("id") or "")
            finding_id = str(trace.get("finding_id") or "")
            status = str(trace.get("status") or "")
            self.add_edge(f"trace:{trace_id}", f"finding:{finding_id}", "supports" if status in {"Confirmed", "Probable"} else "challenges", reason=f"trace status {status or 'unknown'}")
            self.add_edge(f"finding:{finding_id}", f"trace:{trace_id}", "validated_by", reason="finding has trace record")
        for candidate in self.remediation_candidates:
            candidate_id = str(candidate.get("id") or "")
            finding_id = str(candidate.get("finding_id") or "")
            self.add_edge(f"remediation_candidate:{candidate_id}", f"finding:{finding_id}", "depends_on", reason="remediation candidate targets finding")
        for validation in self.patch_validations:
            patch_id = str(validation.get("patch_id") or validation.get("id") or "")
            self.add_edge(f"remediation_candidate:{patch_id}", f"patch_validation:{patch_id}", "validated_by", reason="patch validation result")
        for entry in self.issue_plan_entries:
            finding_id = str(entry.get("id") or "")
            self.add_edge(f"issue_plan_entry:{finding_id}", f"finding:{finding_id}", "publication_candidate", reason="finding appears in issue publication plan")
        if self.metrics:
            for finding in self.findings:
                finding_id = str(finding.get("id") or "")
                self.add_edge("metric:run", f"finding:{finding_id}", "produced", reason="run metrics summarize finding population")
        if self.workflow_profile and "workflow_profile:run" in self.nodes:
            for stage in self.workflow_profile.get("stages") or []:
                if not isinstance(stage, dict):
                    continue
                stage_id = str(stage.get("id") or "")
                if stage_id:
                    self.add_edge(
                        "workflow_profile:run",
                        f"workflow_stage:{stage_id}",
                        "produced",
                        reason=f"workflow profile marks stage {stage.get('status', 'unknown')}",
                    )

    def summary(self) -> dict[str, Any]:
        node_counts = Counter(node["type"] for node in self.nodes.values())
        edge_counts = Counter(edge["type"] for edge in self.edges.values())
        supporting_edges = {edge["target"] for edge in self.edges.values() if edge["type"] in {"supports", "validated_by", "member_of"}}
        challenging_edges = {edge["target"] for edge in self.edges.values() if edge["type"] in {"challenges", "invalidates"}}
        high_issue_findings = [
            finding for finding in self.findings
            if str(finding.get("severity") or "") in HIGH_CRITICAL and finding.get("issue_recommended") is not False
        ]
        scanner_statuses = Counter(str(item.get("status") or "unknown") for item in self.scanner_runs)
        scanner_durations = [
            nonnegative_int(item.get("duration_ms"))
            for item in self.scanner_runs
        ]
        return {
            "node_count": len(self.nodes),
            "edge_count": len(self.edges),
            "node_counts": dict(sorted(node_counts.items())),
            "edge_counts": dict(sorted(edge_counts.items())),
            "missing_optional_artifacts": sorted(set(self.missing_optional_artifacts)),
            "workflow_profile": summarize_workflow_profile(self.workflow_profile),
            "scanner_runs": {
                "artifact_present": bool(self.scanner_runs),
                "run_count": len(self.scanner_runs),
                "by_status": dict(sorted(scanner_statuses.items())),
                "total_duration_ms": sum(scanner_durations),
                "maximum_duration_ms": max(scanner_durations, default=0),
            },
            "high_critical_issue_recommended_findings": len(high_issue_findings),
            "high_critical_with_supporting_evidence": sum(1 for finding in high_issue_findings if f"finding:{finding.get('id')}" in supporting_edges),
            "high_critical_with_challenging_evidence": sum(1 for finding in high_issue_findings if f"finding:{finding.get('id')}" in challenging_edges),
        }

    def build(self) -> dict[str, Any]:
        self.load_artifacts()
        self.add_artifact_nodes()
        self.add_edges()
        graph = {
            "schema_version": "1",
            "run_id": self.ctx.get("run_id", self.run_dir.name),
            "repo": self.ctx.get("repo", ""),
            "branch": self.ctx.get("branch", ""),
            "commit": self.ctx.get("commit", ""),
            "generated_at": utc_now(),
            "source": "local-report-artifacts",
            "safety": {
                "local_artifacts_only": True,
                "raw_evidence_copied": False,
                "secret_values_copied": False,
                "bounded_summaries_only": True,
            },
            "summary": self.summary(),
            "nodes": sorted(self.nodes.values(), key=lambda item: (item["type"], item["id"])),
            "edges": sorted(self.edges.values(), key=lambda item: (item["source"], item["type"], item["target"])),
        }
        return graph


def build_evidence_graph(run_dir: Path) -> dict[str, Any]:
    return EvidenceGraphBuilder(run_dir).build()


def write_evidence_graph(run_dir: Path, graph: dict[str, Any]) -> tuple[Path, Path]:
    reports = reports_dir(run_dir)
    json_path = reports / "evidence-graph.json"
    md_path = reports / "EVIDENCE_GRAPH.md"
    write_json(json_path, graph)
    render_evidence_graph_markdown(md_path, graph)
    return json_path, md_path


def render_evidence_graph_markdown(path: Path, graph: dict[str, Any]) -> None:
    summary = graph.get("summary") if isinstance(graph.get("summary"), dict) else {}
    workflow_profile = summary.get("workflow_profile") if isinstance(summary.get("workflow_profile"), dict) else {}
    scanner_runs = summary.get("scanner_runs") if isinstance(summary.get("scanner_runs"), dict) else {}
    lines = [
        "# Evidence Graph",
        "",
        "Local-only graph linking audit artifacts without copying raw evidence, proof payloads, or secrets.",
        "",
        f"Run ID: `{graph.get('run_id', '')}`",
        f"Repository: `{graph.get('repo', '')}`",
        f"Generated at: `{graph.get('generated_at', '')}`",
        "",
        "## Summary",
        "",
        f"- Nodes: {summary.get('node_count', 0)}",
        f"- Edges: {summary.get('edge_count', 0)}",
        f"- Workflow profile: `{workflow_profile.get('profile', 'not-recorded')}`",
        f"- Stages skipped by scope: {workflow_profile.get('skipped_by_scope_count', 0)}",
        f"- Scanner executions: {scanner_runs.get('run_count', 0)}",
        f"- Scanner execution duration: {scanner_runs.get('total_duration_ms', 0)} ms",
        f"- High/Critical issue-recommended findings: {summary.get('high_critical_issue_recommended_findings', 0)}",
        f"- With supporting evidence: {summary.get('high_critical_with_supporting_evidence', 0)}",
        f"- With challenging evidence: {summary.get('high_critical_with_challenging_evidence', 0)}",
        "",
        "## Nodes by type",
        "",
        "| Type | Count |",
        "|---|---:|",
    ]
    for node_type, count in (summary.get("node_counts") or {}).items():
        lines.append(f"| {node_type} | {count} |")
    lines.extend(["", "## Edges by type", "", "| Type | Count |", "|---|---:|"])
    for edge_type, count in (summary.get("edge_counts") or {}).items():
        lines.append(f"| {edge_type} | {count} |")
    lines.extend(["", "## Finding evidence", "", "| Finding | Supporting/challenging links |", "|---|---|"])
    edges_by_target: dict[str, list[str]] = {}
    for edge in graph.get("edges") or []:
        if isinstance(edge, dict):
            edges_by_target.setdefault(str(edge.get("target") or ""), []).append(
                f"{edge.get('type')} from `{edge.get('source')}`"
            )
    for node in graph.get("nodes") or []:
        if isinstance(node, dict) and node.get("type") == "finding":
            links = "; ".join(edges_by_target.get(str(node.get("id") or ""), [])) or "No inbound evidence links"
            lines.append(f"| `{node.get('ref_id')}` | {links} |")
    missing = summary.get("missing_optional_artifacts") or []
    if missing:
        lines.extend(["", "## Missing optional artifacts", ""])
        for rel in missing:
            lines.append(f"- `{rel}`")
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
