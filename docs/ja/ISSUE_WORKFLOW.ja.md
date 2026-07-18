# GitHub Issue 作成ワークフロー

英語版は [`docs/ISSUE_WORKFLOW.md`](../ISSUE_WORKFLOW.md) を参照してください。この文書では、日本語運用者向けに安全な Issue 作成手順をまとめます。

## 原則

- Issue 作成は `gra-audit` の一部ではありません。
- `reports/findings.json` と `reports/issue-drafts/*.md` を人間が確認した後にだけ実行します。
- secret、credential、未検証の攻撃手順、過度に詳細な exploit 情報を GitHub Issue に出さないでください。
- public repository では公開開示になります。組織ポリシー、修正状況、関係者承認を確認してください。

## 既定の選択条件

`gra-issues` は既定で以下の finding だけを対象にします。

```text
severity: Critical / High
status: Confirmed / Probable
issue_recommended: true
```

条件を満たしていても、自動的に公開してよいという意味ではありません。evidence、impact、remediation、public disclosure risk を人間が確認してください。

Critical / High 候補は、公開前に独立した adversarial validation も実行または確認します。

```bash
gra-gapfill --run runs/OWNER__REPO/RUN_ID --generate
gra-chains --run runs/OWNER__REPO/RUN_ID
gra-proofs --run runs/OWNER__REPO/RUN_ID --all-critical-high
# shared-library / producer finding の consumer 到達可能性を確認する場合だけ:
# gra-trace --producer-run runs/OWNER__shared-lib/RUN_ID --finding SEC-001 --consumer-repo OWNER/consumer --mode prepare
# gra-trace --producer-run runs/OWNER__shared-lib/RUN_ID --finding SEC-001 --consumer-run runs/OWNER__shared-lib/RUN_ID/trace-consumers/OWNER__consumer --mode exec
gra-adversarial-validate --run runs/OWNER__REPO/RUN_ID --all-critical-high --votes 3 --policy human-review-on-split
gra-taxonomy-preflight --run runs/OWNER__REPO/RUN_ID --fix
gra-validate-report --run runs/OWNER__REPO/RUN_ID
```

`reports/COVERAGE.md` と `reports/gapfill-targets.json` で high-risk target
に shallow coverage や unresolved gapfill recommendation が残っていないか
確認してください。

`reports/ATTACK_CHAINS.md` は non-public by default の内部資料です。
chain implications を remediation priority と disclosure planning に使い、
public Issue にそのまま貼り付けないでください。`reports/PROOFS.md` と
`reports/proofs/` は local/private by default の safe local proof artifact です。
proof limitations を Issue 文言に反映し、公開 exploit evidence として扱わないで
ください。`reports/traces.json` と `reports/TRACE.md` は experimental/P3 の
cross-repo reachability evidence であり exploit proof ではありません。
trace limitations を Issue 文言に反映し、confirmed exploitability として
扱う前に人間が確認してください。`reports/VALIDATION.md` と
`reports/validation.json` の `downgrade`、`invalidate`、`needs-human-review` は、
直接公開を止めるシグナルとして扱います。
finding metadata と Issue draft を修正するか、残る不確実性を人間が明示的に
受け入れるまで、confirmed exploitability として扱わないでください。

## dry-run

最初は必ず dry-run を実行します。

```bash
gra-issues --run runs/OWNER__REPO/RUN_ID --dry-run
```

`issue_body_file` を使う finding では、参照先は設定済みの `<reports_dir>/issue-drafts/`（既定値: `reports/issue-drafts/`）配下の相対 `.md` file である必要があります。`gra-issues` は絶対 path、`..` traversal、symlink、non-Markdown file、過大な draft、および設定と異なる reports directory への参照を拒否します。

