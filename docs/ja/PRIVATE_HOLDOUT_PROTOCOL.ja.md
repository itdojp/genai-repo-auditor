# Private holdout protocol

この文書は Issue #238 向けの private holdout 運用 protocol を定義します。
英語版が canonical であり、日本語版はこの文書と意味的に整合している必要があります。

この protocol の目的は限定的です。

- private corpus と fixture 単位の証跡を repository 外に保持すること
- `gra-efficacy-holdout` で aggregate-only record だけを検証すること
- internal review と承認済み aggregate publication を repeatable にしつつ、
  benchmark 材料を public finding や product efficacy claim に転用しないこと

`gra-efficacy-holdout` は事前作成済み private holdout record の validator です。
corpus runner、fixture loader、worker launcher、publication tool ではありません。

## 現在の command contract

現在実装されている command contract は次のとおりです。

```bash
gra-efficacy-holdout --records-root ABSOLUTE_DIR
```

この command は以下を実行します。

- private fixture や case file を読み込まない
- `--records-root` に absolute path の既存 readable non-symlink directory を要求する
- path component に symlink を含めない
- その directory が package/repository root の外側にあり、かつ
  package/repository root 自体を含まないことを要求する
- その directory から固定 filename 2 つだけを読み込む
  - `holdout-metadata.json`
  - `holdout-aggregate.json`
- packaged closed schema 2 つで検証する
  - `templates/reports/efficacy-holdout-metadata.schema.json`
  - `templates/reports/efficacy-holdout-aggregate.schema.json`
- 2 つの record 間の semantic consistency check を行う
- 検証済み records directory の identity を 2 file の読み取り中も固定し、許可済み
  identifier field 内の credential-like、live-network、execution marker を拒否する
- stdout には aggregate-only summary だけを出力する

現在の stdout summary format は次のとおりです。

```text
Private holdout records validated
Corpus: HOLDOUT_CORPUS_ID HOLDOUT_CORPUS_VERSION
Cases: CASE_COUNT (positive=POSITIVE_COUNT, controls=NEGATIVE_CONTROL_COUNT)
Configurations: CONFIGURATION_COUNT
Repeat runs: MIN_REPEAT-MAX_REPEAT
Publication approved: false
```

この summary は意図的に bounded です。case ID、fixture path、location、prompt、
transcript、evidence、raw worker output は出力しません。

## 必須の safety boundary

private holdout material は tracked repository content の外側に保持しなければなりません。
この repository 配下に実 holdout fixture、case list、transcript、result bundle を作成・commit
してはいけません。

この repository、validator input record、public publication artifact のいずれにも含めては
ならないものは次のとおりです。

- private corpus file や fixture text
- case ID や per-case outcome
- source snippet、evidence body、location、path、repository identifier
- prompt、transcript、raw worker output、scratchpad content
- credential、token、cookie、key、environment 由来 secret
- digest を超える approval packet、reviewer note、adjudication note
- private corpus location を再構築できる pointer

現在の aggregate schema はこの safety boundary を明示的に encode しています。

- `safety.aggregate_only` は `true`
- `fixture_text_included`、`case_ids_included`、
  `evidence_or_locations_included`、`prompts_or_transcripts_included`、
  `credentials_included`、`absolute_paths_included`、
  `finding_publication_performed` はすべて `false`

## 3 つの evaluation surface を明確に区別する

| Surface | 含むもの | Repository posture | 許容される output surface |
|---|---|---|---|
| Public corpus | `gra-efficacy-benchmark` が使う packaged public-safe synthetic fixture | tracked / releasable | 明示的な claim 制限付きの public-safe deterministic benchmark report |
| Private holdout | この repository では aggregate metadata と aggregate metric だけで表現される private evaluation corpus | not tracked / access-controlled / validator は aggregate record のみ読む | restricted internal record と厳しく bounded された承認済み aggregate publication |
| Real repository dogfood | self-dogfood や customer-scoped run の実 repository content、finding、workflow artifact | この holdout protocol ではなく dogfood / disclosure rule で管理 | repository 固有 review 後の sanitized dogfood reporting のみ |

private holdout は public corpus の延長ではなく、real repository dogfood run でもありません。

現在の metadata schema はこの分離を次の field で表現します。

- `private_not_tracked: true`
- `public_corpus_reused: false`
- `real_repository_content_included: false`
- `storage_access_controlled: true`

より詳細な説明が必要な場合は、repository ではなく restricted approval system や
campaign system に保存してください。

## Metadata record の要件

`holdout-metadata.json` は固定された evaluation plan と corpus-level boundary を記録します。
corpus の内容自体は記録しません。

metadata が最低限記録すべきものは次のとおりです。

