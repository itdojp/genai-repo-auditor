from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Iterable

from gralib import load_context, load_json, load_targets, utc_now, write_json, write_targets

WORKFLOW_SUFFIXES = {".yml", ".yaml"}
DOC_SUFFIXES = {".md", ".mdx", ".txt"}
MAX_TEXT_BYTES = 512 * 1024

CATEGORY_PATTERNS: list[tuple[str, str]] = [
    (
        "release",
        r"(softprops/action-gh-release|upload-release-asset|gh\s+release|create-release|release-assets?|"
        r"\bon:\s*release\b|drafts? a release)",
    ),
    (
        "package_publish",
        r"(npm\s+publish|twine\s+upload|pypi|cargo\s+publish|mvn\s+deploy|gradle\s+publish|"
        r"nuget\s+push|rubygems|gem\s+push|packages:\s*write)",
    ),
    (
        "container",
        r"(docker/(build-push-action|login-action)|docker\s+push|buildx|ghcr\.io|container image|"
        r"push-to-registry:\s*true)",
    ),
    (
        "binary_or_archive",
        r"(actions/upload-artifact|go\s+build|cargo\s+build\s+--release|pyinstaller|make\s+release|"
        r"\btar\b|\bzip\b|dist/|build/)",
    ),
]

ATTESTATION_RE = re.compile(
    r"(actions/attest(@|[-_a-z0-9/]*@)|actions/attest-build-provenance|actions/attest-sbom|"
    r"gh\s+attestation|cosign\s+attest|slsa-framework/)",
    re.IGNORECASE,
)
SBOM_ATTESTATION_RE = re.compile(r"(sbom-path\s*:|actions/attest-sbom)", re.IGNORECASE)
SBOM_GENERATION_RE = re.compile(r"(cyclonedx|spdx|syft|anchore/sbom-action|sbom)", re.IGNORECASE)
VERIFICATION_GUIDANCE_RE = re.compile(r"(gh\s+attestation\s+verify|attestation verify|slsa|provenance)", re.IGNORECASE)


def _repo_dir(run_dir: Path) -> Path:
    ctx = load_context(run_dir)
    return run_dir / ctx.get("target_repo_dir", "repo")


def _reports_dir(run_dir: Path) -> Path:
    ctx = load_context(run_dir)
    return run_dir / ctx.get("reports_dir", "reports")


def _repo_display_prefix(run_dir: Path, repo_dir: Path) -> str:
    try:
        return repo_dir.relative_to(run_dir).as_posix()
    except ValueError:
        return repo_dir.name


def _display_path(run_dir: Path, repo_dir: Path, path: Path) -> str:
    return f"{_repo_display_prefix(run_dir, repo_dir)}/{path.relative_to(repo_dir).as_posix()}"


def _safe_read_text(path: Path) -> str:
    try:
        if path.is_symlink() or path.stat().st_size > MAX_TEXT_BYTES:
            return ""
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _workflow_files(repo_dir: Path) -> Iterable[Path]:
    workflows_dir = repo_dir / ".github" / "workflows"
    if not workflows_dir.exists() or workflows_dir.is_symlink():
        return []
    workflows = []
    for path in workflows_dir.iterdir():
        if path.is_file() and not path.is_symlink() and path.suffix.lower() in WORKFLOW_SUFFIXES:
            workflows.append(path)
    return sorted(workflows, key=lambda p: p.name)


def _doc_files(repo_dir: Path) -> Iterable[Path]:
    candidates: list[Path] = []
    for name in ["README.md", "README.MD", "SECURITY.md", "RELEASE.md", "CHANGELOG.md"]:
        path = repo_dir / name
        if path.is_file() and not path.is_symlink():
            candidates.append(path)
    docs_dir = repo_dir / "docs"
    if docs_dir.exists() and not docs_dir.is_symlink():
        for root, dirnames, filenames in os.walk(docs_dir, onerror=lambda _error: None):
            root_path = Path(root)
            dirnames[:] = sorted(dirname for dirname in dirnames if not (root_path / dirname).is_symlink())
            for filename in sorted(filenames):
                path = root_path / filename
                if path.is_file() and not path.is_symlink() and path.suffix.lower() in DOC_SUFFIXES:
                    candidates.append(path)
    return sorted(set(candidates), key=lambda p: p.relative_to(repo_dir).as_posix())