dry-run は preview 専用です。`reports/issue-publication-plan.json` は書き込まず、
GitHub Issue も作成しません。`issues-created.json` と
`reports/issue-ledger.json` には `plan_written=false` と
`publication_plan_status=not-written-preview` が記録されます。出力には、
後で `--plan` に昇格した場合に使われる publication plan path と、各 Issue
body の SHA-256 hash が表示されます。hash は候補本文の確認に使えますが、
dry-run 出力を immutable な承認 record として扱わないでください。target 固有の
title、fingerprint、Issue body hash を含み得るため、public demo では未 sanitization
の dry-run 出力を表示しないでください。

### machine-readable local summary

dry-run が成功すると、次の 2 artifact も同時に生成されます。

```text
<reports_dir>/issue-dry-run-summary.json
<reports_dir>/ISSUE_DRY_RUN_SUMMARY.md
```

JSON は closed schema の機械可読 input、Markdown は同じ集計を確認するための
sanitized local aggregate です。どちらにも finding title、body、path、fingerprint、
label、raw GitHub response は入りません。`selection_source` は
`current-findings` または `verified-publication-plan`、`visibility` は宣言値を
記録します。visibility は run artifact から読み、`--apply-plan ... --dry-run` では
verified plan の宣言値を使います。online GitHub visibility lookup ではありません。
そのため `github_visibility_lookup_performed` と
`github_duplicate_search_performed` は常に `false` です。dry-run は GitHub lookup
も mutation も行わず、immutable publication plan も書き込みません。summary では
`safety.github_mutation_performed=false`、
`safety.publication_plan_written=false`、`counts.issues_created=0` が固定です。
`reports_dir` は検証済み run context から読み、default は `reports` です。findings、
plan、ledger、duplicate decision、summary、command event は同じ configured directory
配下に維持されます。

`would_create` は declared visibility を適用した local preview 上の分類です。
公開承認でも、現在の GitHub visibility の証明でもありません。apply mode は
authoritative な online visibility check を実行するため、local declaration が古い、
または誤っている場合は publication を拒否できます。

count は互いに重ならない 2 つの partition を満たします。

```text
total_candidates = selected
                 + filtered_by_severity_or_status
                 + issue_recommendation_suppressed
                 + novelty_suppressed

selected = duplicate_suppressed
         + advanced_validation_blocked
         + public_visibility_blocked
         + would_create
```

最初の式は全 candidate finding の selection 分類です。
`filtered_by_severity_or_status` は設定した severity/status filter、
`issue_recommendation_suppressed` は `issue_recommended=false`、
`novelty_suppressed` は local novelty ledger の `duplicate`、`accepted-risk`、
`invalid-known` を表します。後者の式は selected candidate の publication 分類です。
`duplicate_suppressed` は online search ではなく既存 local issue ledger との一致です。
`--require-advanced-validation` により strict validation が candidate を止めた場合は
`advanced_validation_blocked`、`--allow-public` なしで declared `PUBLIC` または
`UNKNOWN` を止めた場合は `public_visibility_blocked` になります。これは apply mode の
fail-closed visibility class と一致します。`warnings` は aggregate warning count であり、
どちらの partition にも含めません。strict mode で block がある dry-run は、summary を
書いた後に exit `4` になります。

`selection_source=verified-publication-plan` の場合、candidate universe は plan 作成前の
finding 全体ではなく、凍結済み plan entry です。このため
`total_candidates=selected` となり、3 つの pre-selection suppression counter は `0`、
第 2 の partition が全 verified plan entry を分類します。

その後 `gra-metrics --run <run_dir>` を実行すると JSON が直接
`metrics.json.issue_dry_run` に取り込まれます。artifact がない場合は
`artifact_present=false` と全 counter `0` になり、successful zero-selection ではなく
not-run/absent を表します。`gra-dashboard` はその metrics の would-create と local
suppression count を表示し、`gra-benchmark` も同じ metrics field を workflow-health
summary に使います。いずれも GitHub を再照会せず、finding content を解釈し直しません。

summary と downstream view の検証は次の順序で行います。

