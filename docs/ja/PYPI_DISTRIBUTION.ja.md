# PyPI 配布と trusted publishing

## readiness の判断

リポジトリ側の package は、人間が統制する TestPyPI trial と、その trial をレビューした後に別途承認する production PyPI publication に向けて準備できています。
外部 activation は**まだ完了していません**。

- `genai-repo-auditor` project name の利用可否と ownership は、該当する PyPI account で人間が確認するまで分かりません。
- このリポジトリ変更では、PyPI と TestPyPI の project / pending publisher はいずれも設定しません。
- `testpypi` と `pypi` の GitHub environment は maintainer が作成し、保護する必要があります。
- 最初の upload と metadata review が成功するまで、package URL は承認済みではありません。

pending publisher は project name を予約しません。最初の upload の直前に name を再確認してください。未認証の検索結果や一時的な 404 response から利用可能性を推定してはいけません。

推奨 rollout は TestPyPI を先に行うことです。production PyPI は別個の判断であり、さらに workflow は production upload の前に対応する GitHub Release の完全な asset set を download して検証します。

## 配布契約

canonical version は引き続き [`VERSION`](../../VERSION) です。同じ値が package metadata、`gra-* --version`、annotated Git tag `vX.Y.Z`、GitHub Release、PyPI distribution metadata に使われます。PyPI workflow は tag を作成・移動・force-push しません。

[`pyproject.toml`](../../pyproject.toml) では、次を宣言しています。

- distribution name `genai-repo-auditor`
- Apache-2.0 license expression と repository-owned README metadata
- Python `>=3.10,<3.13`。これは、検証済みの Python 3.10-3.12 support window と一致します。
- 完全な `gra-*` console-script surface
- commands、libraries、prompts、schemas、taxonomies、workflow profiles、public synthetic efficacy corpus の package data

[`MANIFEST.in`](../../MANIFEST.in) は、sdist から tests と local/generated root を除外します。public regression fixture は Git repository と GitHub source archive では引き続き利用できますが、PyPI package の install には不要です。

[`scripts/validate_python_distribution.py`](../../scripts/validate_python_distribution.py) は、wheel と sdist がそれぞれちょうど 1 つ存在することを要求し、metadata と期待される runtime resource をすべて検査し、安全でない archive path と link を拒否し、local run、target clone、scanner result、Issue draft、transcript、database、SARIF、holdout、test path を拒否します。これは structural boundary であり、追跡対象 source content の review を置き換えるものではありません。

## ワークフローと権限境界

guard された workflow は [`publish-pypi.yml`](../../.github/workflows/publish-pypi.yml) です。manual-only であり、通常の push や pull request では distribution を upload できません。

read-only の `build-candidate` job は次を実行します。

1. persisted credentials を使わず、明示的に dispatch された ref を checkout します。
2. upload が要求された場合、`main` 上またはその祖先 commit にある、正確な annotated `v$VERSION` tag を要求します。
3. production PyPI の前には対応する GitHub Release を download し、正確な asset set と checksum を検証し、manifest の tag と source commit を dispatch ref および `github.sha` に結び付けます。production release publication 前の TestPyPI trial は引き続き許可します。
4. build/check tooling を hash-lock 済み dependency file から pip cache なしで install し、build isolation なしで wheel と sdist をそれぞれ 1 つずつ build します。
5. strict `twine check` と repository distribution validator を実行します。
6. 正確な wheel と sdist をそれぞれ独立に install し、smoke test します。
7. checksum と正確な source commit を、7 日間保持される workflow artifact に記録します。

conditional な upload job は 1 つだけ実行されます。

| Index | GitHub environment | PyPI publisher binding | Additional condition |
|---|---|---|---|
| TestPyPI | `testpypi` | repository `itdojp/genai-repo-auditor`、workflow `publish-pypi.yml`、environment `testpypi` | `main` 上の正確な annotated tag |
| PyPI | `pypi` | repository `itdojp/genai-repo-auditor`、workflow `publish-pypi.yml`、environment `pypi` | `main` 上の正確な annotated tag と、対応する checksum-valid な GitHub Release asset および manifest |

各 upload job には、read-only の environment-policy API 検査用 `actions: read`、release access 用 `contents: read`、publication 用 `id-token: write` を与えます。OIDC permission は build job と top-level workflow にはありません。upload には official の `pypa/gh-action-pypi-publish` action を使い、review 済みの v1.14.0 commit に pin しています。`PYPI_API_TOKEN`、password、長期有効な upload secret は受け付けません。