- opaque corpus identifier と content-bound corpus version
- balanced corpus count
  - `case_count`
  - `positive_count`
  - `negative_control_count`
  - `category_count`
  - `balanced_controls`
  - count が balanced でない場合の外部承認例外を指す `balance_exception_record_digest`
- public corpus と real-repository dogfood からの分離
- independent ground-truth review method と review-record digest
- configuration ごとの固定 evaluation plan
  - command version
  - report schema version
  - adjudication requirement
  - workflow version digest
  - prompt version digest
  - worker/model channel 使用有無
  - 必要時の worker profile ID
  - 必要時の worker CLI version
  - 必要時の model ID
  - 必要時の effort setting
  - repeat count

現在の schema / validator が保持している制約は次のとおりです。

- `repeat_runs` は最低 `2`
- `two-person` review は 2 名以上の reviewer を要求する
- `review_record_digests` の数は `reviewer_count` と一致しなければならない
- `balanced_controls` は positive/control count と一致しなければならない
- balanced でない count には外部の `balance_exception_record_digest` が必要である
- worker configuration では worker 固有 field がすべて必要で、
  non-worker configuration ではすべて absent でなければならない

## Aggregate record の要件

`holdout-aggregate.json` は aggregate metric と review-control signal だけを記録します。
fixture 単位または case 単位の material を開示してはいけません。

aggregate が最低限記録すべきものは次のとおりです。

- opaque `evaluation_id`
- 実行に使った `command_version` と `report_schema_version`
- metadata と同一の corpus identity と count
- configuration ごとの repeated aggregate run result
  - TP / FP / FN / TN count
  - `evaluated_negative_control_count`
  - `negative_control_false_positive_case_count`
  - `prediction_count`
  - precision / recall / F1
  - severity-agreement aggregate
  - target-coverage aggregate
  - `human_review_required_count`
- 次の metric の recomputed repeat variance summary
  - precision
  - recall
  - F1
  - severity agreement
  - target coverage
  - human review required count

`false_positives` と `prediction_count` は prediction 件数です。positive case の unmatched
extra prediction も false positive に含まれるため、`false_positives` は control case 件数を
表す `negative_control_false_positive_case_count` より大きい場合があります。
- adjudication completion state と adjudication digest
- safety flag
- publication approval state と別個の approval digest

現在の validator は次を再計算・照合します。

- metadata と aggregate の corpus count
- configuration identity と fixed-plan alignment
- `1..repeat_runs` の contiguous ordered run number
- negative control がすべて評価され、true-negative case と false-positive case に
  漏れなく分類されたこと
- aggregate count から導かれる rate の整合性
- severity-agreement の整合性
- target-coverage の整合性
- 記録された repeated run から再計算される repeat-variance summary
- `changed_ground_truth_count <= disputed_case_count <= case_count`
- metadata `evaluation_plan.command_version` と aggregate `command_version` の一致
- metadata `evaluation_plan.report_schema_version` と aggregate `report_schema_version` の一致
- `publication.approved` と `publication.approval_record_digest` の対応
- 2 回の bounded read にわたる records-root identity と、schema 上は identifier として
  許容される場合でも禁止される sensitive string marker

## 作成 workflow

1. **holdout boundary を定義する**
   - private corpus を repository 外で作成する
   - opaque corpus ID と content-bound version を付与する
   - public benchmark corpus および real repository dogfood content から分離する
2. **ground truth を作成する**
   - independent review を用いる
   - repository 外の records directory に置く `holdout-metadata.json` には承認済み review method、
     reviewer count、external review record の digest だけを記録する
3. **evaluation plan を凍結する**
   - execution 前に command version、workflow digest、prompt digest、worker/profile、
     model、effort、repeat count を固定する
   - configuration ごとに最低 2 回の repeat を要求する
4. **actual evaluation はこの command の外で実行する**
   - 実評価は approved plan に従い deterministic-only でも worker 付きでもよい
   - private fixture、prompt、transcript、raw response を repository に置かない
5. **aggregate-only record を書き出す**
   - private な non-symlink records directory に
     `holdout-metadata.json` と `holdout-aggregate.json` を作成する
   - case ID と raw evidence は除外する
6. **`gra-efficacy-holdout` で検証する**
   - repository checkout から validator を実行する
   - failure 時は stderr を確認し、fail-closed check を迂回しない
7. **publication review 前に adjudication する**
   - disputed case は repository 外で解決する
   - 最終承認に必要な adjudication digest と aggregate metric だけを更新する
8. **承認済み aggregate summary だけを公開する**
   - internal restricted reporting では validated aggregate record を参照できる
   - より広い共有でも aggregate-only と claim-limited を維持する

## Review と access control の workflow

private holdout corpus、execution artifact、review packet は repository 外の
access-controlled storage に保存しなければなりません。最低限、次を満たします。