```bash
gra-issues --run runs/OWNER__REPO/RUN_ID --dry-run
gra-validate-report --run runs/OWNER__REPO/RUN_ID
gra-metrics --run runs/OWNER__REPO/RUN_ID
gra-dashboard --run runs/OWNER__REPO/RUN_ID
gra-benchmark --run runs/OWNER__REPO/RUN_ID
gra-validate-report --run runs/OWNER__REPO/RUN_ID --check-freshness
```

最初の validator は JSON/Markdown pair の同時存在、closed schema、count invariant、
unsafe または oversized path を検証します。最後の freshness check は derived
metrics/dashboard/benchmark catalog も確認する場合にだけ必要です。

## immutable publication plan

外部に見える Issue 作成や high-impact な公開操作では、二段階の plan
workflow を推奨します。plan は同じ `findings.json` と issue draft set
に対して deterministic であり、GitHub Issue は作成しません。

```bash
gra-issues --run runs/OWNER__REPO/RUN_ID --plan
```

生成先:

```text
runs/OWNER__REPO/RUN_ID/reports/issue-publication-plan.json
runs/OWNER__REPO/RUN_ID/reports/issue-ledger.json
```

plan には selected finding ID、fingerprint、title、label、issue body
file、issue body SHA-256 hash、public disclosure risk、run ID、repo、
commit、`chain_membership`、`advanced_validation` summary が記録されます。
default の `reports/issue-publication-plan.json` に書く場合は、bounded な
生成時点の `report_freshness` snapshot も埋め込みます。apply 時の正本は、この
static snapshot ではなく sidecar の live assessment です。`issue-ledger.json` は、選択されなかった
finding も含めて公開状態を追跡する canonical ledger です。各 finding の
fingerprint、Issue URL、Issue number、state、title、label、body hash、
published timestamp、source plan を保持します。
新しい ledger は `plan_written` と `publication_plan_status` も記録し、
dry-run preview、`--plan` が作成した immutable plan、`--apply-plan` が検証した
既存 plan を区別できるようにします。
advanced summary には、関連する `reports/chains.json` record の有無、
関連 adversarial validation record の有無、safe local proof artifact の有無
または明示的な not applicable 判定、公開前に確認すべき warning が含まれます。
公開前に plan、参照される issue draft、`reports/ATTACK_CHAINS.md`、
`reports/PROOFS.md`、`reports/VALIDATION.md` を確認します。

warning は既定では公開を自動停止しません。advanced evidence を必須にする
運用では、次の strict mode を使います。

```bash
gra-issues --run runs/OWNER__REPO/RUN_ID --plan --require-advanced-validation
```

この mode は、selected High/Critical finding に必要な chain、proof、
adversarial-validation evidence が欠けている場合、または関連 validation
decision が `downgrade`、`invalidate`、`needs-human-review` の場合に
non-zero で終了します。Issue body には `ATTACK_CHAINS.md` の内容を
含めません。public text には、レビュー済みの remediation / disclosure
implications だけを要約してください。

承認後、同じ plan を apply します。

```bash
gra-issues \
  --run runs/OWNER__REPO/RUN_ID \
  --apply-plan runs/OWNER__REPO/RUN_ID/reports/issue-publication-plan.json \
  --create-labels
```

`--apply-plan` は Issue body hash、advanced-validation summary、
fingerprint、selected finding の存在、title、label、public disclosure risk、
chain membership を再計算・検証し、plan 作成後に変更された内容の公開を
拒否します。run に default plan の tracked record がある場合、その live freshness が
`stale` または `missing_dependency` なら、copy した plan を含む全ての指定 path で
publication safety gate として apply を拒否し、
`gra-issues --run <run_dir> --plan` の再実行と人手の再レビューを要求します。
plan が古くなった場合は `--plan` で作り直し、再レビューしてから apply して
ください。`--apply-plan ... --replan` は plan を更新して終了し、Issue は
作成しません。replan 時も ledger は現在の findings と既存の公開状態を照合して
更新されます。replan が受け付けるのは default tracked plan path だけです。
custom-path replan は書込み前に失敗し、default plan の再生成を案内します。
legacy report validation は `not_applicable` のままですが、
`--apply-plan` は default tracked plan record または sidecar がなければ fail closed
します。default plan を再生成してレビューし、その plan またはレビュー済み copy
を apply してください。これが legacy / custom-plan workflow の publication migration
手順です。通常の plan content 検証も引き続き必須です。

