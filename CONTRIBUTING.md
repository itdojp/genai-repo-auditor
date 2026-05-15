# Contributing

Contributions are welcome when they preserve the project's defensive-only scope.

## Before submitting a PR

Run:

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
```

Do not include:

- real audit runs
- cloned target repositories
- real vulnerability reports
- API keys, tokens, secrets, cookies, or credentials
- weaponized exploit code
- instructions for unauthorized scanning or exploitation

## Naming

Keep the public project name vendor-neutral:

- Use `GenAI Repo Auditor`
- Use `genai-repo-auditor`
- Use `gra-*` command names

Third-party product names may be mentioned only for compatibility documentation.
