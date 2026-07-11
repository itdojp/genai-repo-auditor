# 決定的セキュリティ efficacy benchmark

`gra-efficacy-benchmark` は、version 管理された synthetic corpus を offline の
決定的 reference detector で実行し、上限付きの score report を生成します。
検証対象は corpus loader、case 選択、score 計算、report contract です。

このコマンドは `gra-benchmark` と目的が異なります。

- `gra-efficacy-benchmark`: synthetic security ground truth の score を計算する。
- `gra-benchmark`: audit run の workflow health と publication safety gate を評価する。

reference detector は runner/scoring の smoke baseline であり、製品の検出性能を
示すものではありません。いずれも人による security review の代替ではありません。

## 安全境界

fixture mode は package 内の非 deployable synthetic file だけを読み取ります。
network、GitHub、model、worker、scanner、shell command、repository audit を実行せず、
Issue を公開しません。report に fixture source、raw evidence、finding body を含めません。

corpus integrity、case 選択、closed report schema、output path のいずれかが不正な場合は
fail closed になります。output の親 directory と file に symlink は使用できません。
report 書き込みには Python/OS の directory-relative file operation が必要です。
未対応 platform では output 作成前に fail closed になりますが、`--list`、`--help`、
`--version` は使用できます。JSON と Markdown はそれぞれ 1,000,000 bytes が上限です。

## case の一覧と選択

```bash
# default の core suite
gra-efficacy-benchmark --list

# category suite
gra-efficacy-benchmark --list --suite appsec

# 個別 case。--case は複数回指定できる
gra-efficacy-benchmark --list \
  --case python-web/authz-001 \
  --case python-web/authz-control-001
```

現在の suite は `core`、`agentic`、`appsec`、`automation`、`supply-chain` です。
`--suite` と `--case` は同時指定できません。

## 実行と出力

```bash
gra-efficacy-benchmark
```

default output:

```text
reports/efficacy-benchmark.json
reports/EFFICACY_BENCHMARK.md
```

出力先は `--out-json` と `--out-md` で変更できます。JSON は
`templates/reports/efficacy-benchmark.schema.json` に従い、case ID、分類、結果、
TP/FP/FN/TN、precision、recall、F1、severity agreement、target coverage、
human-review count、version、安全境界、解釈上の制限のみを記録します。

## 決定性の確認

同一 checkout、corpus version、command version、case 選択、出力形式では、2 回の
実行結果が byte 単位で一致する必要があります。report には時刻、duration、hostname、
絶対 fixture path、PID、random run ID を含めません。

```bash
mkdir -p .test-tmp/efficacy
gra-efficacy-benchmark --out-json .test-tmp/efficacy/a.json --out-md .test-tmp/efficacy/a.md
gra-efficacy-benchmark --out-json .test-tmp/efficacy/b.json --out-md .test-tmp/efficacy/b.md
cmp .test-tmp/efficacy/a.json .test-tmp/efficacy/b.json
cmp .test-tmp/efficacy/a.md .test-tmp/efficacy/b.md
```

## 解釈と異常時対応

synthetic score が完全でも、pinned reference rule と pinned fixture が一致したことだけを
示します。production repository に対する recall、precision、severity accuracy、model
quality、language/framework 対応を証明しません。benchmark 由来 finding の自動公開は禁止です。

exit status `0` は一覧または report 生成の成功です。status `2` は引数、corpus、selection、
schema、output safety の異常です。stderr を確認して local contract または出力先を修正し、
再実行してください。integrity error や symlink error を迂回してはいけません。
native Windows CPython など必要な dirfd operation がない環境では `--list` を使用し、
report 生成は WSL2/Linux/macOS で実行してください。comparison と optional worker mode
も最終 report pair を同じ安全境界で publish するため、native Windows では未対応です。
[`WINDOWS_WSL_SUPPORT.ja.md`](WINDOWS_WSL_SUPPORT.ja.md) を参照してください。

corpus の構造と変更手順は英語 canonical 文書
[`EFFICACY_BENCHMARK_CORPUS.md`](../EFFICACY_BENCHMARK_CORPUS.md) を参照してください。

## configuration 比較

```bash
gra-efficacy-benchmark --list-configurations
gra-efficacy-benchmark --compare
```

default comparison は 2 つの決定的 reference configuration を同じ case で比較し、
`reports/efficacy-comparison.json` と `reports/EFFICACY_COMPARISON.md` を生成します。
worker は実行しません。

worker-assisted comparison は `--compare --worker --worker-dir DIR` の明示 opt-in と Codex CLI
0.135.0 以上が必要です。DIR は current working directory 配下の既存 non-symlink directory とし、
cwd 自体は指定せず、version control で ignore してください。
read-only sandbox と sandbox network disabled を固定し、ephemeral session を使用して user
configuration と project/user rule を読み込みません。model/control-plane channel は使用します。
artifact は指定した local directory に保持され、worker row は非決定的です。read-only sandbox は
host-readable file 全体の confidentiality boundary ではないため、必要なら別の host isolation を
使用してください。

方法論、禁止 claim、公開判断は
[`EFFICACY_CLAIMS_AND_PUBLICATION.ja.md`](EFFICACY_CLAIMS_AND_PUBLICATION.ja.md) を参照してください。
