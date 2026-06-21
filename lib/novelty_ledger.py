from __future__ import annotations

import hashlib
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from gralib import load_context, load_json, utc_now, write_json

NOVELTY_STATUSES = {
    "new",
    "duplicate",
    "better-example",
    "accepted-risk",
    "regression",
    "invalid-known",
    "needs-human-review",
}
SUPPRESSED_PUBLICATION_STATUSES = {"duplicate", "accepted-risk", "invalid-known"}
SEVERITY_RANK = {"Critical": 5, "High": 4, "Medium": 3, "Low": 2, "Informational": 1}
CONFIDENCE_RANK = {"High": 3, "Medium": 2, "Low": 1}
FINDING_STATUS_RANK = {
    "Confirmed": 4,
    "Probable": 3,
    "Potential": 2,
    "Needs human review": 1,
    "Informational": 1,
    "Invalid": 0,
}
EMPTY_HASH = hashlib.sha256(b"").hexdigest()[:24]


def normalize_text(value: Any) -> str:
    text = "" if value is None else str(value)
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def digest_text(value: Any, *, length: int = 24) -> str:
    normalized = normalize_text(value)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:length]


def digest_list(values: Iterable[Any], *, length: int = 24) -> str:
    normalized = "\n".join(sorted(normalize_text(value) for value in values))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:length]


def affected_files(finding: dict[str, Any]) -> list[str]:
    files: list[str] = []
    for loc in finding.get("affected_locations") or []:
        if not isinstance(loc, dict):
            continue
        file_name = str(loc.get("file") or "").strip()
        if file_name:
            files.append(file_name)
    return sorted(set(files))


def finding_hashes(finding: dict[str, Any]) -> dict[str, str]:
    return {
        "root_cause": digest_text(finding.get("root_cause")),
        "source_to_sink": digest_text(finding.get("source_to_sink") or finding.get("call_path")),
        "evidence": digest_text(finding.get("evidence")),
        "impact": digest_text(finding.get("impact")),
        "affected_locations": digest_list(affected_files(finding)),
        "entry_point": digest_text(finding.get("entry_point")),
        "trust_boundary": digest_text(finding.get("trust_boundary")),
        "chain_membership": digest_list(finding.get("chain_membership") or []),
    }


def finding_strength(finding: dict[str, Any]) -> dict[str, int]:
    return {
        "severity": SEVERITY_RANK.get(str(finding.get("severity") or ""), 0),
        "confidence": CONFIDENCE_RANK.get(str(finding.get("confidence") or ""), 0),
        "status": FINDING_STATUS_RANK.get(str(finding.get("status") or ""), 0),
        "evidence_size": len(str(finding.get("evidence") or "")),
        "impact_size": len(str(finding.get("impact") or "")),
    }


def current_entry_base(finding: dict[str, Any]) -> dict[str, Any]:
    hashes = finding_hashes(finding)
    strength = finding_strength(finding)
    fingerprint = str(finding.get("fingerprint") or "").strip()
    finding_id = str(finding.get("id") or "SEC-UNKNOWN")
    return {
        "finding_id": finding_id,
        "fingerprint": fingerprint,
        "severity": str(finding.get("severity") or "Unknown"),
        "confidence": str(finding.get("confidence") or "Unknown"),
        "finding_status": str(finding.get("status") or "Unknown"),
        "hashes": hashes,
        "strength": strength,
        "match": {
            "previous_finding_id": None,
            "previous_fingerprint": None,
            "reasons": [],
        },
        "accepted_risk": {
            "active": False,
            "reason": None,
        },
    }


def prior_hash(prior: dict[str, Any], name: str) -> str:
    hashes = prior.get("hashes") if isinstance(prior.get("hashes"), dict) else {}
    return str(hashes.get(name) or "")


def prior_strength(prior: dict[str, Any], name: str) -> int:
    strength = prior.get("strength") if isinstance(prior.get("strength"), dict) else {}
    try:
        return int(strength.get(name) or 0)
    except (TypeError, ValueError):
        return 0


def prior_is_accepted_risk(prior: dict[str, Any]) -> bool:
    accepted = prior.get("accepted_risk") if isinstance(prior.get("accepted_risk"), dict) else {}
    return bool(accepted.get("active")) or str(prior.get("novelty_status") or "") == "accepted-risk"


def evidence_or_impact_changed(current: dict[str, Any], prior: dict[str, Any]) -> bool:
    hashes = current.get("hashes") if isinstance(current.get("hashes"), dict) else {}
    for name in ["evidence", "impact", "source_to_sink", "affected_locations", "entry_point", "trust_boundary", "chain_membership"]:
        if str(hashes.get(name) or "") != prior_hash(prior, name):
            return True
    return False