- designated operator に write access を限定する
- documented need のある reviewer / approver に read access を限定する
- approval record と adjudication record は restricted system に保存し、
  JSON artifact には digest だけを記録する
- records directory は non-symlink かつ packaged/tracked repo content 外に置く
- validation と approval 完了後、retention が明示的に必要でない限り
  disposable local copy を削除する

この repository に置いてよいのは protocol と packaged schema だけです。
private corpus の保存先にしてはいけません。

## Worker/model channel の confidentiality 注意

この protocol は evaluation worker を実行しません。承認済み configuration が
worker/model channel を使ったかどうかを記録するだけです。

`worker_channel_used` が `true` の場合は次を守ってください。

- model/control-plane channel を confidential dependency として扱う
- prompt、transcript、raw worker output を confidential operational artifact として扱う
- それらを `holdout-metadata.json`、`holdout-aggregate.json`、commit message、Issue、
  public report にコピーしない
- read-only sandbox や auxiliary network access 無効化を、private corpus に対する
  完全な confidentiality boundary と見なさない
- schema が要求する bounded identifier のみを記録する
  - worker profile ID
  - worker CLI version
  - model ID
  - effort
  - digest
  - aggregate metric

## Adjudication protocol

この protocol では adjudication は必須です。

private ground truth の dispute や repeated aggregate result の解釈差異は、case-level data を
露出させずに adjudication で解決します。repository に見せてよい surface は次だけです。

- `adjudication.completed: true`
- `disputed_case_count`
- `changed_ground_truth_count`
- `record_digest`

元の adjudication note、evidence、reviewer discussion は restricted system にのみ保存します。

## Validation procedure

検証対象は external directory に置かれた aggregate-only record だけです。
record が synthetic かつ non-sensitive であれば、disposable な local example を使って構いません。

Example flow:

```bash
REPO_ROOT=/absolute/path/to/genai-repo-auditor
WORKSPACE_ROOT=/absolute/path/to/workspace-containing-the-repo
RECORDS_ROOT="$WORKSPACE_ROOT/.codex-local/tmp/private-holdout-example"

mkdir -p "$RECORDS_ROOT"

cat > "$RECORDS_ROOT/holdout-metadata.json" <<'JSON'
{
  "schema_version": "1",
  "corpus": {
    "corpus_id": "holdout-012345abcdef",
    "corpus_version": "1.0.0+sha256.aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "case_count": 12,
    "positive_count": 6,
    "negative_control_count": 6,
    "category_count": 4,
    "balanced_controls": true,
    "balance_exception_record_digest": null
  },
  "separation": {
    "private_not_tracked": true,
    "public_corpus_reused": false,
    "real_repository_content_included": false,
    "storage_access_controlled": true
  },
  "ground_truth_review": {
    "review_method": "two-person",
    "reviewer_count": 2,
    "independent_from_evaluation": true,
    "completed": true,
    "review_record_digests": [
      "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
      "sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
    ]
  },
  "evaluation_plan": {
    "command_version": "0.9.0",
    "report_schema_version": "1",
    "adjudication_required": true,
    "configurations": [
      {
        "configuration_id": "config-012345abcdef",
        "workflow_version": "sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
        "prompt_version": "sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
        "worker_channel_used": false,
        "worker_profile_id": null,
        "worker_cli_version": null,
        "model_id": null,
        "effort": null,
        "repeat_runs": 2
      }
    ]
  }
}
JSON

cat > "$RECORDS_ROOT/holdout-aggregate.json" <<'JSON'
{
  "schema_version": "1",
  "evaluation_id": "evaluation-012345abcdef",
  "command_version": "0.9.0",
  "report_schema_version": "1",
  "corpus": {
    "corpus_id": "holdout-012345abcdef",
    "corpus_version": "1.0.0+sha256.aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "case_count": 12,
    "positive_count": 6,
    "negative_control_count": 6,
    "category_count": 4,
    "balanced_controls": true,
    "balance_exception_record_digest": null
  },
  "configurations": [
    {
      "configuration_id": "config-012345abcdef",
      "workflow_version": "sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
      "prompt_version": "sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
      "worker_channel_used": false,
      "worker_profile_id": null,
      "worker_cli_version": null,
      "model_id": null,
      "effort": null,
      "repeat_runs": 2,
      "runs": [
        {
          "run_number": 1,
          "evaluated_negative_control_count": 6,
          "negative_control_false_positive_case_count": 1,
          "counts": {
            "true_positives": 5,
            "false_positives": 1,
            "false_negatives": 1,
            "true_negatives": 5,
            "prediction_count": 6
          },
          "rates": {
            "precision": 0.833333,
            "recall": 0.833333,
            "f1": 0.833333
          },
          "severity_agreement": {
            "agreed": 4,
            "eligible": 5,
            "rate": 0.8
          },
          "target_coverage": {
            "covered": 12,
            "selected": 12,
            "rate": 1.0
          },
          "human_review_required_count": 2
        },
        {
          "run_number": 2,
          "evaluated_negative_control_count": 6,
          "negative_control_false_positive_case_count": 0,
          "counts": {
            "true_positives": 4,
            "false_positives": 0,
            "false_negatives": 2,
            "true_negatives": 6,
            "prediction_count": 4
          },
          "rates": {
            "precision": 1.0,
            "recall": 0.666667,
            "f1": 0.8
          },
          "severity_agreement": {
            "agreed": 3,
            "eligible": 4,
            "rate": 0.75
          },
          "target_coverage": {
            "covered": 12,
            "selected": 12,
            "rate": 1.0
          },
          "human_review_required_count": 3
        }
      ],
      "repeat_variance": {
        "precision": {
          "applicable_run_count": 2,
          "minimum": 0.833333,
          "maximum": 1.0,
          "mean": 0.916667,
          "population_variance": 0.006944
        },
        "recall": {
          "applicable_run_count": 2,
          "minimum": 0.666667,
          "maximum": 0.833333,
          "mean": 0.75,
          "population_variance": 0.006944
        },
        "f1": {
          "applicable_run_count": 2,
          "minimum": 0.8,
          "maximum": 0.833333,
          "mean": 0.816666,
          "population_variance": 0.000278
        },
        "severity_agreement": {
          "applicable_run_count": 2,
          "minimum": 0.75,
          "maximum": 0.8,
          "mean": 0.775,
          "population_variance": 0.000625
        },
        "target_coverage": {
          "applicable_run_count": 2,
          "minimum": 1.0,
          "maximum": 1.0,
          "mean": 1.0,
          "population_variance": 0.0
        },
        "human_review_required_count": {
          "applicable_run_count": 2,
          "minimum": 2,
          "maximum": 3,
          "mean": 2.5,
          "population_variance": 0.25
        }
      }
    }
  ],
  "adjudication": {
    "completed": true,
    "disputed_case_count": 1,
    "changed_ground_truth_count": 0,
    "record_digest": "sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
  },
  "safety": {
    "aggregate_only": true,
    "fixture_text_included": false,
    "case_ids_included": false,
    "evidence_or_locations_included": false,
    "prompts_or_transcripts_included": false,
    "credentials_included": false,
    "absolute_paths_included": false,
    "finding_publication_performed": false
  },
  "publication": {
    "approved": false,
    "approval_record_digest": null,
    "public_claim_allowed": false,
    "production_performance_claim_allowed": false,
    "finding_publication_authorized": false
  }
}
JSON

(
  cd "$REPO_ROOT"
  bin/gra-efficacy-holdout --records-root "$RECORDS_ROOT"
)
```

