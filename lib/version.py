from __future__ import annotations

from pathlib import Path


def auditor_version(lab_root: Path | None = None) -> str:
    """Return the installed GenAI Repo Auditor version from the root VERSION file."""
    root = Path(lab_root) if lab_root is not None else Path(__file__).resolve().parents[1]
    version_file = root / "VERSION"
    try:
        text = version_file.read_text(encoding="utf-8")
    except OSError:
        return "unknown"
    lines = text.splitlines()
    version = lines[0].strip() if lines else ""
    return version or "unknown"
