from __future__ import annotations

import runpy
import sys
from collections.abc import Sequence
from pathlib import Path

from .resources import resource_root

COMMANDS: tuple[str, ...] = (
    "gra-adversarial-validate",
    "gra-agent-check",
    "gra-audit",
    "gra-batch",
    "gra-benchmark",
    "gra-chains",
    "gra-dashboard",
    "gra-doctor",
    "gra-efficacy-benchmark",
    "gra-evidence-graph",
    "gra-gapfill",
    "gra-import-findings",
    "gra-index",
    "gra-ingest",
    "gra-issues",
    "gra-metrics",
    "gra-no-findings",
    "gra-novelty",
    "gra-proofs",
    "gra-recon",
    "gra-remediate",
    "gra-research",
    "gra-run",
    "gra-run-state",
    "gra-sandbox-check",
    "gra-sarif",
    "gra-scan",
    "gra-scanner-triage",
    "gra-store",
    "gra-targets",
    "gra-taxonomy-preflight",
    "gra-trace",
    "gra-validate-report",
    "gra-variant",
    "gra-workflow-profile",
    "gra-worktree-check",
)


def _entrypoint_name(command: str) -> str:
    return command.replace("-", "_")


def _normalize_exit_code(value: object) -> int:
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        print(value, file=sys.stderr)
        return 1
    return 1


def _resource_script(command: str) -> Path:
    if command not in COMMANDS:
        raise ValueError(f"unknown GenAI Repo Auditor command: {command}")
    script = resource_root(honor_env_override=False) / "bin" / command
    if not script.is_file():
        raise FileNotFoundError(script)
    return script


def run_packaged_python_command(command: str, argv: Sequence[str] | None = None) -> int:
    """Run a bundled legacy Python ``bin/gra-*`` command.

    The installed console scripts enter through this adapter instead of relying
    on executable bits or POSIX shebang dispatch.  ``sys.argv[0]`` is preserved
    as the public command name so argparse help/version output remains stable.
    """

    args = list(sys.argv[1:] if argv is None else argv)
    script = _resource_script(command)
    lib_dir = resource_root(honor_env_override=False) / "lib"
    old_argv = sys.argv[:]
    old_path = sys.path[:]
    sys.argv = [command, *args]
    if str(lib_dir) not in sys.path:
        sys.path.insert(0, str(lib_dir))
    try:
        try:
            runpy.run_path(str(script), run_name="__main__")
        except SystemExit as exc:
            return _normalize_exit_code(exc.code)
        return 0
    finally:
        sys.argv = old_argv
        sys.path = old_path


def dispatch(command: str, argv: Sequence[str] | None = None) -> int:
    try:
        if command == "gra-audit":
            from .audit_cli import main

            return main(argv, prog=command)
        if command == "gra-batch":
            from .batch_cli import main

            return main(argv, prog=command)
        return run_packaged_python_command(command, argv)
    except SystemExit as exc:
        return _normalize_exit_code(exc.code)


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] not in COMMANDS:
        available = ", ".join(COMMANDS)
        print(f"Usage: python -m genai_repo_auditor.cli COMMAND [args...]\nAvailable commands: {available}", file=sys.stderr)
        return 2
    command, *command_args = args
    return dispatch(command, command_args)


def _make_entrypoint(command: str):
    def entrypoint() -> int:
        return dispatch(command)

    entrypoint.__name__ = _entrypoint_name(command)
    entrypoint.__qualname__ = entrypoint.__name__
    entrypoint.__doc__ = f"Console entry point for {command}."
    return entrypoint


for _command in COMMANDS:
    globals()[_entrypoint_name(_command)] = _make_entrypoint(_command)


if __name__ == "__main__":
    raise SystemExit(main())
