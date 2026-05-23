from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from gralib import load_context, load_json, load_targets, utc_now, write_json, write_targets
from scanner_normalize import redact_text

MAX_DETAILS = 8
MAX_NOTE_CHARS = 900
SCORE_LOW_THRESHOLD = 6.0
SCORE_VERY_LOW_THRESHOLD = 3.0

CHECK_DOC_BASE = "https://github.com/ossf/scorecard/blob/main/docs/checks.md"
SCORECARD_REFERENCES = [
    "https://github.com/ossf/scorecard",
    "https://github.com/ossf/scorecard/blob/main/docs/checks.md",
]

CHECK_METADATA: dict[str, dict[str, Any]] = {
    "Dangerous-Workflow": {
        "category": "CI/CD Security",
        "scorecard_risk": "Critical",
        "taxonomy_id": "SC-DANGEROUS-WORKFLOW",
        "taxonomy_label": "Dangerous Workflow",
        "scope": "GitHub Actions workflows with dangerous trigger, checkout, or script-injection patterns",
        "entry_points": [".github/workflows"],
        "trust_boundaries": ["untrusted pull request or workflow event input -> privileged CI runner"],
        "sinks": ["workflow shell steps", "repository checkout", "GitHub token and secrets"],
        "review_questions": [
            "Do privileged workflow triggers execute code or inputs from untrusted contributors?",
            "Are GitHub context values interpolated directly into shell scripts?",
            "Can workflow changes expose repository secrets or write tokens?",
        ],
        "remediation": "Avoid pull_request_target or workflow_run patterns that execute untrusted code; pass untrusted context through environment variables or action inputs instead of shell interpolation.",
        "priority": 95,
    },
    "Token-Permissions": {
        "category": "GitHub Actions Permissions",
        "scorecard_risk": "High",
        "taxonomy_id": "SC-CICD-TOKEN-PERMISSIONS",
        "taxonomy_label": "CI/CD Token Permissions",
        "scope": "GitHub Actions workflow GITHUB_TOKEN permissions",
        "entry_points": [".github/workflows"],
        "trust_boundaries": ["workflow job -> repository contents, packages, checks, and security events"],
        "sinks": ["GITHUB_TOKEN", "repository write APIs", "package registries"],
        "review_questions": [
            "Are workflow permissions read-only by default?",
            "Are required write scopes declared only at the job that needs them?",
            "Could a compromised job push code, alter checks, or publish packages?",
        ],
        "remediation": "Set top-level workflow permissions to read-only or none and grant explicit job-level write scopes only where required.",
        "priority": 90,
    },
    "Pinned-Dependencies": {
        "category": "Supply Chain Hardening",
        "scorecard_risk": "Medium",
        "taxonomy_id": "SC-PINNED-DEPENDENCIES",
        "taxonomy_label": "Pinned Dependencies",
        "scope": "Build, release, and workflow dependencies that may be mutable",
        "entry_points": [".github/workflows", "Dockerfile", "scripts"],
        "trust_boundaries": ["external dependency source -> build or release execution"],
        "sinks": ["GitHub Actions", "container base images", "install scripts"],
        "review_questions": [
            "Are GitHub Actions pinned to immutable commit SHAs where appropriate?",
            "Are build and release dependencies pinned to exact versions or digests?",
            "Is dependency pinning paired with an update process?",
        ],
        "remediation": "Pin build and release dependencies to immutable versions or digests and use dependency update automation to keep pins current.",
        "priority": 65,
    },
    "Branch-Protection": {
        "category": "Repository Governance",
        "scorecard_risk": "High",
        "taxonomy_id": "SC-BRANCH-PROTECTION",
        "taxonomy_label": "Branch Protection",
        "scope": "Default and release branch protection settings",
        "entry_points": ["repository settings", ".github/workflows"],
        "trust_boundaries": ["contributor push or pull request -> protected branch"],
        "sinks": ["default branch", "release branches"],
        "review_questions": [
            "Do important branches prevent force pushes and deletion?",
            "Are required reviews and status checks enforced before merge?",
            "Are repository rulesets or branch protection rules documented for maintainers?",
        ],
        "remediation": "Enable branch protection or repository rulesets with required reviews, required status checks, and restrictions on destructive history changes.",
        "priority": 85,
    },
    "Code-Review": {
        "category": "Repository Governance",
        "scorecard_risk": "High",
        "taxonomy_id": "SC-CODE-REVIEW",
        "taxonomy_label": "Code Review",
        "scope": "Code review requirements for changes merged to protected branches",
        "entry_points": ["repository settings", "pull request workflow"],
        "trust_boundaries": ["proposed code change -> trusted branch"],
        "sinks": ["default branch", "release branches"],
        "review_questions": [
            "Are non-bot changes reviewed by a human before merge?",
            "Are code owners or domain experts required for sensitive areas?",
            "Can bot-only review paths bypass meaningful human review?",
        ],
        "remediation": "Require human review before merging pull requests and consider CODEOWNERS for security-sensitive files.",
        "priority": 85,
    },
    "Dependency-Update-Tool": {
        "category": "Dependency Maintenance",
        "scorecard_risk": "High",
        "taxonomy_id": "SC-DEPENDENCY-UPDATE",
        "taxonomy_label": "Dependency Update Tooling",
        "scope": "Automated dependency update and security update configuration",
        "entry_points": [".github/dependabot.yml", "renovate.json", "package manifests"],
        "trust_boundaries": ["upstream dependency advisory -> local dependency version"],
        "sinks": ["dependency manifests", "lockfiles", "release dependencies"],
        "review_questions": [
            "Is an automated dependency update tool configured for relevant ecosystems?",
            "Are generated dependency update PRs reviewed and merged in a timely manner?",
            "Are security-only updates enabled where supported?",
        ],
        "remediation": "Enable Dependabot, Renovate, or an equivalent dependency update process for all supported package ecosystems.",
        "priority": 80,
    },
    "Security-Policy": {
        "category": "Disclosure Governance",
        "scorecard_risk": "Medium",
        "taxonomy_id": "SC-SECURITY-POLICY",
        "taxonomy_label": "Security Policy",
        "scope": "Security policy and vulnerability disclosure process",
        "entry_points": ["SECURITY.md", ".github/SECURITY.md", "docs/SECURITY.md"],
        "trust_boundaries": ["external vulnerability reporter -> maintainer disclosure channel"],
        "sinks": ["vulnerability reports", "security advisories"],
        "review_questions": [
            "Is SECURITY.md present in a standard location?",
            "Does it describe supported versions and a private reporting channel?",
            "Does it define disclosure expectations or response timelines?",
        ],
        "remediation": "Add a SECURITY.md file that explains supported versions, private reporting channels, and coordinated disclosure expectations.",
        "priority": 60,
    },
    "SAST": {
        "category": "Static Analysis Coverage",
        "scorecard_risk": "Medium",
        "taxonomy_id": "SC-SAST",
        "taxonomy_label": "Static Analysis Coverage",
        "scope": "Static analysis coverage in CI or repository-integrated tooling",
        "entry_points": [".github/workflows", "code scanning configuration"],
        "trust_boundaries": ["source changes -> automated security analysis"],
        "sinks": ["CodeQL", "SAST results", "code scanning alerts"],
        "review_questions": [
            "Does CI run SAST for languages used by the repository?",
            "Are SAST alerts monitored and triaged?",
            "Does the SAST configuration cover pull requests and main branch changes?",
        ],
        "remediation": "Add a SAST workflow such as CodeQL or an equivalent tool and document alert triage ownership.",
        "priority": 60,
    },
    "Signed-Releases": {
        "category": "Release Integrity",
        "scorecard_risk": "High",
        "taxonomy_id": "SC-SIGNED-RELEASES",
        "taxonomy_label": "Signed Releases",
        "scope": "Release signatures, provenance, and verification guidance",
        "entry_points": ["release workflows", "release assets", "release documentation"],
        "trust_boundaries": ["release build -> downstream artifact consumers"],
        "sinks": ["release assets", "package registries", "container registries"],
        "review_questions": [
            "Are release artifacts signed or accompanied by provenance attestations?",
            "Can downstream users verify release artifacts against the source repository and tag?",
            "Are verification instructions documented?",
        ],
        "remediation": "Sign release artifacts or publish provenance attestations and document verification commands for consumers.",
        "priority": 85,
    },
}


