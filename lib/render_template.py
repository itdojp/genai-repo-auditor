#!/usr/bin/env python3
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

if len(sys.argv) != 3:
    print("Usage: render_template.py TEMPLATE OUT", file=sys.stderr)
    raise SystemExit(2)

DENYLIST_RE = re.compile(r"(?:TOKEN|SECRET|KEY|PASSWORD|COOKIE|SESSION|CREDENTIAL)")
CONTROLLED_PREFIX = "GRA_TEMPLATE_"

# Explicitly supported template placeholders. Values may come from defaults,
# same-named environment variables, or controlled GRA_TEMPLATE_<NAME> variables.
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

pattern = re.compile(r"{{([A-Z0-9_]+)}}")
name_re = re.compile(r"^[A-Z0-9_]+$")


def denied(name: str) -> bool:
    return bool(DENYLIST_RE.search(name))


def build_values() -> dict[str, str]:
    values = dict(defaults)
    for key in defaults:
        if key in os.environ and not denied(key):
            values[key] = os.environ[key]
    for key, value in os.environ.items():
        if not key.startswith(CONTROLLED_PREFIX):
            continue
        placeholder = key[len(CONTROLLED_PREFIX):]
        if not placeholder or not name_re.fullmatch(placeholder):
            raise ValueError(f"invalid controlled template placeholder name: {key}")
        if denied(placeholder):
            raise ValueError(f"denied controlled template placeholder: {placeholder}")
        values[placeholder] = value
    return values


def main() -> int:
    template_path = Path(sys.argv[1])
    out = Path(sys.argv[2])
    template = template_path.read_text(encoding="utf-8")
    try:
        values = build_values()
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    unknown: list[str] = []
    denied_names: list[str] = []

    def repl(match: re.Match[str]) -> str:
        name = match.group(1)
        if denied(name):
            denied_names.append(name)
            return match.group(0)
        if name not in values:
            unknown.append(name)
            return match.group(0)
        return str(values[name])

    out_text = pattern.sub(repl, template)
    if denied_names or unknown:
        for name in sorted(set(denied_names)):
            print(f"ERROR: denied template placeholder: {name}", file=sys.stderr)
        for name in sorted(set(unknown)):
            print(f"ERROR: unknown template placeholder: {name}", file=sys.stderr)
        return 2

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(out_text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
