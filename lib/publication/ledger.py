from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from duplicate_decisions import (
    decision_for as duplicate_decision_for,
    rel_to_run as duplicate_decision_rel_to_run,
    write_duplicate_decision,
)
from issue_ledger import (
    base_entry as ledger_base_entry,
    default_ledger_path,
    load_ledger,
    merge_current_entries,
    plan_source as ledger_plan_source,
    write_ledger,
)

from .planning import plan_entry_key
from .policy import finding_selection_reason, issue_title, normalize_labels
from .rendering import sha256_text, stable_fingerprint


def ledger_entry_from_plan_entry(
    entry: Dict[str, Any],
    body: str,
    *,
    publication_status: str,
    run_dir: Path,
    plan_path: Optional[Path],
    plan_sha256: Optional[str],
) -> Dict[str, Any]:
    return ledger_base_entry(
        finding_id=str(entry.get("id") or "SEC-UNKNOWN"),
        fingerprint=str(entry.get("fingerprint") or ""),
        title=str(entry.get("title") or ""),
        labels=[str(label) for label in entry.get("labels") or []],
        body_hash=str(entry.get("issue_body_sha256") or sha256_text(body)),
        publication_status=publication_status,
        source_plan=ledger_plan_source(plan_path, run_dir),
        plan_sha256=plan_sha256,
    )


def build_ledger_entries(
    *,
    repo: str,
    findings: Iterable[Dict[str, Any]],
    selected_entries: Iterable[Dict[str, Any]],
    selected_bodies: Dict[str, str],
    run_dir: Path,
    min_severity: str,
    statuses: Iterable[str],
    novelty_entries: Optional[Dict[str, Dict[str, Any]]],
    plan_path: Optional[Path],
    plan_sha256: Optional[str],
    overrides: Optional[Dict[str, Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    overrides = overrides or {}
    selected_by_key: Dict[str, Tuple[Dict[str, Any], str]] = {}
    for entry in selected_entries:
        if not isinstance(entry, dict):
            continue
        selected_by_key[plan_entry_key(entry)] = (entry, selected_bodies.get(plan_entry_key(entry), ""))

    entries: List[Dict[str, Any]] = []
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        finding_id = str(finding.get("id") or "SEC-UNKNOWN")
        fingerprint = stable_fingerprint(repo, finding)
        key = f"{finding_id}\0{fingerprint}"
        if key in overrides:
            entries.append(dict(overrides[key]))
            continue
        planned = selected_by_key.get(key)
        if planned:
            entry, body = planned
            entries.append(
                ledger_entry_from_plan_entry(
                    entry,
                    body,
                    publication_status="pending",
                    run_dir=run_dir,
                    plan_path=plan_path,
                    plan_sha256=plan_sha256,
                )
            )
        else:
            entries.append(
                ledger_base_entry(
                    finding_id=finding_id,
                    fingerprint=fingerprint,
                    title=issue_title(finding),
                    labels=normalize_labels(finding),
                    body_hash=None,
                    publication_status="not-selected",
                    selection_reason=finding_selection_reason(
                        finding,
                        min_severity,
                        statuses,
                        repo=repo,
                        novelty_entries=novelty_entries,
                    ),
                    source_plan=ledger_plan_source(plan_path, run_dir),
                    plan_sha256=plan_sha256,
                )
            )
    return entries


def write_issue_ledger_snapshot(
    *,
    run_dir: Path,
    repo: str,
    run_id: str,
    commit: str,
    findings: Iterable[Dict[str, Any]],
    selected_entries: Iterable[Dict[str, Any]],
    selected_bodies: Dict[str, str],
    min_severity: str,
    statuses: Iterable[str],
    novelty_entries: Optional[Dict[str, Dict[str, Any]]],
    plan_path: Optional[Path],
    plan_sha256: Optional[str],
    plan_written: bool,
    publication_plan_status: str,
    overrides: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    ledger_path = default_ledger_path(run_dir)
    existing = load_ledger(ledger_path, run_id=run_id, repo=repo, commit=commit)
    current_entries = build_ledger_entries(
        repo=repo,
        findings=findings,
        selected_entries=selected_entries,
        selected_bodies=selected_bodies,
        run_dir=run_dir,
        min_severity=min_severity,
        statuses=statuses,
        novelty_entries=novelty_entries,
        plan_path=plan_path,
        plan_sha256=plan_sha256,
        overrides=overrides,
    )
    ledger = merge_current_entries(
        existing=existing,
        current_entries=current_entries,
        run_id=run_id,
        repo=repo,
        commit=commit,
        plan_written=plan_written,
        publication_plan_status=publication_plan_status,
    )
    write_ledger(run_dir, ledger_path, ledger)
    print(f"Wrote issue ledger: {ledger_path}")
    return ledger


def record_duplicate_decision(
    *,
    run_dir: Path,
    run_id: str,
    repo: str,
    commit: str,
    finding: Dict[str, Any],
    fingerprint: str,
    exact_match_url: Optional[str] = None,
    exact_match_source: Optional[str] = None,
) -> Tuple[str, str]:
    decision = duplicate_decision_for(
        run_id=run_id,
        repo=repo,
        commit=commit,
        finding=finding,
        fingerprint=fingerprint,
        exact_match_url=exact_match_url,
        exact_match_source=exact_match_source,
    )
    path = write_duplicate_decision(run_dir, decision)
    rel_path = duplicate_decision_rel_to_run(run_dir, path)
    print(f"Wrote duplicate decision: {rel_path}")
    return rel_path, str(decision.get("decision") or "")
