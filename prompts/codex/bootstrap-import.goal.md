/goal Import the GenAI Repo Auditor initial file set into https://github.com/itdojp/genai-repo-auditor and prepare the first public OSS commit.

Use vendor-neutral project naming:
- Project display name: GenAI Repo Auditor
- Repository name: genai-repo-auditor
- CLI prefix: gra

Do not use OpenAI, Codex, GPT, Claude, Anthropic, Mythos, or GitHub as the project name or CLI prefix. Product names may appear only in compatibility and operational documentation.

Read first:
- AGENTS.md if present
- README.md if present
- docs/CODEX_WORK_INSTRUCTIONS.md if present
- .codex-local/import/ if present

Tasks:
1. Reconcile the generated file set into the repository root.
2. Ensure bin/gra-* commands exist and are executable.
3. Ensure lib/gralib.py exists and all imports refer to gralib.
4. Ensure README.md, LICENSE, NOTICE, SECURITY.md, CONTRIBUTING.md, CODE_OF_CONDUCT.md, TRADEMARKS.md, .gitignore, .github/, bin/, lib/, docs/, prompts/, templates/, and examples/ are present.
5. Ensure no runs/, batches/, *.sqlite, cloned target repos, scanner outputs, secrets, or real findings are included.
6. Run validation:
   - for f in bin/gra-*; do
  if head -n 1 "$f" | grep -q "bash"; then
    bash -n "$f"
  fi
done
   - python3 -m py_compile lib/*.py bin/gra-*
7. Summarize git status and provide a commit message.

Stop when validation passes and the repository is ready for the initial commit.
