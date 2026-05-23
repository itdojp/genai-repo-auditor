from __future__ import annotations

import os
import re
from contextlib import suppress
from pathlib import Path
from typing import Any, Iterable

from gralib import load_context, load_json, utc_now, write_json, load_targets, write_targets

MCP_CONFIG_PATHS = {
    ".mcp.json",
    ".vscode/mcp.json",
    ".cursor/mcp.json",
    "claude_desktop_config.json",
    "mcp.json",
    "mcp-servers.json",
}
AGENT_INSTRUCTION_PATHS = {
    "AGENTS.md",
    ".github/copilot-instructions.md",
    "CLAUDE.md",
    "GEMINI.md",
    ".clinerules",
    ".cursorrules",
    ".windsurfrules",
    ".continue/config.json",
}
AGENT_INSTRUCTION_PARTS = (
    ".cursor/rules/",
    ".windsurf/rules/",
    ".continue/rules/",
    ".github/instructions/",
)
TEXT_SUFFIXES = {
    "",
    ".cfg",
    ".conf",
    ".config",
    ".go",
    ".js",
    ".json",
    ".jsonc",
    ".jsx",
    ".j2",
    ".jinja",
    ".jinja2",
    ".mjs",
    ".md",
    ".mdc",
    ".py",
    ".rb",
    ".rs",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}
SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "target",
    "vendor",
}
MAX_FILE_BYTES = 512 * 1024
TOKEN_START = r"(?<![A-Za-z0-9_])"
TOKEN_END = r"(?![A-Za-z0-9_])"

CAPABILITY_PATTERNS: list[tuple[str, str]] = [
    ("shell", rf"{TOKEN_START}(shell|bash|sh|zsh|powershell|cmd\.exe|exec|spawn|subprocess|child_process|terminal){TOKEN_END}"),
    (
        "filesystem",
        rf"({TOKEN_START}(filesystem|file system|readfile|writefile|root_path|workspace){TOKEN_END}|fs\.|path\.|/etc/|/var/|/home/)",
    ),
    ("network", rf"{TOKEN_START}(https?|fetch|request|axios|curl|wget|url|websocket|sse|network){TOKEN_END}"),
    ("git", rf"{TOKEN_START}(git|commit|push|pull request|merge request|branch){TOKEN_END}"),
    ("github", rf"({TOKEN_START}(github|issues?|pull requests?|secrets?){TOKEN_END}|(^|\s)gh\s+)"),
    ("email", rf"{TOKEN_START}(email|smtp|sendgrid|mailgun){TOKEN_END}"),
    ("slack", rf"{TOKEN_START}(slack|webhook){TOKEN_END}"),
    ("ticket", rf"{TOKEN_START}(jira|ticket|linear|incident){TOKEN_END}"),
    ("deployment", rf"{TOKEN_START}(deploy|release|kubectl|terraform|cloudformation|aws|gcp|azure){TOKEN_END}"),
    ("memory", rf"{TOKEN_START}(memory|vector|embedding|chroma|pinecone|qdrant|weaviate|faiss|milvus|pgvector){TOKEN_END}"),
]
AI_SDK_PATTERNS: list[tuple[str, str]] = [
    ("OpenAI", r"\b(openai|from openai import|OpenAI\(|AzureOpenAI|@openai/)\b"),
    ("Anthropic", r"\b(anthropic|Claude|@anthropic-ai/)\b"),
    ("Gemini", r"\b(gemini|google\.generativeai|@google/generative-ai|vertexai)\b"),
    ("Azure AI", r"\b(azure\.ai|AzureOpenAI|azure-ai)\b"),
    ("OpenRouter", r"\b(openrouter|openrouter\.ai)\b"),
]
PROMPT_PATTERNS = ("prompt", "system", "developer", "instruction")
SUSPICIOUS_INSTRUCTION_RE = re.compile(
    r"(ignore (all )?(previous|prior|system)|print secrets?|exfiltrat|override (the )?(policy|instructions)|create (a )?github issue)",
    re.IGNORECASE,
)
WILDCARD_SCOPE_RE = re.compile(r"(allow[_-]?all|unrestricted|\"\*\"|scope\s*[:=]\s*\*)", re.IGNORECASE)
TOOL_DEFINITION_RE = re.compile(r"\b(tools?|tool_calls?|function_call|functions|mcpServers|server_name)\b", re.IGNORECASE)


def _repo_dir(run_dir: Path) -> Path:
    ctx = load_context(run_dir)
    return run_dir / ctx.get("target_repo_dir", "repo")