def _permission_value(text: str, name: str) -> str:
    pattern = re.compile(rf"^\s*{re.escape(name)}\s*:\s*([A-Za-z0-9_-]+)\s*(?:#.*)?$", re.IGNORECASE | re.MULTILINE)
    match = pattern.search(text)
    return match.group(1).lower() if match else ""


def _permission_summary(text: str) -> dict[str, str]:
    return {
        "id-token": _permission_value(text, "id-token"),
        "contents": _permission_value(text, "contents"),
        "attestations": _permission_value(text, "attestations"),
        "packages": _permission_value(text, "packages"),
        "artifact-metadata": _permission_value(text, "artifact-metadata"),
    }


def _categories(text: str) -> list[str]:
    found = []
    for category, pattern in CATEGORY_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            found.append(category)
    return found


def _permission_gaps(categories: list[str], permissions: dict[str, str], has_attestation: bool) -> list[str]:
    if not categories:
        return []
    required = {
        "id-token": "write",
        "contents": "read",
        "attestations": "write",
    }
    if "container" in categories and has_attestation:
        required["packages"] = "write"
    gaps = []
    for name, expected in required.items():
        observed = permissions.get(name, "")
        if observed != expected:
            gaps.append(f"{name}: expected {expected}, observed {observed or 'missing'}")
    return gaps


def _recommendations(
    *,
    categories: list[str],
    has_attestation: bool,
    has_sbom_generation: bool,
    has_sbom_attestation: bool,
    permission_gaps: list[str],
) -> list[str]:
    if not categories:
        return []
    recommendations = []
    if not has_attestation:
        recommendations.append("Add artifact provenance attestations for published release, package, container, or binary artifacts.")
    if has_sbom_generation and not has_sbom_attestation:
        recommendations.append("If SBOMs are generated, attest them with actions/attest and the sbom-path input.")
    if permission_gaps:
        recommendations.append("Align workflow token permissions with attestation requirements before publishing artifacts.")
    if "container" in categories and not has_attestation:
        recommendations.append("For container images, attest the image digest and push the attestation to the registry.")
    return recommendations


def _taxonomy_refs(permission_gaps: list[str]) -> list[dict[str, str]]:
    refs = [{"name": "Supply Chain Posture", "id": "SC-ARTIFACT-ATTESTATION", "label": "Artifact Attestation"}]
    if permission_gaps:
        refs.append({"name": "Supply Chain Posture", "id": "SC-CICD-TOKEN-PERMISSIONS", "label": "CI/CD Token Permissions"})
    return refs


def _workflow_posture(run_dir: Path, repo_dir: Path, path: Path) -> dict[str, Any]:
    text = _safe_read_text(path)
    categories = _categories(text)
    has_attestation = bool(ATTESTATION_RE.search(text))
    has_sbom_attestation = bool(SBOM_ATTESTATION_RE.search(text))
    has_sbom_generation = bool(SBOM_GENERATION_RE.search(text))
    permissions = _permission_summary(text)
    permission_gaps = _permission_gaps(categories, permissions, has_attestation)
    recommendations = _recommendations(
        categories=categories,
        has_attestation=has_attestation,
        has_sbom_generation=has_sbom_generation,
        has_sbom_attestation=has_sbom_attestation,
        permission_gaps=permission_gaps,
    )
    return {
        "path": _display_path(run_dir, repo_dir, path),
        "categories": categories,
        "publishes_artifacts": bool(categories),
        "has_attestation": has_attestation,
        "has_sbom_generation": has_sbom_generation,
        "has_sbom_attestation": has_sbom_attestation,
        "permissions": permissions,
        "permission_gaps": permission_gaps,
        "risk": "medium" if recommendations else "informational",
        "recommendations": recommendations,
        "taxonomies": _taxonomy_refs(permission_gaps) if categories else [],
    }