## apply

Issue 本文、label、重複有無、公開可否を確認した後だけ apply します。

```bash
gra-issues --run runs/OWNER__REPO/RUN_ID --apply --create-labels
```

private workflow で既に人間レビュー済みの場合は direct `--apply` も利用できます。
ただし、承認を exact Issue content に結び付ける必要がある場合は plan workflow
を使用してください。

public repository への Issue 作成はデフォルトで拒否されます。公開が意図され、承認済みの場合だけ `--allow-public` を指定します。

```bash
gra-issues --run runs/OWNER__REPO/RUN_ID --apply --create-labels --allow-public
```

## duplicate prevention

Issue 本文には hidden marker を入れます。

```markdown
<!-- genai-repo-auditor:fingerprint=<fingerprint> -->
```

既存 open Issue に同じ fingerprint がある場合は新規作成を避けます。fingerprint が placeholder、短すぎる値、重複値の場合は、Issue 化前に finding を修正してください。

`reports/issue-ledger.json` が存在する場合、`gra-issues` は GitHub 検索より前に
ledger を確認します。ledger 上で同じ finding ID / fingerprint が
`published` または `duplicate` として記録されている場合、再実行しても
新規 Issue は作成しません。同じ finding ID の published entry が ledger に
1 件だけあり、現在の fingerprint が変わっている場合も、新規 Issue は作成せず
ledger に fingerprint drift を記録します。apply 後の `issues-created.json` は
互換性のため残りますが、継続的な公開状態確認では `issue-ledger.json` を優先します。
dry-run / apply では、選択 finding ごとに
`reports/duplicate-decisions/<finding_id>.json` も作成します。同じ finding ID の
record が衝突する場合は fingerprint suffix 付きの file name を使います。この record は
candidate Issue number、exact match の有無、`variant_of`、root cause fingerprint、
source-to-sink fingerprint、`new` / `exact-duplicate` / `variant` /
`related-not-duplicate` の decision、rationale、`checked_at` を保存します。

GitHub 側の状態と ledger の不整合を確認する場合は、次を実行します。

```bash
gra-issues --run runs/OWNER__REPO/RUN_ID --verify-ledger
```

この確認は `reports/issue-ledger.json` の published / duplicate entry を
open GitHub Issue の fingerprint marker と照合し、見つからない場合や URL が
異なる場合、または published / duplicate entry に対応する duplicate decision
record が存在しない場合に non-zero で終了します。

## 作成前チェックリスト

- `gra-validate-report --run RUN_DIR` が成功している。
- `reports/findings.json` の severity、status、confidence、public disclosure risk が妥当である。
- `reports/duplicate-decisions/*.json` で exact duplicate / variant / related-but-not-duplicate / new の判断根拠が確認できる。
- `reports/ATTACK_CHAINS.md` は non-public by default として扱い、Issue 本文にそのまま含めない。
- `reports/PROOFS.md` と `reports/proofs/` は local/private by default として扱い、Issue 本文にそのまま含めない。
- `reports/VALIDATION.md` の downgrade / invalidate / needs-human-review を確認し、必要な修正または明示承認が済んでいる。
- `reports/issue-ledger.json` がある場合、既存の published / duplicate entry と GitHub 側の状態に drift がない。
- `reports/issue-drafts/*.md` に secret の全文、token、credential、実 exploit 手順が含まれていない。
- scanner 由来の情報は repository context で到達可能性と影響を確認済みである。
- public repository の場合、`--allow-public` を使う根拠と承認が明確である。
