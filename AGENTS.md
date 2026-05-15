# AGENTS.md

This repository is `genai-repo-auditor`, a public OSS project for local-first defensive repository security auditing.

## Project rules

- Keep project naming vendor-neutral: use `GenAI Repo Auditor`, `genai-repo-auditor`, and `gra-*` command names.
- Do not rename the project to include OpenAI, Codex, GPT, Claude, Anthropic, Mythos, GitHub, or other third-party product names.
- It is acceptable to mention compatible products in compatibility sections only.
- Do not use third-party logos or brand styling.
- Keep all workflows defensive-only.

## Safety rules

- Do not add live exploitation, external scanning, credential access, credential rotation, production probing, brute force, or weaponized exploit generation.
- Do not commit audit runs, cloned target repositories, scanner outputs, findings from real third-party repositories, API keys, tokens, or secrets.
- Treat `runs/`, `batches/`, `*.sqlite`, scanner outputs, and Codex transcripts as local artifacts only.
- Public GitHub Issue creation for vulnerabilities must remain opt-in and guarded by explicit flags.

## Development rules

- Prefer POSIX-friendly shell and Python 3 standard library only unless a dependency is clearly justified.
- Keep CLI outputs deterministic and concise.
- Keep generated report schemas stable.
- Preserve backward-compatible command flags when possible.
- Add or update docs when command behavior changes.

## Validation

Before committing, run:

```bash
for f in bin/gra-*; do
  if head -n 1 "$f" | grep -q "bash"; then
    bash -n "$f"
  fi
done
python3 - <<'PY'
from pathlib import Path
import py_compile
files = list(Path('lib').glob('*.py'))
files += [p for p in Path('bin').glob('gra-*') if p.read_text(encoding='utf-8', errors='ignore').startswith('#!/usr/bin/env python3')]
for p in files:
    py_compile.compile(str(p), doraise=True)
print('python syntax ok')
PY
python3 - <<'PY'
from pathlib import Path
for p in Path('bin').glob('gra-*'):
    assert p.read_text(encoding='utf-8').startswith(('#!', ''))
print('basic validation ok')
PY
```

If shellcheck is available, also run:

```bash
scripts/validate-shellcheck.sh
```

## Documentation tone

- Use plain, technical English in public documentation.
- Japanese operational notes may be added under `docs/ja/` when useful.
- Avoid marketing claims about model capabilities.
- State uncertainty when behavior depends on a specific AI agent version.