各 upload job の最初の step は、environment-level variable `PYPI_TRUSTED_PUBLISHING_APPROVED` が destination（`testpypi` または `pypi`）と一致することを要求します。次の step は GitHub API を照会し、正確な environment が存在し、required reviewer が空でなく、self-review prevention が有効で、custom deployment policy が `v*` tag pattern の 1 件だけであることを要求します。存在しない environment は GitHub Actions により protection なしで自動作成され得るため、marker または protection がない場合は candidate download や OIDC publication より前に fail します。同名 marker を repository scope または organization scope に作成することは禁止します。marker 単独と異なり、API check は実 environment の protection を独立して検証します。

download した candidate は checksum で検証され、action が短期の trusted-publishing credential を取得する前に `github.sha` と結び付けられます。production では publication 直前に live GitHub Release も再 download し、正確な asset set、manifest、release checksum list が review 済み candidate binding と byte-for-byte で一致することを要求します。

PyPI attestation は、どちらの trusted-publishing destination でも有効です。これらは GitHub source-release checksum、SBOM、GitHub artifact attestation を補完しますが、置き換えるものではありません。

## 脅威モデル

| Threat | Repository control | Residual / human control |
|---|---|---|
| PR や通常の push が package を upload する | workflow は `workflow_dispatch` のみで、upload job も `publish=true` を要求します。 | workflow 自体の変更に対しては、引き続き branch protection と review が防御になります。 |
| tag/version の差し替え | 正確な annotated tag、`VERSION`、checkout 済み commit、`main` ancestry、candidate source commit、package metadata がすべて一致しなければなりません。 | maintainer は release review と `main` CI の green を確認した後にのみ tag を作成します。 |
| 長期 credential の窃取 | trusted publishing は GitHub OIDC を使い、PyPI token secret を参照しません。 | maintainer は repository secret や environment secret に token fallback を追加してはいけません。 |
| 過剰な OIDC 権限 | `id-token: write` は conditional かつ environment-gated な upload job にのみ存在します。 | pin された publish action と download action は、引き続き信頼された dependency とし、更新時には review が必要です。 |
| build dependency の差し替え | build/check dependency と transitive dependency は version と hash で lock し、pip cache と isolated-build download を無効にします。 | tooling 更新時には maintainer が lock の変更を review し、意図的に再生成する必要があります。 |
| 未レビューの package content | structural archive validation、strict metadata check、独立した wheel/sdist install、resource smoke test、checksum binding を upload 前に実行します。 | tracked source と download された candidate は人間が review してください。structural check だけでは source content に機微情報がないことは証明できません。 |
| 誤った、または未保護の publisher environment | 固定 name、destination marker、read-only API check により、実 environment に reviewer、self-review prevention、`v*` のみの deployment policy がなければ OIDC より前に fail します。 | publisher record は引き続き完全一致させ、外部所有の protection と marker を maintainer が設定します。 |
| 重複・部分的・誤 index の release | TestPyPI を最初の rollout とし、production は別 environment で、さらに GitHub Release を要求します。skip-existing 動作は有効化していません。 | PyPI file と version は immutable です。失敗または部分的な release は調査が必要であり、通常は上書きではなく新しい version を使います。 |
| project name の takeover | 利用可能性は主張しておらず、pending publisher でも name は予約されません。 | publisher 設定時と最初の upload 直前に、ownership と name availability を確認してください。 |

## upload なしの repository validation

ignore される local storage で build と validation を実行します。

```bash
python3 -m venv .codex-local/venvs/pypi-readiness
.codex-local/venvs/pypi-readiness/bin/python -m pip install \
  --require-hashes --no-cache-dir \
  -r .github/requirements/publish-build.txt
rm -rf .codex-local/tmp/pypi-dist
.codex-local/venvs/pypi-readiness/bin/python -m build \
  --no-isolation --outdir .codex-local/tmp/pypi-dist
.codex-local/venvs/pypi-readiness/bin/python -m twine check --strict \
  .codex-local/tmp/pypi-dist/*
python3 scripts/validate_python_distribution.py \
  --dist-dir .codex-local/tmp/pypi-dist
```

workflow でも、OIDC や upload を使わずに candidate を build して保持できます。

```bash
gh workflow run publish-pypi.yml \
  --ref main \
  -f publish=false \
  -f index=testpypi
```