def materially_stronger(current: dict[str, Any], prior: dict[str, Any]) -> bool:
    strength = current.get("strength") if isinstance(current.get("strength"), dict) else {}
    if int(strength.get("severity") or 0) > prior_strength(prior, "severity"):
        return True
    if int(strength.get("confidence") or 0) > prior_strength(prior, "confidence"):
        return True
    if int(strength.get("status") or 0) > prior_strength(prior, "status"):
        return True
    if int(strength.get("evidence_size") or 0) > prior_strength(prior, "evidence_size"):
        return True
    if int(strength.get("impact_size") or 0) > prior_strength(prior, "impact_size"):
        return True
    return False


def accepted_risk_changed(current: dict[str, Any], prior: dict[str, Any]) -> bool:
    strength = current.get("strength") if isinstance(current.get("strength"), dict) else {}
    return (
        evidence_or_impact_changed(current, prior)
        or int(strength.get("severity") or 0) > prior_strength(prior, "severity")
        or int(strength.get("confidence") or 0) > prior_strength(prior, "confidence")
        or int(strength.get("status") or 0) > prior_strength(prior, "status")
    )


def load_prior_entries(paths: Iterable[Path]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    seen_paths: set[Path] = set()
    for path in paths:
        resolved = path.resolve(strict=False)
        if resolved in seen_paths or not path.exists():
            continue
        seen_paths.add(resolved)
        data = load_json(path, {}) or {}
        if not isinstance(data, dict):
            continue
        for entry in data.get("findings") or []:
            if isinstance(entry, dict):
                entries.append(entry)
    return entries


def select_prior(current: dict[str, Any], prior_entries: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, list[str]]:
    fingerprint = str(current.get("fingerprint") or "")
    if fingerprint:
        for prior in prior_entries:
            if str(prior.get("fingerprint") or "") == fingerprint:
                return prior, ["fingerprint"]
    root = str((current.get("hashes") or {}).get("root_cause") or "")
    if root:
        for prior in prior_entries:
            if prior_hash(prior, "root_cause") == root:
                reasons = ["root_cause"]
                for name in ["source_to_sink", "affected_locations", "entry_point", "trust_boundary", "chain_membership"]:
                    current_hash = str((current.get("hashes") or {}).get(name) or "")
                    if current_hash and current_hash != EMPTY_HASH and current_hash == prior_hash(prior, name):
                        reasons.append(name)
                return prior, reasons
    return None, []


def classify_entry(
    finding: dict[str, Any],
    prior_entries: list[dict[str, Any]],
    *,
    accepted_risk_ids: set[str] | None = None,
    accepted_risk_reason: str | None = None,
) -> dict[str, Any]:
    accepted_risk_ids = accepted_risk_ids or set()
    entry = current_entry_base(finding)
    finding_id = str(entry["finding_id"])

    if finding_id in accepted_risk_ids:
        entry["novelty_status"] = "accepted-risk"
        entry["issue_recommended"] = False
        entry["accepted_risk"] = {"active": True, "reason": accepted_risk_reason or "operator accepted risk locally"}
        return entry

    prior, reasons = select_prior(entry, prior_entries)
    if prior is None:
        entry["novelty_status"] = "new"
        entry["issue_recommended"] = bool(finding.get("issue_recommended"))
        return entry

    entry["match"] = {
        "previous_finding_id": str(prior.get("finding_id") or "") or None,
        "previous_fingerprint": str(prior.get("fingerprint") or "") or None,
        "reasons": reasons,
    }

    if reasons == ["root_cause"]:
        entry["novelty_status"] = "needs-human-review"
        entry["issue_recommended"] = bool(finding.get("issue_recommended"))
        return entry

    if prior_is_accepted_risk(prior):
        if accepted_risk_changed(entry, prior):
            entry["novelty_status"] = "regression"
            entry["issue_recommended"] = bool(finding.get("issue_recommended"))
            entry["accepted_risk"] = {"active": False, "reason": "accepted-risk evidence or impact changed"}
        else:
            entry["novelty_status"] = "accepted-risk"
            entry["issue_recommended"] = False
            prior_accepted = prior.get("accepted_risk") if isinstance(prior.get("accepted_risk"), dict) else {}
            entry["accepted_risk"] = {
                "active": True,
                "reason": prior_accepted.get("reason") or "prior ledger accepted risk still applies",
            }
        return entry

    if "fingerprint" in reasons:
        entry["novelty_status"] = "duplicate"
        entry["issue_recommended"] = False
    elif materially_stronger(entry, prior) and evidence_or_impact_changed(entry, prior):
        entry["novelty_status"] = "better-example"
        entry["issue_recommended"] = bool(finding.get("issue_recommended"))
    else:
        entry["novelty_status"] = "duplicate"
        entry["issue_recommended"] = False
    return entry


def build_report(
    *,
    run_dir: Path,
    prior_paths: Iterable[Path] = (),
    accepted_risk_ids: set[str] | None = None,
    accepted_risk_reason: str | None = None,
) -> dict[str, Any]:
    ctx = load_context(run_dir)
    reports_dir = run_dir / str(ctx.get("reports_dir", "reports"))
    findings_data = load_json(reports_dir / "findings.json", {}) or {}
    findings = [item for item in findings_data.get("findings") or [] if isinstance(item, dict)]
    prior_entries = load_prior_entries(prior_paths)
    entries = [
        classify_entry(
            finding,
            prior_entries,
            accepted_risk_ids=accepted_risk_ids,
            accepted_risk_reason=accepted_risk_reason,
        )
        for finding in findings
    ]
    counts = Counter(str(entry.get("novelty_status") or "needs-human-review") for entry in entries)
    return {
        "schema_version": "1",
        "run_id": str(findings_data.get("run_id") or ctx.get("run_id") or run_dir.name),
        "repo": str(findings_data.get("repo") or ctx.get("repo") or ""),
        "branch": findings_data.get("branch", ctx.get("branch")),
        "commit": str(findings_data.get("commit") or ctx.get("commit") or ""),
        "generated_at": utc_now(),
        "source": "local-report-artifacts",
        "safety": {
            "local_artifacts_only": True,
            "raw_evidence_copied": False,
            "secrets_copied": False,
            "accepted_risk_exported_by_default": False,
        },
        "summary": {
            "finding_count": len(entries),
            "status_counts": {status: counts.get(status, 0) for status in sorted(NOVELTY_STATUSES)},
            "suppressed_publication_count": sum(
                1 for entry in entries if str(entry.get("novelty_status")) in SUPPRESSED_PUBLICATION_STATUSES
            ),
        },
        "findings": entries,
    }


def write_markdown(report: dict[str, Any], out_path: Path) -> None:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    counts = summary.get("status_counts") if isinstance(summary.get("status_counts"), dict) else {}
    lines = [
        "# Novelty ledger",
        "",
        "Local-only classification of current findings against prior known-finding records.",
        "The ledger stores fingerprints and hashes only; it does not copy raw evidence, root cause text, impact text, or issue bodies.",
        "",
        "## Summary",
        "",
        f"- Run ID: `{report.get('run_id', '')}`",
        f"- Repository: `{report.get('repo', '')}`",
        f"- Commit: `{report.get('commit', '')}`",
        f"- Findings: {summary.get('finding_count', 0)}",
        f"- Suppressed by default: {summary.get('suppressed_publication_count', 0)}",
        "",
        "| Novelty status | Count |",
        "|---|---:|",
    ]
    for status in sorted(NOVELTY_STATUSES):
        lines.append(f"| `{status}` | {counts.get(status, 0)} |")
    lines.extend([
        "",
        "## Findings",
        "",
        "| Finding | Fingerprint | Novelty | Issue recommended | Match reasons |",
        "|---|---|---|---:|---|",
    ])
    for entry in report.get("findings") or []:
        if not isinstance(entry, dict):
            continue
        match = entry.get("match") if isinstance(entry.get("match"), dict) else {}
        reasons = ", ".join(str(item) for item in match.get("reasons") or [])
        fingerprint = str(entry.get("fingerprint") or "")
        short_fp = fingerprint[:16] + ("…" if len(fingerprint) > 16 else "")
        lines.append(
            f"| `{entry.get('finding_id', '')}` | `{short_fp}` | `{entry.get('novelty_status', '')}` | "
            f"{str(bool(entry.get('issue_recommended'))).lower()} | {reasons or '-'} |"
        )
    lines.append("")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")


def write_report(report: dict[str, Any], reports_dir: Path) -> tuple[Path, Path]:
    json_path = reports_dir / "known-findings.json"
    md_path = reports_dir / "NOVELTY.md"
    write_json(json_path, report)
    write_markdown(report, md_path)
    return json_path, md_path


def novelty_by_finding_id(run_dir: Path) -> dict[str, dict[str, Any]]:
    ctx = load_context(run_dir)
    path = run_dir / str(ctx.get("reports_dir", "reports")) / "known-findings.json"
    data = load_json(path, {}) or {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for entry in data.get("findings") or []:
        if isinstance(entry, dict) and entry.get("finding_id"):
            out[str(entry.get("finding_id"))] = entry
    return out


def novelty_for_finding(run_dir: Path, finding: dict[str, Any]) -> dict[str, Any] | None:
    return novelty_by_finding_id(run_dir).get(str(finding.get("id") or ""))


def suppresses_publication(entry: dict[str, Any] | None) -> bool:
    if not entry:
        return False
    status = str(entry.get("novelty_status") or "")
    return status in SUPPRESSED_PUBLICATION_STATUSES or entry.get("issue_recommended") is False and status in {"duplicate", "accepted-risk"}
