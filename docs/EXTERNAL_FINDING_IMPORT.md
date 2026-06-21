# External Finding Import

`gra-import-findings` normalizes a conservative, vendor-neutral JSON contract
from managed AI security tools, deterministic scanners, or internal review
systems into local GenAI Repo Auditor artifacts.

The command does not call vendor APIs, does not run external scanners, and does
not claim support for proprietary exports without explicit fixtures and tests.
It is a local import bridge: external records become review leads first, and
publication still goes through the normal `findings.json` and `gra-issues`
controls.

## Input contract

The initial supported format is generic JSON:

```json
{
  "source": "external-tool-name",
  "source_version": "optional",
  "findings": [
    {
      "external_id": "EXT-001",
      "title": "Potential command injection",
      "severity": "High",
      "confidence": "Medium",
      "status": "Potential",
      "category": "command-injection",
      "affected_locations": [{"file": "src/app.py", "line": 10}],
      "evidence": "bounded external evidence text",
      "minimal_remediation": "Use an argv array and validate inputs"
    }
  ]
}
```

Supported severity values are `Critical`, `High`, `Medium`, `Low`, and
`Informational`. Supported confidence values are `High`, `Medium`, and `Low`.
Supported status values are `Confirmed`, `Probable`, `Potential`,
`Informational`, `Invalid`, and `Needs human review`. Common lowercase aliases
are normalized.

`affected_locations[].file` must be a repository-relative path using `/`
separators. Absolute paths, `..`, empty segments, Windows paths, and home
expansion are rejected.

## Review-only import

Default mode writes import artifacts only and does not modify
`reports/findings.json`:

```bash
gra-import-findings --run runs/OWNER__REPO/RUN_ID --file external-findings.json
```

Outputs:

```text
reports/imported-findings.json
reports/IMPORTED_FINDINGS.md
```

`imported-findings.json` contains:

- normalized findings with `append_status=review-only`;
- rejected leads with explicit rejection reasons;
- source metadata, input counts, and source file digest metadata;
- redacted and bounded evidence/remediation strings.

Invalid per-record data is retained under `rejected_findings`; valid records are
not silently mixed with invalid data. Malformed top-level JSON, missing source,
or a non-array `findings` field is a command error.

## Explicit append mode

Append mode is opt-in:

```bash
gra-import-findings --run runs/OWNER__REPO/RUN_ID --file external-findings.json --append-findings
```

When enabled, each valid normalized record is converted into a
`findings.json`-compatible finding with:

- stable `IMP-...` ID;
- stable fingerprint derived from source, external ID, title, location, severity,
  and redacted evidence;
- `external_source` metadata (`source`, `source_version`, `external_id`,
  `input_index`, `imported_at`);
- `issue_recommended=false` and empty `issue_body_file` by default;
- `Not assessed` structured assessment dimensions.

Duplicate fingerprints already present in `reports/findings.json` or repeated
within the same import are not appended again. They are recorded as
`append_status=duplicate-skipped` in `imported-findings.json`.

## Validation and publication

Validate after import:

```bash
gra-validate-report --run runs/OWNER__REPO/RUN_ID
```

The validator checks `templates/reports/imported-findings.schema.json`, summary
counts, rejected lead reasons, safe affected-location paths, source metadata,
append status consistency, duplicate-skip consistency, and obvious unredacted
full secrets.

Appended imported findings do not bypass issue-publication controls. They are
review-gated by default because `issue_recommended=false`. To publish an
imported finding, a human reviewer should first validate the finding locally,
update the finding fields and issue draft, then use the normal issue workflow:

```bash
gra-issues --run runs/OWNER__REPO/RUN_ID --plan
gra-issues --run runs/OWNER__REPO/RUN_ID --publish
```

## Safety and privacy

- The command stores only the input file name, SHA-256 digest, and size; it does
  not store an absolute source-file path.
- Evidence and remediation text are passed through the same bounded redaction
  helper used by scanner normalization.
- Imported findings are local artifacts and must not be committed when they are
  generated from private or third-party repositories.
- Proprietary adapters should be added only with sample fixtures, explicit
  schema tests, and no network access by default.
