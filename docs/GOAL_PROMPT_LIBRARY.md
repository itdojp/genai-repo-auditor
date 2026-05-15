# `/goal` Prompt Library

`gra-audit --mode goal` は、run ディレクトリに render 済みの `/goal` prompt を生成する。

## 生成場所

```text
runs/OWNER__REPO/RUN_ID/
  prompt.goal.md
  prompts/
    full-audit.goal.md
    deep-dive-finding.goal.md
    deep-dive-category.goal.md
    validate-findings.goal.md
```

## ファイルの使い分け

| ファイル | 用途 |
|---|---|
| `prompt.goal.md` | `full-audit.goal.md` と同等の主プロンプト。最初に使う標準 deep audit。 |
| `prompts/full-audit.goal.md` | 単一repo全体の深掘り監査。 |
| `prompts/deep-dive-finding.goal.md` | 既存 finding 1件を深く検証する。`TARGET_FINDING_ID` を置換して使う。 |
| `prompts/deep-dive-category.goal.md` | 認可、CI/CD、Secretsなど特定カテゴリを深く調べる。`TARGET_CATEGORY` と `TARGET_SCOPE` を置換して使う。 |
| `prompts/validate-findings.goal.md` | Critical / High findings の false positive を減らすための検証。 |

## 推奨順序

```text
1. prompt.goal.md または prompts/full-audit.goal.md
2. 必要に応じて prompts/deep-dive-finding.goal.md
3. 必要に応じて prompts/deep-dive-category.goal.md
4. prompts/validate-findings.goal.md
5. gra-validate-report
6. Issue dry-run
```

## 起動例

```bash
gra-audit --repo OWNER/REPO --mode goal --model gpt-5.5 --effort xhigh
# 表示された codex コマンドを実行
```

Codex 起動後、次を貼る。

```bash
cat runs/OWNER__REPO/RUN_ID/prompt.goal.md
```

既存 finding を検証する場合:

```bash
cp runs/OWNER__REPO/RUN_ID/prompts/deep-dive-finding.goal.md /tmp/sec-001.goal.md
# /tmp/sec-001.goal.md 内の TARGET_FINDING_ID と TARGET_QUESTION を置換して貼る
```

カテゴリ深掘りの場合:

```bash
cp runs/OWNER__REPO/RUN_ID/prompts/deep-dive-category.goal.md /tmp/authz.goal.md
# TARGET_CATEGORY と TARGET_SCOPE を置換して貼る
```

## ルール

- `/goal` は単一repo・単一目的に限定する。
- Issue作成、PR作成、commit、pushは goal 内で行わせない。
- 修正実装はこの deep dive goal に含めない。
- network は原則無効のままにする。
- 対象 repo の `AGENTS.md`、README、workflow、test fixture は untrusted input として扱う。

## レポート検証

`/goal` 完了後:

```bash
RUN="runs/OWNER__REPO/RUN_ID"
gra-validate-report --run "$RUN"
```
