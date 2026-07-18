from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any

from run_events import reports_dir as configured_reports_dir


MAX_TARGETS_JSON_BYTES = 16 * 1024 * 1024


def load_targets_artifact(run_dir: Path, default: Any = None) -> Any:
    """Read targets.json through a bounded, no-follow file descriptor."""

    return load_targets_artifact_path(configured_reports_dir(run_dir) / "targets.json", default)


def load_targets_artifact_path(path: Path, default: Any = None) -> Any:
    """Read an explicitly selected targets artifact without following its leaf."""

    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except FileNotFoundError:
        return default
    except OSError as exc:
        raise OSError("targets.json must be a regular non-symlink file") from exc
    try:
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode):
            raise OSError("targets.json must be a regular non-symlink file")
        if metadata.st_size > MAX_TARGETS_JSON_BYTES:
            raise OSError(f"targets.json exceeds the {MAX_TARGETS_JSON_BYTES}-byte limit")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(fd, min(1024 * 1024, MAX_TARGETS_JSON_BYTES + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > MAX_TARGETS_JSON_BYTES:
                raise OSError(f"targets.json exceeds the {MAX_TARGETS_JSON_BYTES}-byte limit")
        return json.loads(b"".join(chunks).decode("utf-8"))
    finally:
        os.close(fd)