def _reports_dir(run_dir: Path) -> Path:
    ctx = load_context(run_dir)
    return run_dir / ctx.get("reports_dir", "reports")


def _check_anchor(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _default_doc_url(name: str) -> str:
    return f"{CHECK_DOC_BASE}#{_check_anchor(name)}"


def _taxonomy_ref(meta: dict[str, Any]) -> dict[str, str]:
    return {
        "name": "Supply Chain Posture",
        "id": str(meta["taxonomy_id"]),
        "label": str(meta["taxonomy_label"]),
    }


def _bounded_text(value: Any) -> str:
    if isinstance(value, (dict, list)):
        text = json.dumps(value, sort_keys=True, ensure_ascii=False)
    else:
        text = "" if value is None else str(value)
    text = redact_text(text).replace("\r", " ").replace("\n", " ")
    return re.sub(r"\s+", " ", text).strip()


def _markdown_text(value: Any) -> str:
    text = _bounded_text(value)
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _coerce_score(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        if float(value) < 0:
            return None
        if float(value) > 10:
            return None
        return round(float(value), 2)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped or stripped in {"?", "N/A", "n/a", "null"}:
            return None
        try:
            parsed = float(stripped.split("/", 1)[0].strip())
        except ValueError:
            return None
        if parsed < 0:
            return None
        if parsed > 10:
            return None
        return round(parsed, 2)
    return None


def _first_present(data: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        if key in data and data[key] not in (None, ""):
            return data[key]
    return None


def _find_checks(parsed: Any) -> list[dict[str, Any]]:
    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, dict)]
    if not isinstance(parsed, dict):
        return []
    for key in ("checks", "Checks", "check_results", "checkResults", "CheckResults", "results", "Results"):
        value = parsed.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _documentation_url(check: dict[str, Any], name: str) -> str:
    direct = _first_present(check, ["documentation_url", "documentationUrl", "url"])
    if direct:
        return _bounded_text(direct)
    documentation = check.get("documentation") or check.get("Documentation")
    if isinstance(documentation, dict):
        value = _first_present(documentation, ["url", "URL", "link", "remediation"])
        if value:
            return _bounded_text(value)
    if isinstance(documentation, str) and documentation.startswith(("http://", "https://")):
        return _bounded_text(documentation)
    return _default_doc_url(name)


def _details(check: dict[str, Any]) -> list[str]:
    raw = _first_present(check, ["details", "Details", "warnings", "Warnings"])
    if raw is None:
        return []
    values: list[Any]
    if isinstance(raw, list):
        values = raw
    elif isinstance(raw, dict):
        values = [raw]
    else:
        values = [raw]
    details: list[str] = []
    for value in values:
        if isinstance(value, dict):
            value = _first_present(value, ["msg", "message", "text", "reason", "detail"]) or value
        text = _bounded_text(value)
        if text:
            details.append(text)
        if len(details) >= MAX_DETAILS:
            break
    return details


def _overall_score(parsed: Any) -> float | None:
    if isinstance(parsed, dict):
        score = _coerce_score(_first_present(parsed, ["score", "Score", "aggregate_score", "aggregateScore"]))
        if score is not None:
            return score
    return None


def _scorecard_version(parsed: Any) -> str:
    if not isinstance(parsed, dict):
        return ""
    scorecard = parsed.get("scorecard") or parsed.get("Scorecard")
    if isinstance(scorecard, dict):
        return _bounded_text(_first_present(scorecard, ["version", "Version", "commit", "Commit"]))
    return _bounded_text(_first_present(parsed, ["scorecard_version", "scorecardVersion", "version", "Version"]))


def _scanned_repo(parsed: Any) -> str:
    if not isinstance(parsed, dict):
        return ""
    repo = parsed.get("repo") or parsed.get("Repo")
    if isinstance(repo, dict):
        return _bounded_text(_first_present(repo, ["name", "Name", "url", "URL"]))
    return _bounded_text(repo)


def _raw_generated_at(parsed: Any) -> str:
    if not isinstance(parsed, dict):
        return ""
    return _bounded_text(_first_present(parsed, ["date", "Date", "generated_at", "generatedAt"]))


def _assessed_risk(scorecard_risk: str, score: float | None) -> str:
    if score is None:
        return "informational"
    if scorecard_risk == "Critical":
        if score <= SCORE_VERY_LOW_THRESHOLD:
            return "critical"
        if score <= SCORE_LOW_THRESHOLD:
            return "high"
        if score < 10:
            return "medium"
        return "informational"
    if scorecard_risk == "High":
        if score <= SCORE_LOW_THRESHOLD:
            return "high"
        if score < 10:
            return "medium"
        return "informational"
    if scorecard_risk == "Medium":
        if score <= SCORE_VERY_LOW_THRESHOLD:
            return "medium"
        if score <= SCORE_LOW_THRESHOLD:
            return "low"
        return "informational"
    if score <= SCORE_VERY_LOW_THRESHOLD:
        return "low"
    return "informational"


def _target_recommended(scorecard_risk: str, score: float | None) -> bool:
    if score is None:
        return False
    if scorecard_risk in {"Critical", "High"}:
        return score <= SCORE_LOW_THRESHOLD
    if scorecard_risk == "Medium":
        return score <= SCORE_VERY_LOW_THRESHOLD
    return False


def _normalize_check(check: dict[str, Any]) -> dict[str, Any]:
    name = _bounded_text(_first_present(check, ["name", "Name", "check", "Check", "check_name", "checkName"])) or "Unknown"
    score = _coerce_score(_first_present(check, ["score", "Score", "value", "Value"]))
    reason = _bounded_text(_first_present(check, ["reason", "Reason", "description", "Description", "summary", "Summary"]))
    meta = CHECK_METADATA.get(name, {})
    scorecard_risk = str(meta.get("scorecard_risk") or "Unknown")
    assessed_risk = _assessed_risk(scorecard_risk, score)
    taxonomy = _taxonomy_ref(meta) if meta else None
    remediation = _bounded_text(_first_present(check, ["remediation", "Remediation", "fix", "Fix"])) or str(meta.get("remediation") or "Review Scorecard documentation for remediation guidance.")
    normalized = {
        "name": name,
        "score": score,
        "score_display": "unknown" if score is None else f"{score:g}/10",
        "scorecard_risk": scorecard_risk,
        "risk": assessed_risk,
        "category": str(meta.get("category") or "Scorecard Posture"),
        "reason": reason,
        "details": _details(check),
        "documentation_url": _documentation_url(check, name),
        "remediation": remediation,
        "target_recommended": bool(meta and _target_recommended(scorecard_risk, score)),
        "taxonomy": taxonomy,
    }
    return normalized


def analyze_scorecard_posture(*, run_dir: Path, raw_path: Path, raw_result_ref: str) -> dict[str, Any]:
    ctx = load_context(run_dir)
    parse_error = ""
    parsed: Any = {}
    try:
        parsed = json.loads(raw_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - posture artifact should record bad scanner input safely
        parse_error = _bounded_text(exc)
    checks = [_normalize_check(item) for item in _find_checks(parsed)] if not parse_error else []
    target_checks = [check for check in checks if check.get("target_recommended")]
    low_or_medium_checks = [check for check in checks if check.get("risk") in {"critical", "high", "medium", "low"}]
    if parse_error:
        status = "invalid"
        summary = "Scorecard input could not be parsed as JSON. Generic scanner ingestion still keeps the raw local artifact and redacted normalized leads."
    elif not checks:
        status = "no_checks"
        summary = "No Scorecard checks were found in the ingested JSON."
    elif target_checks:
        status = "needs_review"
        summary = f"{len(target_checks)} low-scoring Scorecard check(s) should be converted into target-queue review items."
    elif low_or_medium_checks:
        status = "posture_observed"
        summary = f"{len(low_or_medium_checks)} Scorecard check(s) indicate posture gaps, but no high-priority target threshold was met."
    else:
        status = "passing"
        summary = "Mapped Scorecard checks did not identify low-scoring posture gaps."
    return {
        "schema_version": "1",
        "run_id": ctx.get("run_id", run_dir.name),
        "repo": ctx.get("repo", ""),
        "branch": ctx.get("branch", ""),
        "commit": ctx.get("commit", ""),
        "generated_at": utc_now(),
        "status": status,
        "summary": summary,
        "source": {
            "tool": "OpenSSF Scorecard",
            "raw_result_ref": raw_result_ref,
            "scorecard_version": _scorecard_version(parsed),
            "scorecard_generated_at": _raw_generated_at(parsed),
            "scanned_repo": _scanned_repo(parsed),
        },
        "overall_score": _overall_score(parsed),
        "parse_error": parse_error,
        "findings_created": 0,
        "checks": checks,
        "target_recommendations": [
            {"check": check.get("name"), "risk": check.get("risk"), "score": check.get("score"), "taxonomy": check.get("taxonomy")}
            for check in target_checks
        ],
        "references": SCORECARD_REFERENCES,
    }


def render_scorecard_markdown(data: dict[str, Any]) -> str:
    lines = [
        "# OpenSSF Scorecard supply-chain posture",
        "",
        f"Repository: `{data.get('repo', '')}`",
        f"Run ID: `{data.get('run_id', '')}`",
        f"Commit: `{data.get('commit', '')}`",
        f"Status: `{data.get('status', '')}`",
        f"Overall score: `{data.get('overall_score') if data.get('overall_score') is not None else 'unknown'}`",
        "",
        _markdown_text(data.get("summary", "")),
        "",
        "Scorecard output is treated as posture evidence and target-queue input, not as automatically confirmed findings.",
        f"Findings created by this deterministic ingestion step: `{data.get('findings_created', 0)}`",
        "",
        "## Source",
        "",
    ]
    source = data.get("source") or {}
    lines.extend(
        [
            f"- Raw local artifact: `{_markdown_text(source.get('raw_result_ref', ''))}`",
            f"- Scorecard version/commit: `{_markdown_text(source.get('scorecard_version') or 'unknown')}`",
            f"- Scorecard generated at: `{_markdown_text(source.get('scorecard_generated_at') or 'unknown')}`",
            f"- Scanned repository: `{_markdown_text(source.get('scanned_repo') or 'unknown')}`",
            "",
        ]
    )
    if data.get("parse_error"):
        lines.extend(["## Parse error", "", _markdown_text(data.get("parse_error")), ""])
    lines.extend(["## Checks", ""])
    checks = [check for check in data.get("checks") or [] if isinstance(check, dict)]
    if not checks:
        lines.append("No Scorecard checks were available.")
        lines.append("")
    for check in checks:
        lines.extend(
            [
                f"### `{check.get('name', '')}`",
                "",
                f"- Score: `{check.get('score_display', 'unknown')}`",
                f"- Scorecard risk: `{check.get('scorecard_risk', 'Unknown')}`",
                f"- Assessed risk: `{check.get('risk', 'informational')}`",
                f"- Category: {_markdown_text(check.get('category', ''))}",
                f"- Reason: {_markdown_text(check.get('reason') or 'not provided')}",
                f"- Remediation: {_markdown_text(check.get('remediation') or 'Review Scorecard documentation.')}",
                f"- Documentation/remediation link: {_markdown_text(check.get('documentation_url') or _default_doc_url(str(check.get('name', ''))))}",
                f"- Target recommended: {bool(check.get('target_recommended'))}",
            ]
        )
        details = check.get("details") or []
        if details:
            lines.append("- Details:")
            for detail in details:
                lines.append(f"  - {_markdown_text(detail)}")
        lines.append("")
    lines.extend(
        [
            "## References",
            "",
            "- OpenSSF Scorecard: https://github.com/ossf/scorecard",
            "- Scorecard check documentation: https://github.com/ossf/scorecard/blob/main/docs/checks.md",
            "",
        ]
    )
    return "\n".join(lines)


def write_scorecard_posture_artifacts(*, run_dir: Path, raw_path: Path, raw_result_ref: str) -> dict[str, Any]:
    reports = _reports_dir(run_dir)
    reports.mkdir(parents=True, exist_ok=True)
    data = analyze_scorecard_posture(run_dir=run_dir, raw_path=raw_path, raw_result_ref=raw_result_ref)
    write_json(reports / "supply-chain-posture.json", data)
    (reports / "supply-chain-posture.md").write_text(render_scorecard_markdown(data), encoding="utf-8")
    return data


def _target_id(index: int) -> str:
    return f"TGT-SCORECARD-{index:03d}"


def _target_note(check: dict[str, Any]) -> str:
    pieces = [
        f"Generated from reports/supply-chain-posture.json. OpenSSF Scorecard check: {check.get('name', '')}.",
        f"Score: {check.get('score_display', 'unknown')}.",
        f"Reason: {check.get('reason') or 'not provided'}.",
        f"Remediation: {check.get('remediation') or 'Review Scorecard documentation.'}",
        f"Documentation: {check.get('documentation_url') or ''}",
    ]
    note = " ".join(piece for piece in pieces if piece)
    return note[:MAX_NOTE_CHARS] + ("...<truncated>" if len(note) > MAX_NOTE_CHARS else "")


def append_scorecard_posture_targets(run_dir: Path) -> list[dict[str, Any]]:
    reports = _reports_dir(run_dir)
    data = load_json(reports / "supply-chain-posture.json", {}) or {}
    checks = [check for check in data.get("checks") or [] if isinstance(check, dict) and check.get("target_recommended")]
    targets = load_targets(run_dir)
    existing_scopes = {str(target.get("scope")) for target in targets if isinstance(target, dict)}
    existing_notes = {str(target.get("notes")) for target in targets if isinstance(target, dict)}
    existing_ids = {str(target.get("id")) for target in targets if isinstance(target, dict)}
    next_index = 1
    added: list[dict[str, Any]] = []
    for check in checks:
        name = str(check.get("name") or "Unknown")
        meta = CHECK_METADATA.get(name, {})
        scope = f"OpenSSF Scorecard: {name}"
        if scope in existing_scopes or any(f"OpenSSF Scorecard check: {name}." in note for note in existing_notes):
            continue
        while _target_id(next_index) in existing_ids:
            next_index += 1
        target = {
            "id": _target_id(next_index),
            "category": str(meta.get("category") or check.get("category") or "Supply Chain Posture"),
            "title": f"Review OpenSSF Scorecard {name} posture",
            "risk": str(check.get("risk") or "medium"),
            "priority": int(meta.get("priority") or 60),
            "status": "queued",
            "scope": scope,
            "entry_points": list(meta.get("entry_points") or ["repository posture"]),
            "trust_boundaries": list(meta.get("trust_boundaries") or ["repository configuration -> downstream users"]),
            "sinks": list(meta.get("sinks") or ["supply-chain posture"]),
            "security_invariants": [
                "Scorecard posture gaps should be reviewed in repository context before promotion to findings.",
                "Scanner-derived posture data must not expose raw tokens or secrets in target notes.",
            ],
            "review_questions": list(meta.get("review_questions") or ["Does repository context confirm the Scorecard posture gap?", "What bounded remediation should be prioritized?"]),
            "candidate_files": list(meta.get("entry_points") or []),
            "recommended_mode": "exec",
            "notes": _target_note(check),
            "taxonomies": [check.get("taxonomy") or _taxonomy_ref(meta)] if meta else [],
        }
        targets.append(target)
        added.append(target)
        existing_ids.add(target["id"])
        existing_scopes.add(scope)
        existing_notes.add(str(target["notes"]))
        next_index += 1
    if added:
        write_targets(run_dir, targets)
    return added
