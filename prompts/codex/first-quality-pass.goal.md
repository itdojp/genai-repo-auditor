/goal Perform a public OSS quality pass for GenAI Repo Auditor.

Read first:
- AGENTS.md
- README.md
- SECURITY.md
- CONTRIBUTING.md
- TRADEMARKS.md
- docs/WORKFLOW_OVERVIEW.md
- docs/SECURITY_MODEL.md
- bin/gra-audit
- lib/gralib.py

Tasks:
1. Search for legacy names: codex-security-lab, Codex Security Lab, codex-sec-.
2. Replace legacy names unless they are needed in compatibility notes.
3. Verify docs consistently use gra-* command names.
4. Verify public safety boundaries are present.
5. Verify .gitignore blocks local audit artifacts.
6. Run validation:
   - for f in bin/gra-*; do
  if head -n 1 "$f" | grep -q "bash"; then
    bash -n "$f"
  fi
done
   - python3 -m py_compile lib/*.py bin/gra-*
7. Prepare a short summary of changed files and remaining issues.

Stop when validation passes and remaining work is expressed as issue candidates.
