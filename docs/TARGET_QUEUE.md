# Target Queue

`reports/targets.json` is the queue of bounded security research units.

A target should be smaller than a repository audit and larger than a single file grep. Good targets include:

- tenant-scoped API authorization
- webhook authenticity and replay handling
- file upload parser and path traversal paths
- GitHub Actions `pull_request_target` and token-permission risks
- admin API privilege boundaries
- outbound URL fetchers and SSRF-relevant paths

Generate targets:

```bash
gra-targets --run runs/OWNER__REPO/RUN_ID --generate
```

List targets:

```bash
gra-targets --run runs/OWNER__REPO/RUN_ID --list
```

Show one target:

```bash
gra-targets --run runs/OWNER__REPO/RUN_ID --show TGT-001
```

Mark status manually:

```bash
gra-targets --run runs/OWNER__REPO/RUN_ID --mark TGT-001 skipped
```

Allowed statuses:

```text
queued
in_progress
reviewed
skipped
needs_human_review
```

Research a target:

```bash
gra-research --run runs/OWNER__REPO/RUN_ID --target TGT-001
```

Deep research with `/goal`:

```bash
gra-research --run runs/OWNER__REPO/RUN_ID --target TGT-001 --mode goal
```