この example は disposable な non-sensitive placeholder data だけを使います。
実 holdout fixture に置き換えて repository 内へ置いてはいけません。

native Windows では、checkout 外の access-controlled directory に同じ 2 record を
作成した後、PowerShell から検証します。

```powershell
$RecordsRoot = Join-Path $env:LOCALAPPDATA "GenAIRepoAuditor\private-holdout-records"
gra-efficacy-holdout --records-root $RecordsRoot
if ($LASTEXITCODE -ne 0) { throw "private holdout validation failed" }
```

この validation-only command は、native Windows で未対応の efficacy report generation
path を使用しません。install matrix は Windows、macOS、Ubuntu で semantic validation を
実行します。

## Internal reporting と public publication

restricted internal reporting では、validated aggregate metric、variance、
adjudication status、workflow 差分を扱えます。ただし case-level / evidence-level の内容は
引き続き除外しなければなりません。

public publication は internal reporting より厳格です。

- 承認済み aggregate summary のみを公開する
- aggregate-only を維持する
- `public_claim_allowed: false` を維持する
- `production_performance_claim_allowed: false` を維持する
- `finding_publication_authorized: false` を維持する
- corpus version、command version、configuration ID、repeat count、
  worker/model channel 使用有無を明記する
- これは private holdout aggregate であり、production recall / precision の証拠ではないと
  明示する

承認は benchmark を finding publication workflow に変えるものではありません。
別管理の approval record digest で参照される bounded aggregate statement を許可するだけです。

## Finding と claim の制限

private holdout benchmark は repository finding の公開を許可しません。

この protocol を使って次の claim をしてはいけません。

- production 全体に対する product-wide recall / precision
- model、workflow、provider、effort level の優劣
- real repository における finding の検証完了
- target repository の release safety
- vulnerability report、Issue、advisory、case study の公開許可

この benchmark surface は aggregate evaluation control 専用です。
repository finding の公開は、引き続き repository 固有の evidence、validation、
disclosure、approval workflow で管理されます。
