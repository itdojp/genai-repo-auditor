# GitHub bootstrap

Repository:

```text
https://github.com/itdojp/genai-repo-auditor
```

Recommended settings:

- Visibility: public
- Default branch: `main`
- Issues: enabled
- Pull requests: enabled
- Wiki: disabled unless needed
- Discussions: optional, disabled initially
- Actions: enabled for lint workflow only
- Branch protection for `main`: required after first push
- Secret scanning / push protection: enable where available
- Dependabot alerts: enable

## Initial import

```bash
git clone git@github.com:itdojp/genai-repo-auditor.git
cd genai-repo-auditor

# Copy the generated file set into this repository root.
# Then run validation:
chmod +x bin/*
bash -n bin/*
python3 -m py_compile lib/*.py bin/gra-*

git status --short
git add .
git commit -m "Initial import of GenAI Repo Auditor"
git push -u origin main
```

## Post-import branch protection

After the initial push, protect `main`:

- Require pull request before merging
- Require at least one approval
- Dismiss stale approvals
- Require status checks to pass
- Require the `lint` workflow
- Disable force pushes
- Disable branch deletion

## Labels

Suggested labels:

```text
security
appsec
agentic-audit
scanner-triage
variant-analysis
severity-critical
severity-high
severity-medium
severity-low
confidence-high
confidence-medium
needs-human-review
false-positive
accepted-risk
```
