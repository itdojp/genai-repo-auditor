#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path

from template_env import PLACEHOLDER_PATTERN, build_template_values, is_denied_placeholder

if len(sys.argv) != 3:
    print("Usage: render_template.py TEMPLATE OUT", file=sys.stderr)
    raise SystemExit(2)


def main() -> int:
    template_path = Path(sys.argv[1])
    out = Path(sys.argv[2])
    template = template_path.read_text(encoding="utf-8")
    try:
        values = build_template_values(os.environ)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    unknown: list[str] = []
    denied_names: list[str] = []

    def repl(match) -> str:
        name = match.group(1)
        if is_denied_placeholder(name):
            denied_names.append(name)
            return match.group(0)
        if name not in values:
            unknown.append(name)
            return match.group(0)
        return str(values[name])

    out_text = PLACEHOLDER_PATTERN.sub(repl, template)
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
