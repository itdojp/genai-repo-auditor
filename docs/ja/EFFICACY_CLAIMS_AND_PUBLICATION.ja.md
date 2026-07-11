# Efficacy 比較・claim・公開ポリシー

この文書は `gra-efficacy-benchmark --compare` と任意の worker-assisted run に
適用します。synthetic corpus は回帰検証用であり、production data を代表しません。

## 方法論

決定的比較では checkout/command version、corpus ID と content-bound version、suite と
case ID、schema、configuration ID、出力形式を固定します。default は次の 2 つの
reference-review workflow 構成です。

- `reference-review-all-signals-v1`: fixture reference review の全 synthetic signal を残す。
- `reference-review-high-severity-gate-v1`: 同じ review 後の gate で High/Critical signal だけを残す。

report は configuration/case ID、TP/FP/FN/TN、rate、上限付き case outcome、baseline
との差分だけを記録します。fixture 本文、evidence、location、remediation、exploit step、
worker prompt/transcript、credential は含めません。差分は比較機構の回帰証拠であり、
production security-review strategy の優劣を示しません。report は `workflow_stage_ids` で stage
差分を明示します。これらは scanner-only、AI-only、production full-harness の別名ではありません。

## 任意 worker 実行

worker は `--compare --worker --worker-dir DIR` を全て明示した場合だけ実行されます。
初期対応は builtin `codex-cli` profile です。approval `never`、read-only sandbox、
web search disabled、sandbox network access `false` を固定し、sandbox network を有効にする
option はありません。ephemeral session を使用し、user configuration と project/user rule を
読み込まず、closed worker response schema を Codex CLI に渡します。launcher が model channel
へ入力として渡すのは public-safe synthetic fixture だけです。operator の trusted `PATH` から
`codex` を 1 回解決して固定し、変更された builtin profile executable 名は拒否します。worker
environment は縮小し、無関係な GitHub/cloud credential は渡しません。event/stderr/response の
size は実行中にも監視し、上限超過時は worker を停止します。

worker row は `deterministic: false` です。model、effort、prompt、command、corpus version が
異なる結果を単一変数の比較として扱ってはいけません。report は Codex CLI version も記録します。
isolated execution flag を使用するため Codex CLI 0.135.0 以上が必要で、worker command が version
gate を行います。`gra-agent-check` は executable の存在だけを別途確認します。worker mode は model service
control-plane channel を使用します。`external_network_beyond_model_channel_enabled: false` は
subprocess sandbox に追加 network を許可せず、user configuration を無視し、web search を
無効にした launcher 設定を示します。offline や、network activity を独立観測したという意味では
ありません。

Codex の read-only sandbox は、host 上の全ての readable file に対する OS-level の
confidentiality boundary ではありません。prompt は command と無関係な read を禁止しますが、
非アクセスの証明にはなりません。worker が読めてはならない情報を host が持つ場合は、専用 host
または別管理の container を使用してください。選択した `codex` executable と model service は
trusted dependency として扱います。Codex に必要な model authentication/proxy variable は縮小済み
worker environment に残る場合があります。

## 禁止する claim

この corpus だけを根拠に、以下を主張してはいけません。

- 製品全体の recall、precision、false-positive rate。
- language/framework/vulnerability class/worker/model/provider/workflow の対応や優位性。
- guaranteed discovery、complete coverage、production readiness、release safety。
- model superiority、統計的に有意な改善、実 repository finding の妥当性。

report の `product_capability_claim_allowed: false` と
`production_performance_claim_allowed: false` は強制ポリシーです。内部共有では
corpus/configuration/case/command version と worker/model channel 使用有無を必ず示します。

## 公開判断

comparison report と worker artifact は default で非公開の local artifact です。private
repository 情報、credential、worker transcript、不当な claim、production への誤解がないことを
人が確認し、security/disclosure owner が承認した場合だけ aggregate report を共有できます。

benchmark は finding や GitHub Issue の公開を許可しません。real repository finding には
repository-specific evidence、adversarial validation、disclosure review、通常の Issue 公開手順が
別途必要です。worker artifact は添付せず、local path を除外し、score 表の近くに small
synthetic-corpus limitation を記載してください。

## CI 回帰確認

CI は deterministic comparison だけを実行し、worker/model/GitHub/network helper を呼びません。

```bash
gra-efficacy-benchmark --list-configurations
gra-efficacy-benchmark --compare \
  --out-json .test-tmp/efficacy-comparison.json \
  --out-md .test-tmp/EFFICACY_COMPARISON.md
```

worker-assisted comparison は承認済みの監督下 local operation とし、`--worker-dir` は
current working directory 配下の既存 non-symlink directory とします。cwd 自体は指定できません。
`.test-tmp/efficacy-worker` など version control で ignore された path を使用してください。