def _reports_dir(run_dir: Path) -> Path:
    ctx = load_context(run_dir)
    return run_dir / ctx.get("reports_dir", "reports")


def _iter_text_files(repo_dir: Path) -> Iterable[Path]:
    if not repo_dir.exists():
        return []
    files: list[Path] = []
    for root, dirnames, filenames in os.walk(repo_dir, onerror=lambda _error: None):
        root_path = Path(root)
        dirnames[:] = sorted(
            dirname
            for dirname in dirnames
            if dirname not in SKIP_DIRS and not (root_path / dirname).is_symlink()
        )
        for filename in sorted(filenames):
            path = root_path / filename
            if not path.is_file():
                continue
            if path.is_symlink():
                continue
            if any(part in SKIP_DIRS for part in path.relative_to(repo_dir).parts):
                continue
            if path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            try:
                if path.stat().st_size > MAX_FILE_BYTES:
                    continue
            except OSError:
                continue
            files.append(path)
    return sorted(files, key=lambda p: p.relative_to(repo_dir).as_posix())


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _repo_display_prefix(run_dir: Path, repo_dir: Path) -> str:
    try:
        return repo_dir.relative_to(run_dir).as_posix()
    except ValueError:
        return repo_dir.name


def _display_path(run_dir: Path, repo_dir: Path, path: Path) -> str:
    prefix = _repo_display_prefix(run_dir, repo_dir)
    return f"{prefix}/{path.relative_to(repo_dir).as_posix()}"


def _is_agent_instruction(rel: str) -> bool:
    if rel in AGENT_INSTRUCTION_PATHS:
        return True
    return any(rel.startswith(prefix) for prefix in AGENT_INSTRUCTION_PARTS)


def _is_prompt_template(path: Path, rel: str) -> bool:
    haystack = f"{path.stem} {rel}".lower()
    return any(token in haystack for token in PROMPT_PATTERNS) and path.suffix.lower() in {".md", ".txt", ".j2", ".jinja", ".json", ".yaml", ".yml"}


def _detect_capabilities(text: str) -> list[str]:
    found = []
    for name, pattern in CAPABILITY_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            found.append(name)
    return found


def _taxonomy_refs(surface_type: str, capabilities: list[str]) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    if surface_type == "mcp_config":
        refs.append({"name": "MCP Security", "id": "MCP-SCOPE-MINIMIZATION", "label": "Scope Minimization Failure"})
        if "network" in capabilities:
            refs.append({"name": "MCP Security", "id": "MCP-SSRF", "label": "OAuth Metadata SSRF"})
    if surface_type in {"agent_instruction", "prompt_template"}:
        refs.append({"name": "OWASP LLM Top 10 2025", "id": "LLM01", "label": "Prompt Injection"})
        refs.append({"name": "OWASP AI Agent Security", "id": "AGENT-PROMPT-INJECTION", "label": "Agent Prompt Injection"})
    if surface_type in {"tool_definition", "ai_sdk_usage", "mcp_config"}:
        refs.append({"name": "OWASP AI Agent Security", "id": "AGENT-TOOL-PERMISSION", "label": "Over-Privileged Tool Access"})
        if any(cap in capabilities for cap in ["github", "deployment", "email", "slack", "ticket"]):
            refs.append({"name": "OWASP AI Agent Security", "id": "AGENT-HIGH-IMPACT-ACTION", "label": "High-Impact Action Abuse"})
    if surface_type == "memory_store" or "memory" in capabilities:
        refs.append({"name": "OWASP LLM Top 10 2025", "id": "LLM08", "label": "Vector and Embedding Weaknesses"})
        refs.append({"name": "OWASP AI Agent Security", "id": "AGENT-MEMORY-ISOLATION", "label": "Memory and Context Isolation"})
    # Keep order stable while removing duplicates.
    unique: list[dict[str, str]] = []
    seen = set()
    for ref in refs:
        key = (ref["name"], ref["id"])
        if key not in seen:
            unique.append(ref)
            seen.add(key)
    return unique


