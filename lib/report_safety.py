from __future__ import annotations

import re
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Iterator, Tuple

from run_events import reports_dir as configured_reports_dir

MAX_ISSUE_BODY_BYTES = 256 * 1024
SECRET_PATTERNS: Tuple[Tuple[str, re.Pattern[str]], ...] = (
    ("private key", re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")),
    ("GitHub token", re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}")),
    ("AWS access key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("Slack token", re.compile(r"xox[baprs]-[A-Za-z0-9-]{20,}")),
)
SECRET_EXAMPLE_MARKERS = ("REDACTED", "EXAMPLE", "PLACEHOLDER", "DUMMY", "FAKE", "<SECRET", "***", "...")


class ReportSafetyError(ValueError):
    """Raised when a report-controlled path or value violates safety policy."""


def _is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
        return True
    except ValueError:
        return False


def _path_chain(path: Path, stop: Path) -> Iterator[Path]:
    current = path
    while True:
        yield current
        if current == stop:
            break
        if current.parent == current:
            break
        current = current.parent


def _looks_like_intentional_secret_example(text: str) -> bool:
    upper = text.upper()
    return any(marker in upper for marker in SECRET_EXAMPLE_MARKERS)


def validate_relative_repo_path(value: object, *, field_path: str) -> str:
    raw = str(value or "")
    if not raw:
        raise ReportSafetyError(f"{field_path}: file path must not be empty")
    if "\x00" in raw:
        raise ReportSafetyError(f"{field_path}: file path contains NUL byte")
    if "\\" in raw:
        raise ReportSafetyError(f"{field_path}: file path must use '/' separators")
    posix = PurePosixPath(raw)
    if posix.is_absolute() or PureWindowsPath(raw).is_absolute():
        raise ReportSafetyError(f"{field_path}: file path must be relative")
    if raw.startswith("~"):
        raise ReportSafetyError(f"{field_path}: file path must not use home-directory expansion")
    if any(part in {"", ".", ".."} for part in raw.split("/")):
        raise ReportSafetyError(f"{field_path}: file path must not contain empty, '.', or '..' segments")
    return raw


def safe_issue_body_path(run_dir: Path, issue_body_file: object, *, field_path: str = "issue_body_file", max_bytes: int = MAX_ISSUE_BODY_BYTES) -> Path:
    try:
        reports_root = configured_reports_dir(run_dir)
    except OSError as exc:
        raise ReportSafetyError(f"{field_path}: unsafe reports_dir: {exc}") from exc
    issue_drafts_root = reports_root / "issue-drafts"
    issue_drafts_ref = issue_drafts_root.relative_to(run_dir)
    required_prefix = issue_drafts_ref.as_posix() + "/"
    raw = str(issue_body_file or "")
    if not raw:
        raise ReportSafetyError(f"{field_path}: issue_body_file must not be empty when an issue body file is used")
    if "\x00" in raw:
        raise ReportSafetyError(f"{field_path}: issue_body_file contains NUL byte")
    if "\\" in raw:
        raise ReportSafetyError(f"{field_path}: issue_body_file must use '/' separators")
    posix = PurePosixPath(raw)
    if posix.is_absolute() or PureWindowsPath(raw).is_absolute():
        raise ReportSafetyError(f"{field_path}: issue_body_file must be relative under {required_prefix}")
    if any(part in {"", ".", ".."} for part in raw.split("/")):
        raise ReportSafetyError(f"{field_path}: issue_body_file must not contain empty, '.', or '..' segments")
    if (
        len(posix.parts) <= len(issue_drafts_ref.parts)
        or posix.parts[:len(issue_drafts_ref.parts)] != issue_drafts_ref.parts
    ):
        raise ReportSafetyError(f"{field_path}: issue_body_file must be under {required_prefix}")
    if posix.suffix.lower() != ".md":
        raise ReportSafetyError(f"{field_path}: issue_body_file must be a .md file")

    base = issue_drafts_root.resolve(strict=False)
    candidate = run_dir / raw
    if not candidate.exists():
        raise ReportSafetyError(f"{field_path}: issue_body_file not found: {raw}")
    for part in _path_chain(candidate, run_dir):
        if part.exists() and part.is_symlink():
            raise ReportSafetyError(f"{field_path}: issue_body_file must not be a symlink: {raw}")
    resolved = candidate.resolve(strict=True)
    if not _is_relative_to(resolved, base):
        raise ReportSafetyError(f"{field_path}: issue_body_file escapes {required_prefix}: {raw}")
    if not resolved.is_file():
        raise ReportSafetyError(f"{field_path}: issue_body_file is not a regular file: {raw}")
    size = resolved.stat().st_size
    if size > max_bytes:
        raise ReportSafetyError(f"{field_path}: issue_body_file exceeds {max_bytes} bytes: {raw}")
    return resolved


def iter_secret_findings(value: object, *, field_path: str = "$") -> Iterator[str]:
    if isinstance(value, dict):
        for key, item in value.items():
            yield from iter_secret_findings(item, field_path=f"{field_path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from iter_secret_findings(item, field_path=f"{field_path}[{index}]")
    elif isinstance(value, str):
        if _looks_like_intentional_secret_example(value):
            return
        for label, pattern in SECRET_PATTERNS:
            if pattern.search(value):
                yield f"{field_path}: contains obvious unredacted full secret value matching {label} pattern"
