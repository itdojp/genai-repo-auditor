# Variant Analysis

Variant analysis searches for structurally similar instances of an already identified root cause.

Use it after a finding has been reviewed and is at least `Probable`.

```bash
gra-variant --run runs/OWNER__REPO/RUN_ID --finding SEC-001
```

Supervised `/goal` mode:

```bash
gra-variant --run runs/OWNER__REPO/RUN_ID --finding SEC-001 --mode goal
```

Examples of useful seeds:

- missing tenant filter in ORM queries
- webhook handler missing signature verification
- CI workflow using untrusted PR input with privileged token
- file path derived from user input before normalization
- outbound URL fetcher that allows internal addresses

Rules:

- Search for the root-cause pattern, not identical syntax.
- Reject candidates that are not reachable or are mitigated.
- Do not generate exploit payloads.
- Use static call-path reasoning and benign local validation only.