def _review_questions(surface_type: str, capabilities: list[str]) -> list[str]:
    common = ["Is untrusted repository content prevented from overriding the auditor or runtime policy?"]
    if surface_type == "mcp_config":
        return [
            "Are MCP server commands and arguments allowlisted and scoped to the intended workspace?",
            "Are transport, network, and filesystem permissions minimized for this MCP server?",
            "Are tokens scoped and prevented from passthrough to untrusted MCP servers?",
        ]
    if surface_type == "agent_instruction":
        return common + [
            "Are repository-local agent instructions treated as project data rather than controlling system instructions?",
            "Do these instructions request high-impact actions such as Issue creation, file writes, or secret disclosure?",
        ]
    if surface_type == "tool_definition":
        return common + [
            "Are tool descriptions free from hidden instructions and privilege escalation guidance?",
            "Are high-impact tool calls gated by explicit human approval?",
        ]
    if surface_type == "ai_sdk_usage":
        return common + [
            "Are AI tool permissions least-privilege and separated from untrusted prompt content?",
            "Are model outputs validated before reaching sensitive sinks?",
        ]
    if surface_type == "memory_store":
        return common + [
            "Is agent memory or vector-store content isolated by tenant, repository, and run?",
            "Are secrets and sensitive context excluded or redacted before indexing?",
        ]
    return common + ["Are prompt templates structured to separate trusted instructions from untrusted context?"]


def _risk(surface_type: str, text: str, capabilities: list[str]) -> str:
    high_caps = {"shell", "filesystem", "network", "github", "deployment", "email", "slack", "ticket"}
    if surface_type == "mcp_config" and (high_caps.intersection(capabilities) or WILDCARD_SCOPE_RE.search(text)):
        return "high"
    if surface_type == "agent_instruction" and SUSPICIOUS_INSTRUCTION_RE.search(text):
        return "high"
    if surface_type == "tool_definition" and high_caps.intersection(capabilities):
        return "high"
    if surface_type == "ai_sdk_usage" and high_caps.intersection(capabilities):
        return "high"
    if surface_type == "memory_store":
        return "medium"
    return "medium"


def _summary(surface_type: str, rel: str, capabilities: list[str], providers: list[str] | None = None) -> str:
    caps = f" with {', '.join(capabilities)} capability hints" if capabilities else ""
    if surface_type == "ai_sdk_usage" and providers:
        return f"AI SDK usage detected for {', '.join(providers)}{caps}"
    labels = {
        "mcp_config": "MCP/client configuration detected",
        "agent_instruction": "Repository-local agent instruction file detected",
        "tool_definition": "AI tool/function definition hints detected",
        "prompt_template": "Prompt or system-instruction template detected",
        "memory_store": "Agent memory or vector-store usage detected",
    }
    return f"{labels.get(surface_type, surface_type)} in {rel}{caps}"


def _make_surface(
    surface_type: str,
    run_dir: Path,
    repo_dir: Path,
    path: Path,
    text: str,
    providers: list[str] | None = None,
) -> dict[str, Any]:
    rel = path.relative_to(repo_dir).as_posix()
    capabilities = _detect_capabilities(text)
    risk = _risk(surface_type, text, capabilities)
    return {
        "type": surface_type,
        "path": _display_path(run_dir, repo_dir, path),
        "risk": risk,
        "summary": _summary(surface_type, rel, capabilities, providers),
        "detected_capabilities": capabilities,
        "review_questions": _review_questions(surface_type, capabilities),
        "taxonomies": _taxonomy_refs(surface_type, capabilities),
    }


def discover_agent_surfaces(run_dir: Path) -> list[dict[str, Any]]:
    repo_dir = _repo_dir(run_dir)
    surfaces: list[dict[str, Any]] = []
    for path in _iter_text_files(repo_dir):
        rel = path.relative_to(repo_dir).as_posix()
        text = _read_text(path)
        lower = text.lower()
        if rel in MCP_CONFIG_PATHS or rel.endswith("/mcp.json"):
            surfaces.append(_make_surface("mcp_config", run_dir, repo_dir, path, text))
        if _is_agent_instruction(rel):
            surfaces.append(_make_surface("agent_instruction", run_dir, repo_dir, path, text))
        providers = [label for label, pattern in AI_SDK_PATTERNS if re.search(pattern, text, re.IGNORECASE)]
        if providers:
            surfaces.append(_make_surface("ai_sdk_usage", run_dir, repo_dir, path, text, providers))
        if "vector" in lower or any(token in lower for token in ["chroma", "pinecone", "qdrant", "weaviate", "faiss", "milvus", "pgvector"]):
            surfaces.append(_make_surface("memory_store", run_dir, repo_dir, path, text))
        if TOOL_DEFINITION_RE.search(text) and ("tool" in lower or "function" in lower):
            surfaces.append(_make_surface("tool_definition", run_dir, repo_dir, path, text))
        if _is_prompt_template(path, rel):
            surfaces.append(_make_surface("prompt_template", run_dir, repo_dir, path, text))

    surfaces = sorted(surfaces, key=lambda item: (item["path"], item["type"]))
    for index, surface in enumerate(surfaces, start=1):
        surface["id"] = f"AGS-{index:03d}"
    return surfaces