def _release_docs(run_dir: Path, repo_dir: Path) -> dict[str, Any]:
    docs = []
    verification_guidance = False
    for path in _doc_files(repo_dir):
        text = _safe_read_text(path)
        if VERIFICATION_GUIDANCE_RE.search(text):
            verification_guidance = True
            docs.append(_display_path(run_dir, repo_dir, path))
    return {"verification_guidance": verification_guidance, "paths": docs}


def analyze_provenance_posture(run_dir: Path) -> dict[str, Any]:
    ctx = load_context(run_dir)
    repo_dir = _repo_dir(run_dir)
    workflows = [_workflow_posture(run_dir, repo_dir, path) for path in _workflow_files(repo_dir)]
    applicable = [workflow for workflow in workflows if workflow["publishes_artifacts"]]
    needs_review = [workflow for workflow in applicable if workflow["recommendations"]]
    if not applicable:
        status = "not_applicable"
        summary = "No release, package, container, or binary artifact publishing workflows were detected."
    elif needs_review:
        status = "needs_review"
        summary = f"{len(needs_review)} artifact-publishing workflow(s) need provenance posture review."
    else:
        status = "attested"
        summary = "Artifact-publishing workflows include attestation posture signals and required permissions."
    return {
        "schema_version": "1",
        "run_id": ctx.get("run_id", run_dir.name),
        "repo": ctx.get("repo", ""),
        "branch": ctx.get("branch", ""),
        "commit": ctx.get("commit", ""),
        "generated_at": utc_now(),
        "status": status,
        "summary": summary,
        "workflows": workflows,
        "release_docs": _release_docs(run_dir, repo_dir),
        "references": [
            "https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations",
            "https://github.com/actions/attest",
        ],
    }


