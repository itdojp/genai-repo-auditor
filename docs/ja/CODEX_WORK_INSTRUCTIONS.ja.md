# Codex 作業指示

この文書は、`https://github.com/itdojp/genai-repo-auditor` に初期ファイル一式を投入し、以後 Codex CLI で保守するための手順です。

## 前提

```text
Repository: https://github.com/itdojp/genai-repo-auditor
Project: GenAI Repo Auditor
CLI prefix: gra
Default model: gpt-5.5
Default effort: xhigh
```

## ローカル準備

```bash
gh repo clone itdojp/genai-repo-auditor
cd genai-repo-auditor
mkdir -p .codex-local/import
```

生成済みファイル一式を repository root にコピーするか、`.codex-local/import/` 配下に置いてください。

## Codex 起動

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

## 最初に貼る `/goal`

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
   - for each bash script under bin/gra-*, run bash -n
   - compile lib/*.py and Python bin/gra-* scripts with py_compile
8. Inspect git status and summarize the files added.
9. Prepare a concise commit message.

Stop condition:
- Required files are present.
- Validation commands pass or failures are clearly explained.
- No local audit outputs or secrets are staged.
- A proposed commit message is provided.
```

## 人間側で実行する確認

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

git status --short
git add .
git commit -m "Initial import of GenAI Repo Auditor"
git push -u origin main
```
