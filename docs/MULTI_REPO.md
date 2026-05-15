# Multiple repository operation

## 基本方針

複数repoは `gra-batch` で処理します。最初は `--concurrency 1` を推奨します。

```bash
gra-batch --repo-list repos.txt --concurrency 1 --mode exec --model gpt-5.5 --effort xhigh
```

`repos.txt`:

```text
ORG/repo-a
ORG/repo-b
ORG/repo-c
```

## 並列実行

並列化する場合も最初は `--concurrency 2` 程度に抑えます。

```bash
gra-batch --repo-list repos.txt --concurrency 2 --mode exec
```

同一repoの同時監査は lock で防ぎます。`--no-lock` は通常使いません。

## run layout

```text
runs/
  OWNER__repo-a/RUN_ID/
    repo/
    reports/
  OWNER__repo-b/RUN_ID/
    repo/
    reports/
```

## Issue creation

Issue作成は監査後に逐次実行します。

```bash
gra-issues --run runs/OWNER__repo-a/RUN_ID --dry-run
gra-issues --run runs/OWNER__repo-a/RUN_ID --apply
```

並列Issue作成は推奨しません。重複Issue、GitHub API制限、公開事故のリスクが上がります。

## 推奨ポリシー

```text
- 監査: concurrency=1 から開始
- Issue作成: 常に逐次
- 同一repo同時実行: 禁止
- /goal: 単一repo深掘り専用
```