def render_provenance_markdown(data: dict[str, Any]) -> str:
    lines = [
        "# Artifact attestation and release provenance posture",
        "",
        f"Repository: `{data.get('repo', '')}`",
        f"Run ID: `{data.get('run_id', '')}`",
        f"Commit: `{data.get('commit', '')}`",
        f"Status: `{data.get('status', '')}`",
        "",
        str(data.get("summary", "")),
        "",
        "This report is a supply-chain posture review aid. Missing attestations are not automatically high-severity findings.",
        "",
        "## Workflow summary",
        "",
    ]
    workflows = data.get("workflows") or []
    if not workflows:
        lines.append("- No GitHub Actions workflow files were found under the target repository.")
    for workflow in workflows:
        lines.extend(
            [
                f"### `{workflow.get('path')}`",
                "",
                f"- Categories: {', '.join(workflow.get('categories') or []) or 'not applicable'}",
                f"- Attestation detected: {bool(workflow.get('has_attestation'))}",
                f"- SBOM generation detected: {bool(workflow.get('has_sbom_generation'))}",
                f"- SBOM attestation detected: {bool(workflow.get('has_sbom_attestation'))}",
                f"- Permission gaps: {', '.join(workflow.get('permission_gaps') or []) or 'none detected'}",
            ]
        )
        for recommendation in workflow.get("recommendations") or []:
            lines.append(f"- Recommendation: {recommendation}")
        lines.append("")
    docs = data.get("release_docs") or {}
    lines.extend(
        [
            "## Verification guidance",
            "",
            f"- Release verification guidance detected in docs: {bool(docs.get('verification_guidance'))}",
            "- Online verification normally uses `gh attestation verify` against GitHub's attestation service.",
            "- Offline or air-gapped verification requires separately exported attestations and trust material; do not assume online commands work offline.",
            "",
            "## Remediation examples",
            "",
            "Binary artifact provenance:",
            "",
            "```yaml",
            "permissions:",
            "  id-token: write",
            "  contents: read",
            "  attestations: write",
            "steps:",
            "  - uses: actions/attest@v4",
            "    with:",
            "      subject-path: dist/app.tar.gz",
            "```",
            "",
            "Container image provenance:",
            "",
            "```yaml",
            "permissions:",
            "  id-token: write",
            "  contents: read",
            "  attestations: write",
            "  packages: write",
            "steps:",
            "  - uses: actions/attest@v4",
            "    with:",
            "      subject-name: ghcr.io/OWNER/IMAGE",
            "      subject-digest: ${{ steps.build.outputs.digest }}",
            "      push-to-registry: true",
            "```",
            "",
            "SBOM attestation:",
            "",
            "```yaml",
            "steps:",
            "  - uses: actions/attest@v4",
            "    with:",
            "      subject-path: dist/app.tar.gz",
            "      sbom-path: sbom.spdx.json",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def write_provenance_posture_artifacts(run_dir: Path) -> dict[str, Any]:
    reports = _reports_dir(run_dir)
    reports.mkdir(parents=True, exist_ok=True)
    data = analyze_provenance_posture(run_dir)
    write_json(reports / "provenance-posture.json", data)
    (reports / "PROVENANCE_POSTURE.md").write_text(render_provenance_markdown(data), encoding="utf-8")
    return data


def _target_id(index: int) -> str:
    return f"TGT-PROVENANCE-{index:03d}"


def append_provenance_posture_targets(run_dir: Path) -> list[dict[str, Any]]:
    reports = _reports_dir(run_dir)
    data = load_json(reports / "provenance-posture.json", {}) or {}
    workflows = [workflow for workflow in data.get("workflows") or [] if isinstance(workflow, dict)]
    targets = load_targets(run_dir)
    existing_scopes = {str(target.get("scope")) for target in targets if isinstance(target, dict)}
    existing_ids = {str(target.get("id")) for target in targets if isinstance(target, dict)}
    next_index = 1
    added: list[dict[str, Any]] = []
    for workflow in workflows:
        recommendations = workflow.get("recommendations") or []
        scope = str(workflow.get("path") or "")
        if not recommendations or not scope or scope in existing_scopes:
            continue
        while _target_id(next_index) in existing_ids:
            next_index += 1
        target = {
            "id": _target_id(next_index),
            "category": "Release Provenance",
            "title": f"Review artifact attestation posture for {scope}",
            "risk": "medium",
            "priority": 60,
            "status": "queued",
            "scope": scope,
            "entry_points": [scope],
            "trust_boundaries": ["source repository workflow -> published artifact consumers"],
            "sinks": ["release assets", "packages", "container registries"],
            "security_invariants": [
                "Published artifacts should be attributable to a trusted workflow and commit.",
                "Attestation token permissions should be least privilege and explicit.",
            ],
            "review_questions": [
                "Does this workflow publish artifacts consumed outside the repository?",
                "Are provenance and SBOM attestations generated for the published artifacts?",
                "Are id-token, contents, attestations, and package permissions scoped appropriately?",
            ],
            "candidate_files": [scope],
            "recommended_mode": "exec",
            "notes": "Generated from reports/provenance-posture.json. " + " ".join(str(item) for item in recommendations),
            "taxonomies": workflow.get("taxonomies") or [
                {"name": "Supply Chain Posture", "id": "SC-ARTIFACT-ATTESTATION", "label": "Artifact Attestation"}
            ],
        }
        targets.append(target)
        added.append(target)
        existing_ids.add(target["id"])
        existing_scopes.add(scope)
        next_index += 1
    if added:
        write_targets(run_dir, targets)
    return added