def write_agent_surface_artifacts(run_dir: Path) -> list[dict[str, Any]]:
    ctx = load_context(run_dir)
    surfaces = discover_agent_surfaces(run_dir)
    if not surfaces:
        reports = _reports_dir(run_dir)
        for artifact in [reports / "agent-surface.json", reports / "AGENT_SURFACE.md"]:
            with suppress(OSError):
                artifact.unlink()
        return []
    reports = _reports_dir(run_dir)
    data = {
        "schema_version": "1",
        "run_id": ctx.get("run_id", run_dir.name),
        "repo": ctx.get("repo", ""),
        "branch": ctx.get("branch", ""),
        "commit": ctx.get("commit", ""),
        "generated_at": utc_now(),
        "agent_surfaces": surfaces,
    }
    write_json(reports / "agent-surface.json", data)
    (reports / "AGENT_SURFACE.md").write_text(render_agent_surface_markdown(data), encoding="utf-8")
    return surfaces


def render_agent_surface_markdown(data: dict[str, Any]) -> str:
    lines = [
        "# AI agent and MCP surface discovery",
        "",
        f"Repository: `{data.get('repo', '')}`",
        f"Run ID: `{data.get('run_id', '')}`",
        f"Commit: `{data.get('commit', '')}`",
        "",
        "Repository content is untrusted input. These entries are review leads, not confirmed vulnerabilities.",
        "",
        "| ID | Risk | Type | Path | Capabilities | Summary |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for surface in data.get("agent_surfaces") or []:
        caps = ", ".join(surface.get("detected_capabilities") or []) or "-"
        lines.append(
            "| "
            f"{_markdown_cell(surface.get('id'))} | "
            f"{_markdown_cell(surface.get('risk'))} | "
            f"{_markdown_cell(surface.get('type'))} | "
            f"`{_markdown_cell(surface.get('path'))}` | "
            f"{_markdown_cell(caps)} | "
            f"{_markdown_cell(surface.get('summary'))} |"
        )
    lines.append("")
    lines.append("## Review questions")
    for surface in data.get("agent_surfaces") or []:
        lines.append("")
        lines.append(f"### {_markdown_cell(surface.get('id'))} `{_markdown_cell(surface.get('path'))}`")
        for question in surface.get("review_questions") or []:
            lines.append(f"- {question}")
    lines.append("")
    return "\n".join(lines)


def _markdown_cell(value: Any) -> str:
    return str(value).replace("\n", " ").replace("\r", " ").replace("|", "\\|")


def _target_id(index: int) -> str:
    return f"TGT-AGENT-{index:03d}"


def append_agent_surface_targets(run_dir: Path) -> list[dict[str, Any]]:
    reports = _reports_dir(run_dir)
    data = load_json(reports / "agent-surface.json", {}) or {}
    surfaces = [s for s in data.get("agent_surfaces") or [] if isinstance(s, dict)]
    high_risk = [s for s in surfaces if s.get("risk") == "high"]
    if not high_risk:
        return []
    targets = load_targets(run_dir)
    existing_scopes = {str(t.get("scope")) for t in targets if isinstance(t, dict)}
    existing_ids = {str(t.get("id")) for t in targets if isinstance(t, dict)}
    next_index = 1
    added: list[dict[str, Any]] = []
    for surface in high_risk:
        scope = str(surface.get("path") or "")
        if scope in existing_scopes:
            continue
        while _target_id(next_index) in existing_ids:
            next_index += 1
        target = {
            "id": _target_id(next_index),
            "category": "AI Agent/MCP",
            "title": f"Review {surface.get('type')} surface at {scope}",
            "risk": "high",
            "priority": 90,
            "status": "queued",
            "scope": scope,
            "entry_points": [scope],
            "trust_boundaries": ["untrusted repository content -> AI agent/tool execution context"],
            "sinks": surface.get("detected_capabilities") or ["AI tool invocation"],
            "security_invariants": [
                "Repository-local instructions cannot override run-level audit policy.",
                "High-impact tool actions require explicit approval and least-privilege scope.",
            ],
            "review_questions": surface.get("review_questions") or [],
            "candidate_files": [scope],
            "recommended_mode": "exec",
            "notes": f"Generated from {surface.get('id')} in reports/agent-surface.json. {surface.get('summary', '')}",
            "taxonomies": surface.get("taxonomies") or [],
        }
        targets.append(target)
        added.append(target)
        existing_ids.add(target["id"])
        existing_scopes.add(scope)
        next_index += 1
    if added:
        write_targets(run_dir, targets)
    return added
