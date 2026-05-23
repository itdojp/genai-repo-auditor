# AI agent and MCP surface discovery

`gra-recon` includes a deterministic local discovery pass for AI-agent and
Model Context Protocol (MCP) surfaces before it asks Codex to perform broader
reconnaissance. The pass reads repository files as untrusted input and never
executes target repository code. Symlinked repository files are skipped rather
than followed outside the cloned target tree.

When surfaces are found, the command writes:

- `reports/agent-surface.json`
- `reports/AGENT_SURFACE.md`

`gra-targets --generate` then appends high-risk surfaces as bounded target queue
items with IDs such as `TGT-AGENT-001`.

## Detected surface types

The detector recognizes these surface types:

- `mcp_config`: known MCP client/server configuration files, including
  `.mcp.json`, `.vscode/mcp.json`, `.cursor/mcp.json`,
  `claude_desktop_config.json`, `mcp.json`, and `mcp-servers.json`.
- `agent_instruction`: repository-local agent instructions such as `AGENTS.md`,
  `.github/copilot-instructions.md`, `CLAUDE.md`, `GEMINI.md`, `.clinerules`,
  `.cursorrules`, `.windsurfrules`, `.continue/config.json`, and rule files
  under `.cursor/rules/`, `.windsurf/rules/`, `.continue/rules/`, or
  `.github/instructions/`.
- `ai_sdk_usage`: source files that reference model-provider SDKs such as
  OpenAI, Anthropic, Gemini / Google Generative AI, Azure AI, or OpenRouter.
- `tool_definition`: files that contain tool, function-call, or MCP server
  definition hints.
- `prompt_template`: prompt, system, developer, or instruction templates.
- `memory_store`: memory, embedding, vector, RAG, or vector database usage hints.

The scanner is intentionally bounded to common text source, config, Markdown,
YAML, JSON, TOML, and prompt-template suffixes. Files larger than 512 KiB and
large dependency or build directories such as `.git/`, `node_modules/`,
`vendor/`, `dist/`, and `target/` are skipped.

## Risk classification

The detector emits review leads, not confirmed findings.

High risk is assigned when evidence suggests broad or high-impact agentic
capabilities, for example:

- MCP configs with shell, filesystem, network, wildcard, or unrestricted scope
  hints;
- repository-local agent instructions that attempt prompt injection, policy
  override, secret disclosure, or GitHub Issue creation;
- tool definitions or model-provider usage that reference shell execution,
  filesystem writes, network fetchers, GitHub operations, ticket/email/slack
  creation, deployment, or cloud actions.

Medium risk is used for lower-confidence prompt, SDK, or memory-store review
leads that still warrant inspection but should not become findings by default.

## Target queue behavior

`gra-targets --generate` reads `reports/agent-surface.json` after Codex target
generation completes. For each high-risk surface not already represented by an
existing target scope, it appends a target with:

- category `AI Agent/MCP`;
- ID format `TGT-AGENT-NNN`;
- the surface path as `scope`, `entry_points`, and `candidate_files`;
- review questions specific to MCP, agent instruction, tool, SDK, prompt, or
  memory surfaces;
- advisory taxonomy refs for MCP Security, OWASP AI Agent Security, and OWASP
  LLM Top 10 where applicable.

## Adding detectors

1. Update `lib/agent_surface.py` with a deterministic file pattern or content
   heuristic. Keep the detector local-only and non-executing.
2. Add or extend tests in `tests/test_agent_surface.py` and the staged workflow
   integration tests.
3. Keep outputs bounded. Do not copy full prompts, secrets, scanner payloads, or
   large source snippets into `agent-surface.json` or `AGENT_SURFACE.md`.
4. Prefer advisory taxonomy refs over severity escalation. Confirmed findings
   should still come from later evidence-backed review passes.

## Privacy and safety

Agent surface artifacts can reveal internal tool names, model providers, local
MCP server commands, and high-impact automation paths. Keep them local unless the
operator intentionally approves disclosure.
