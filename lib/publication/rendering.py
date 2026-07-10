from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple

from report_safety import safe_issue_body_path


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def slug(s: str, *, max_len: int = 50) -> str:
    out = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return out[:max_len] or "unknown"


def loc_file_line(loc: Any) -> Tuple[str, Optional[Any], Optional[Any]]:
    if not isinstance(loc, dict):
        return str(loc), None, None
    file_ = loc.get("file") or loc.get("path") or ""
    line = loc.get("line") or loc.get("start_line")
    end = loc.get("end_line")
    return str(file_), line, end


def stable_fingerprint(repo: str, finding: Dict[str, Any]) -> str:
    existing = str(finding.get("fingerprint") or "").strip()
    if existing and existing.lower() not in {"n/a", "none", "unknown"}:
        return existing
    locs = finding.get("affected_locations") or []
    loc_str = ";".join(f"{loc_file_line(x)[0]}:{loc_file_line(x)[1] or ''}" for x in locs)
    raw = "|".join([
        repo,
        str(finding.get("category", "")),
        str(finding.get("title", "")),
        loc_str,
        str(finding.get("entry_point", "")),
        str(finding.get("trust_boundary", "")),
        str(finding.get("call_path") or finding.get("source_to_sink") or ""),
        str(finding.get("root_cause", "")),
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def render_locations(locs: Iterable[Any]) -> str:
    lines = []
    for loc in locs:
        file_, line, end = loc_file_line(loc)
        if line and end and str(end) != str(line):
            lines.append(f"- `{file_}:{line}-{end}`")
        elif line:
            lines.append(f"- `{file_}:{line}`")
        elif file_:
            lines.append(f"- `{file_}`")
    return "\n".join(lines) if lines else "- Not specified"


def render_body(repo: str, run_id: str, commit: str, finding: Dict[str, Any], fingerprint: str, run_dir: Path) -> str:
    issue_body_file = str(finding.get("issue_body_file") or "")
    if issue_body_file:
        p = safe_issue_body_path(run_dir, issue_body_file)
        body = p.read_text(encoding="utf-8")
        if "genai-repo-auditor:fingerprint=" not in body and "gra-fingerprint:" not in body:
            body += f"\n\n<!-- genai-repo-auditor:fingerprint={fingerprint} -->\n"
        return body

    title = str(finding.get("title") or "Security finding")
    call_path = finding.get("call_path") or finding.get("source_to_sink") or "Not specified"
    body = f"""# {title}

<!-- genai-repo-auditor:fingerprint={fingerprint} -->

## Summary

{finding.get('root_cause') or finding.get('evidence') or 'See audit report.'}

## Severity / confidence / status

- Severity: {finding.get('severity', 'Unknown')}
- Confidence: {finding.get('confidence', 'Unknown')}
- Status: {finding.get('status', 'Unknown')}
- Category: {finding.get('category', 'Unknown')}

## Affected code

{render_locations(finding.get('affected_locations') or [])}

## Entry point

{finding.get('entry_point', 'Not specified')}

## Trust boundary

{finding.get('trust_boundary', 'Not specified')}

## Call path / source-to-sink

{call_path}

## Evidence

{finding.get('evidence', 'See audit report.')}

## Impact

{finding.get('impact', 'Not specified')}

## Minimal remediation

{finding.get('minimal_remediation', 'Not specified')}

## Regression test

{finding.get('regression_test_idea', 'Not specified')}

## Audit metadata

- Repository: `{repo}`
- Run ID: `{run_id}`
- Commit: `{commit}`
- Finding ID: `{finding.get('id', 'Unknown')}`
"""
    return body
