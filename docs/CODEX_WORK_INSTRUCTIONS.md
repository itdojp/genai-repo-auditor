# Codex work instructions

This document is for using Codex CLI to import and maintain this repository.

## Current target

```text
Repository: https://github.com/itdojp/genai-repo-auditor
Project: GenAI Repo Auditor
CLI prefix: gra
Default model: gpt-5.5
Default effort: xhigh
```

## Local preparation

```bash
gh repo clone itdojp/genai-repo-auditor
cd genai-repo-auditor

# Place the generated file set under .codex-local/import/ or copy it into the repo root.
mkdir -p .codex-local/import
```

## Start Codex

```bash
codex \
  --cd . \
  --model gpt-5.5 \
  --enable goals \
  --sandbox workspace-write \
  --ask-for-approval on-request \
  -c 'model_reasoning_effort="xhigh"' \
  -c 'web_search="disabled"' \
  -c 'sandbox_workspace_write.network_access=false'
```

## Import goal prompt

Paste this into Codex after the generated files are available locally.

```text
/goal Import the GenAI Repo Auditor initial file set into this repository and prepare the first public OSS commit.

Context:
- This repository is https://github.com/itdojp/genai-repo-auditor.
- The repository may currently be empty.
- The project must remain vendor-neutral: use GenAI Repo Auditor, genai-repo-auditor, and gra-* command names.
- Third-party product names may be mentioned only for compatibility.
- Do not use OpenAI, Codex, GPT, Claude, Anthropic, Mythos, or GitHub as project or CLI names.

Read first:
- AGENTS.md if present
- README.md if present
- .codex-local/import/ if present
- docs/CODEX_WORK_INSTRUCTIONS.md if present

Tasks:
1. Copy or reconcile the generated file set into the repository root.
2. Ensure the CLI command files are named gra-* and executable.
3. Ensure README.md, LICENSE, NOTICE, SECURITY.md, CONTRIBUTING.md, CODE_OF_CONDUCT.md, TRADEMARKS.md, .gitignore, .github/, bin/, lib/, docs/, prompts/, templates/, and examples/ are present.
4. Ensure documentation uses vendor-neutral project naming.
5. Keep compatibility references to OpenAI Codex CLI only in compatibility sections or operational instructions.
6. Do not add real audit outputs, cloned target repositories, scanner outputs, API keys, tokens, secrets, or findings from real repositories.
7. Run validation:
   - for f in bin/gra-*; do
  if head -n 1 "$f" | grep -q "bash"; then
    bash -n "$f"
  fi
done
   - python3 -m py_compile lib/*.py bin/gra-*
8. Inspect git status and summarize the files added.
9. Prepare a concise commit message.

Stop condition:
- Required files are present.
- Validation commands pass or failures are clearly explained.
- No local audit outputs or secrets are staged.
- A proposed commit message is provided.
```

## First quality pass goal prompt

Use this after the initial import commit.

```text
/goal Perform the first quality pass for GenAI Repo Auditor without changing project scope.

Read first:
- AGENTS.md
- README.md
- SECURITY.md
- CONTRIBUTING.md
- docs/WORKFLOW_OVERVIEW.md
- docs/SECURITY_MODEL.md
- bin/gra-audit
- lib/gralib.py

Tasks:
1. Check for remaining old project names, especially codex-security-lab and codex-sec-*.
2. Check that public documentation is vendor-neutral.
3. Check that commands and docs consistently use gra-*.
4. Check that .gitignore excludes runs/, batches/, *.sqlite, scanner outputs, Codex transcripts, and local artifacts.
5. Check that public safety boundaries are stated in README.md and SECURITY.md.
6. Run:
   - for f in bin/gra-*; do
  if head -n 1 "$f" | grep -q "bash"; then
    bash -n "$f"
  fi
done
   - python3 -m py_compile lib/*.py bin/gra-*
7. Update docs only if necessary.

Stop condition:
- No legacy project names remain except historical notes if deliberately retained.
- Validation passes.
- Remaining issues are listed as GitHub Issue candidates.
```

## Maintenance policy

Use `codex exec` for small deterministic changes. Use `/goal` only for larger refactors, documentation consolidation, command surface changes, or validation loops.
