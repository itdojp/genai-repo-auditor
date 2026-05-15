# Report contract

Codex は以下を `reports/` に生成する必要があります。

```text
reports/
  AUDIT_SUMMARY.md
  THREAT_MODEL.md
  ATTACK_SURFACE.md
  FINDINGS.md
  findings.json
  AUDIT_LOG.md
  issue-drafts/
    SEC-001.md
```

## findings.json

`findings.json` は Issue 作成の唯一の機械可読入力です。Markdownではなくstrict JSONです。

重要フィールド:

```text
run_id
repo
commit
generated_at
findings[].id
findings[].fingerprint
findings[].severity
findings[].confidence
findings[].status
findings[].affected_locations
findings[].entry_point
findings[].trust_boundary
findings[].source_to_sink
findings[].evidence
findings[].minimal_remediation
findings[].issue_title
findings[].issue_body_file
findings[].issue_recommended
findings[].labels
```

## finding quality bar

Critical / High finding は以下を満たす必要があります。

- concrete file:line
- entry point
- trust boundary
- call path or source-to-sink
- impact
- evidence
- validation status
- minimal remediation
- regression test idea

満たせないものは `Potential` または `Needs human review` に落とします。
