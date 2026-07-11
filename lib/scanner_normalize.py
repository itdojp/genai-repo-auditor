from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

MAX_LEADS = 200
MAX_EVIDENCE_CHARS = 500
MAX_TEXT_BYTES = 64 * 1024

REDACTION_PATTERNS: Tuple[Tuple[str, re.Pattern[str]], ...] = (
    ("private-key", re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?(?:-----END [A-Z0-9 ]*PRIVATE KEY-----|$)", re.DOTALL)),
    ("github-token", re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}")),
    ("stripe-secret", re.compile(r"sk_(?:live|test)_[A-Za-z0-9]{8,}")),
    ("aws-access-key", re.compile(r"(?:AKIA|ASIA)[0-9A-Z]{16}")),
    ("slack-token", re.compile(r"xox[baprs]-[A-Za-z0-9-]{20,}")),
)


def _mask_secret(value: str) -> str:
    if len(value) <= 8:
        return "<REDACTED>"
    if value.startswith("sk_"):
        prefix = value.split("_", 2)[:2]
        return "_".join(prefix) + "_..." + value[-4:]
    if value.startswith(("ghp_", "gho_", "ghu_", "ghs_", "ghr_")):
        return value[:4] + "..." + value[-4:]
    if value.startswith("AKIA"):
        return "AKIA..." + value[-4:]
    if value.startswith("xox"):
        return value[:6] + "..." + value[-4:]
    return value[:4] + "..." + value[-4:]


def redact_text_with_count(value: object) -> tuple[str, int]:
    text = "" if value is None else str(value)
    redaction_count = 0
    for label, pattern in REDACTION_PATTERNS:
        if label == "private-key":
            text, count = pattern.subn("<REDACTED:private-key>", text)
        else:
            text, count = pattern.subn(lambda m: _mask_secret(m.group(0)), text)
        redaction_count += count
    if len(text) > MAX_EVIDENCE_CHARS:
        text = text[:MAX_EVIDENCE_CHARS] + "...<truncated>"
    return text, redaction_count


def redact_text(value: object) -> str:
    return redact_text_with_count(value)[0]


def redact_sensitive_field_with_count(value: object) -> tuple[str, int]:
    text = "" if value is None else str(value)
    redacted, count = redact_text_with_count(text)
    if redacted == text and text:
        return "<REDACTED:scanner-secret>", 1
    return redacted, count


def redact_sensitive_field(value: object) -> str:
    return redact_sensitive_field_with_count(value)[0]


def sha256_short(value: str, length: int = 24) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()[:length]


def first_value(data: Dict[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        if key in data and data[key] not in (None, ""):
            return data[key]
    return None


def nested_get(data: Dict[str, Any], path: Iterable[str]) -> Any:
    cur: Any = data
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    return cur


def coerce_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def iter_result_objects(parsed: Any) -> List[Dict[str, Any]]:
    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, dict)]
    if not isinstance(parsed, dict):
        return []
    for key in ("results", "findings", "Issues", "issues", "secrets"):
        value = parsed.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    sarif_runs = parsed.get("runs")
    if isinstance(sarif_runs, list):
        out: List[Dict[str, Any]] = []
        for run in sarif_runs:
            if isinstance(run, dict) and isinstance(run.get("results"), list):
                out.extend(item for item in run["results"] if isinstance(item, dict))
        return out
    return [parsed]


def normalize_result(tool: str, item: Dict[str, Any], index: int, raw_result_ref: str) -> Dict[str, Any]:
    raw_rule_id = first_value(item, ["RuleID", "rule_id", "ruleId", "check_id", "DetectorName", "detector_name", "type"]) or "unknown"
    rule_id, rule_id_redactions = redact_text_with_count(raw_rule_id)
    raw_severity = str(first_value(item, ["Severity", "severity", "level"]) or ("high" if tool.lower() in {"gitleaks", "trufflehog"} else "unknown")).lower()
    severity, severity_redactions = redact_text_with_count(raw_severity)
    path = first_value(item, ["File", "file", "path", "Path", "uri"])
    path = path or nested_get(item, ["SourceMetadata", "Data", "Git", "file"])
    path = path or nested_get(item, ["location", "path"])
    if not path and isinstance(item.get("locations"), list) and item["locations"]:
        first_location = item["locations"][0]
        if isinstance(first_location, dict):
            path = nested_get(first_location, ["physicalLocation", "artifactLocation", "uri"])
    path, path_redactions = redact_text_with_count(path or "")
    line = coerce_int(first_value(item, ["StartLine", "Line", "line", "start_line"]))
    if line is None:
        line = coerce_int(nested_get(item, ["SourceMetadata", "Data", "Git", "line"]))
    if line is None:
        line = coerce_int(nested_get(item, ["start", "line"]))
    if line is None and isinstance(item.get("locations"), list) and item["locations"]:
        first_location = item["locations"][0]
        if isinstance(first_location, dict):
            line = coerce_int(nested_get(first_location, ["physicalLocation", "region", "startLine"]))

    sensitive_evidence = first_value(item, ["Secret", "secret", "Raw", "raw"])
    evidence_source = sensitive_evidence
    if evidence_source is None:
        evidence_source = first_value(item, ["Match", "match", "Snippet", "snippet", "message", "Message"])
    if evidence_source is None and "extra" in item and isinstance(item["extra"], dict):
        evidence_source = first_value(item["extra"], ["message", "metadata", "lines"])
    if sensitive_evidence is not None:
        redacted_evidence, evidence_redactions = redact_sensitive_field_with_count(sensitive_evidence)
    else:
        redacted_evidence, evidence_redactions = redact_text_with_count(
            evidence_source if evidence_source is not None else json.dumps(item, sort_keys=True)[:MAX_EVIDENCE_CHARS]
        )
    redaction_count = rule_id_redactions + severity_redactions + path_redactions + evidence_redactions
    fingerprint_source = "|".join([tool, str(rule_id), path, str(line or ""), redacted_evidence, str(index)])
    return {
        "tool": tool,
        "rule_id": rule_id,
        "severity": severity,
        "path": path,
        "line": line,
        "redacted_evidence": redacted_evidence,
        "fingerprint": sha256_short(fingerprint_source),
        "raw_result_ref": raw_result_ref,
        "raw_result_index": index,
        "redaction_count": redaction_count,
    }


def normalize_scanner_file(*, tool: str, raw_path: Path, raw_result_ref: str) -> Dict[str, Any]:
    raw_bytes = raw_path.read_bytes()
    raw_size = len(raw_bytes)
    full_text = raw_bytes.decode("utf-8", errors="replace")
    text_sample = full_text[:MAX_TEXT_BYTES]
    fmt = raw_path.suffix.lower().lstrip(".")
    leads: List[Dict[str, Any]] = []
    parse_error = ""
    try:
        parsed = json.loads(full_text)
        results = iter_result_objects(parsed)
        for index, item in enumerate(results[:MAX_LEADS]):
            leads.append(normalize_result(tool, item, index, raw_result_ref))
        truncated_input = False
        truncated_results = len(results) > MAX_LEADS
    except Exception as exc:  # noqa: BLE001
        parse_error = str(exc)
        jsonl_results: List[Dict[str, Any]] = []
        for line in full_text.splitlines():
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except Exception:  # noqa: BLE001
                jsonl_results = []
                break
            if isinstance(item, dict):
                jsonl_results.append(item)
        if jsonl_results:
            parse_error = ""
            for index, item in enumerate(jsonl_results[:MAX_LEADS]):
                leads.append(normalize_result(tool, item, index, raw_result_ref))
            truncated_input = False
            truncated_results = len(jsonl_results) > MAX_LEADS
        else:
            truncated_input = raw_size > MAX_TEXT_BYTES
            truncated_results = False
            redacted, sample_redaction_count = redact_text_with_count(text_sample)
            leads.append({
                "tool": tool,
                "rule_id": "unparsed-text",
                "severity": "unknown",
                "path": "",
                "line": None,
                "redacted_evidence": redacted,
                "fingerprint": sha256_short("|".join([tool, raw_result_ref, redacted])),
                "raw_result_ref": raw_result_ref,
                "raw_result_index": 0,
                "redaction_count": sample_redaction_count,
            })
    redaction_count = sum(
        int(lead.get("redaction_count") or 0)
        for lead in leads
        if isinstance(lead, dict) and isinstance(lead.get("redaction_count"), int)
    )
    return {
        "tool": tool,
        "raw_result_ref": raw_result_ref,
        "raw_bytes": raw_size,
        "format": fmt or "unknown",
        "normalization": {
            "max_leads": MAX_LEADS,
            "max_evidence_chars": MAX_EVIDENCE_CHARS,
            "max_text_bytes": MAX_TEXT_BYTES,
            "input_truncated": truncated_input,
            "results_truncated": truncated_results,
            "parse_error": parse_error,
            "redaction_count": redaction_count,
        },
        "leads": leads,
    }
