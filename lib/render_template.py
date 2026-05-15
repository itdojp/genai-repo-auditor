#!/usr/bin/env python3
import os
import re
import sys
from pathlib import Path

if len(sys.argv) != 3:
    print("Usage: render_template.py TEMPLATE OUT", file=sys.stderr)
    raise SystemExit(2)

template = Path(sys.argv[1]).read_text(encoding="utf-8")

# Keep known defaults, then allow arbitrary environment variables to be used
# as {{PLACEHOLDER}} values by scripts.
defaults = {
    "RUN_ID": "",
    "REPO": "",
    "REPO_SLUG": "",
    "BRANCH": "",
    "COMMIT": "",
    "VISIBILITY": "UNKNOWN",
    "RUN_DIR": "",
    "REPO_DIR": "",
    "TARGET_REPO_DIR": "repo",
    "REPORTS_DIR": "reports",
    "REPORT_DIR": "",
    "TARGET_ID": "",
    "TARGET_CATEGORY": "",
    "TARGET_SCOPE": "",
    "TARGET_FILE": "",
    "FINDING_ID": "",
    "VARIANT_SOURCE": "",
    "SCANNER_INDEX": "reports/scanner-results/scanner-index.json",
}
values = {**defaults, **os.environ}

pattern = re.compile(r"{{([A-Z0-9_]+)}}")

def repl(match: re.Match[str]) -> str:
    return str(values.get(match.group(1), match.group(0)))

out_text = pattern.sub(repl, template)
out = Path(sys.argv[2])
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(out_text, encoding="utf-8")
