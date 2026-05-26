# Multiple repository operation

## 基本方針

複数repoは `gra-batch` で処理します。最初は `--concurrency 1` を推奨します。

```bash
gra-batch --repo-list repos.txt --concurrency 1 --mode exec --model gpt-5.5 --effort xhigh
```

`gra-batch` は全 repo の監査を継続し、結果を
`runs/_batches/BATCH_ID/batch-results.json` に集約します。既定では 1 件以上の
repo が失敗すると batch 全体も non-zero exit します。

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

## Failure handling

CI などで失敗を厳密に扱う場合は既定動作を使います。

```bash
gra-batch --repo-list repos.txt --concurrency 1 --mode exec
```

探索目的で失敗 repo を記録しつつ batch 自体は成功扱いにする場合のみ
`--allow-failures` を使います。

```bash
gra-batch --repo-list repos.txt --concurrency 1 --mode exec --allow-failures
```

最初の失敗で停止したい場合は `--fail-fast` を使います。この option は
`--concurrency 1` と組み合わせてください。

```bash
gra-batch --repo-list repos.txt --concurrency 1 --mode exec --fail-fast
```

## run layout

```text
runs/
  OWNER__repo-a/RUN_ID/
    repo/
    reports/
  OWNER__repo-b/RUN_ID/
    repo/
    reports/
  _batches/BATCH_ID/
    batch.json
    batch-results.json
    logs/
```

## Issue creation

Issue作成は監査後に逐次実行します。

```bash
gra-issues --run runs/OWNER__repo-a/RUN_ID --dry-run
gra-issues --run runs/OWNER__repo-a/RUN_ID --apply
```

並列Issue作成は推奨しません。重複Issue、GitHub API制限、公開事故のリスクが上がります。

## Cross-repo trace reachability

共有 library や producer repository の finding が consumer repository から
到達可能かを確認する場合は、各 repository の通常 audit run を先に作成し、
producer run から `gra-trace` を実行します。

```bash
gra-trace \
  --producer-run runs/ORG__shared-lib/PRODUCER_RUN_ID \
  --finding SEC-001 \
  --consumer-run runs/ORG__consumer-api/CONSUMER_RUN_ID \
  --mode exec
```

consumer run がまだない場合だけ、明示的な prepare mode で GitHub clone を
行えます。

```bash
gra-trace \
  --producer-run runs/ORG__shared-lib/PRODUCER_RUN_ID \
  --finding SEC-001 \
  --consumer-repo ORG/consumer-api \
  --mode prepare
```

`gra-trace` は experimental/P3 です。`reports/traces.json` と
`reports/TRACE.md` は reachability evidence であり exploit proof では
ありません。external scanning、production/staging probing、exploit
payload、credential access、dependency installation、producer/consumer repo
modification は禁止です。

## 推奨ポリシー

```text
- 監査: concurrency=1 から開始
- Issue作成: 常に逐次
- 同一repo同時実行: 禁止
- /goal: 単一repo深掘り専用
- cross-repo trace: producer/consumer run を明示し、結果は local/private
```
