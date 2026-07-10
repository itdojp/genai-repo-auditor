#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

fail() {
  echo "install smoke: $*" >&2
  exit 1
}

tmp_parent="$ROOT/.test-tmp"
mkdir -p "$tmp_parent"
work_dir="$(mktemp -d "$tmp_parent/install-smoke.XXXXXX")"
sentinel="$work_dir/external-command-invocations.txt"
cleanup() {
  local status=$?
  if [[ "$status" -ne 0 && -e "$sentinel" ]]; then
    echo "install smoke: a discovery command invoked a forbidden external tool:" >&2
    cat "$sentinel" >&2
  fi
  rm -rf "$work_dir"
  rmdir "$tmp_parent" 2>/dev/null || true
  exit "$status"
}
trap cleanup EXIT

mock_bin="$work_dir/bin"
mkdir -p "$mock_bin"

write_forbidden_command() {
  local name="$1"
  cat > "$mock_bin/$name" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
echo "$0 $*" >> "${GRA_INSTALL_SMOKE_SENTINEL:?}"
exit 97
SH
  chmod +x "$mock_bin/$name"
}

write_forbidden_command gh
write_forbidden_command codex

for path in bin/gra-*; do
  [[ -f "$path" ]] || fail "no gra-* commands found under bin/"
  [[ -x "$path" ]] || fail "$path is not executable; run chmod +x bin/*"
done

for path in scripts/*.sh; do
  [[ -f "$path" ]] || continue
  [[ -x "$path" ]] || fail "$path is not executable; run chmod +x scripts/*.sh"
done

export GRA_INSTALL_SMOKE_SENTINEL="$sentinel"
export PATH="$ROOT/bin:$mock_bin:$PATH"

resolved="$(command -v gra-audit || true)"
[[ "$resolved" == "$ROOT/bin/gra-audit" ]] || fail "gra-audit resolves to '$resolved', expected '$ROOT/bin/gra-audit'; check PATH"

version="$(sed -n '1p' VERSION)"
[[ -n "$version" ]] || fail "VERSION is empty"

for path in bin/gra-*; do
  command_name="${path##*/}"
  output="$("$command_name" --version)"
  expected="$command_name $version"
  [[ "$output" == "$expected" ]] || fail "$command_name --version output '$output', expected '$expected'"
done

gra-audit --help >/dev/null
gra-doctor --help >/dev/null
gra-validate-report --help >/dev/null
smoke_run="$work_dir/minimal-run"
cp -R "$ROOT/tests/fixtures/minimal-run" "$smoke_run"
gra-validate-report --run "$smoke_run" >/dev/null

if [[ -e "$sentinel" ]]; then
  echo "install smoke: a discovery command invoked a forbidden external tool:" >&2
  cat "$sentinel" >&2
  exit 1
fi

echo "install smoke ok"