upload を設定または承認する前に、workflow artifact を review してください。

## 人手で統制する外部設定

Codex と repository automation は、これらの account 操作を実行してはいけません。

1. 対象となる TestPyPI と PyPI の owner account に sign in し、project name / ownership state を確認します。新規 project の場合は pending publisher を作成し、既存 project の場合は project の Publishing settings で publisher を追加します。
2. GitHub で、名前を正確に `testpypi` と `pypi` とした environment を作成します。readiness marker を追加する前に、少なくとも 1 人の required reviewer、self-review prevention、custom deployment branches and tags を設定し、deployment policy は `v*` tag pattern の 1 件だけを追加します。workflow の read-only GitHub API gate は、この最小構成との完全一致を要求します。どちらの environment にも PyPI API token は保存してはいけません。
3. protection rule の保存後にのみ、environment-level variable `PYPI_TRUSTED_PUBLISHING_APPROVED` を追加します。`testpypi` environment の値は `testpypi`、`pypi` environment の値は `pypi` とします。この variable を repository scope または organization scope に作成してはいけません。variable がない場合、upload job は OIDC publication 前に fail closed します。
4. TestPyPI trusted publisher を次の値で設定します。
   - owner: `itdojp`
   - repository: `genai-repo-auditor`
   - workflow: `publish-pypi.yml`
   - environment: `testpypi`
5. production PyPI trusted publisher は、同じ owner、repository、workflow と、environment `pypi` で設定します。
6. project-name ownership を再確認します。正確な annotated release tag、成功した `main` CI、package candidate、metadata、checksum、environment reviewer list を review してください。
7. 最初の TestPyPI trial は、正確な tag から承認して実行します。

   ```bash
   gh workflow run publish-pypi.yml \
     --ref vX.Y.Z \
     -f publish=true \
     -f index=testpypi
   ```

8. TestPyPI metadata を確認し、dependency fallback なしで正確な version を install します。

   ```bash
   python3 -m venv .codex-local/tmp/testpypi-verify
   .codex-local/tmp/testpypi-verify/bin/python -m pip install \
     --index-url https://test.pypi.org/simple/ \
     --no-deps genai-repo-auditor==X.Y.Z
   .codex-local/tmp/testpypi-verify/bin/gra-audit --version
   .codex-local/tmp/testpypi-verify/bin/gra-doctor --help
   ```

9. TestPyPI の結果、GitHub Release、正確な public metadata、environment approval がすべて受け入れられた後にのみ、同じ tag から `index=pypi` を別途 dispatch します。approved public package URL を記録する前に、production package、attestation、console script、metadata を確認してください。

README に未検証の PyPI URL や index-based install command を追加してはいけません。

## 障害時の扱い

- OIDC が publisher mismatch を報告した場合は、owner、repository、workflow filename、environment、event/ref claim を正確に比較してください。token workaround を追加してはいけません。
- environment readiness、tag、version、`main` ancestry、GitHub Release asset set / manifest、source commit、checksum、metadata、archive、install、smoke validation のいずれかに失敗した場合は publication を停止し、source または外部 protection を該当する review 済み process で修正してください。
- release tag を上書き、移動、再利用してはいけません。skip-existing を有効化してはいけません。
- PyPI では、upload 済み distribution file を置き換えられません。部分的 upload は release incident として扱い、再公開が必要な場合は review 済みの新しい version を使ってください。

## 公式リファレンス

- [Adding a publisher to an existing PyPI project](https://docs.pypi.org/trusted-publishers/adding-a-publisher/)
- [Creating a project with a pending publisher](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/)
- [Publishing with a trusted publisher](https://docs.pypi.org/trusted-publishers/using-a-publisher/)
- [Trusted publisher internals](https://docs.pypi.org/trusted-publishers/internals/)
- [Trusted publisher troubleshooting](https://docs.pypi.org/trusted-publishers/troubleshooting/)
- [PyPI attestations](https://docs.pypi.org/attestations/producing-attestations/)
- [GitHub OIDC reference](https://docs.github.com/en/actions/reference/security/oidc)
- [GitHub deployment environments](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments)
- [GitHub REST API for deployment environments](https://docs.github.com/en/rest/deployments/environments)
- [GitHub REST API for deployment branch policies](https://docs.github.com/en/rest/deployments/branch-policies)
- [`pypa/gh-action-pypi-publish`](https://github.com/pypa/gh-action-pypi-publish)
