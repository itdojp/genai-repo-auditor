#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

shellcheck \
  scripts/validate-shellcheck.sh \
  bin/gra-audit \
  bin/gra-batch \
  examples/staged-agentic-workflow.sh.example
