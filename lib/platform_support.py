from __future__ import annotations

import os
import platform
from pathlib import Path
from typing import Any, Mapping


def dirfd_report_writes_supported() -> bool:
    """Return whether the fail-closed efficacy report writer can run safely."""

    return (
        os.open in os.supports_dir_fd
        and os.mkdir in os.supports_dir_fd
        and os.rename in os.supports_dir_fd
        and os.stat in os.supports_dir_fd
        and os.stat in os.supports_follow_symlinks
        and os.unlink in os.supports_dir_fd
        and bool(getattr(os, "O_DIRECTORY", 0))
        and bool(getattr(os, "O_NOFOLLOW", 0))
    )


def classify_environment(
    *,
    system: str,
    os_name: str,
    env: Mapping[str, str],
    osrelease: str = "",
) -> str:
    normalized = system.strip().lower()
    if os_name == "nt" or normalized.startswith("win"):
        return "native-windows"
    if normalized == "linux":
        release = osrelease.lower()
        if "wsl2" in release or "microsoft-standard" in release:
            return "wsl2"
        if env.get("WSL_INTEROP") or env.get("WSL_DISTRO_NAME") or "microsoft" in release:
            return "wsl-unknown"
    if normalized == "linux":
        return "linux"
    if normalized == "darwin":
        return "macos"
    return "unsupported"


def detect_environment() -> str:
    osrelease = ""
    if platform.system().lower() == "linux":
        try:
            osrelease = Path("/proc/sys/kernel/osrelease").read_text(encoding="ascii", errors="ignore")
        except OSError:
            pass
    return classify_environment(
        system=platform.system(),
        os_name=os.name,
        env=os.environ,
        osrelease=osrelease,
    )


def platform_support_report() -> dict[str, Any]:
    environment = detect_environment()
    dirfd = dirfd_report_writes_supported()
    diagnostics: list[str] = []
    if environment == "native-windows":
        diagnostics.append(
            "Native Windows supports packaged inspection, prepare, and workflow orchestration; use WSL2 when a feature requires POSIX dirfd safeguards."
        )
        diagnostics.append(
            "Native Windows scanner execution is experimental and requires local Docker Desktop using Linux containers; Podman and gVisor execution are not supported there."
        )
    elif environment == "wsl2":
        diagnostics.append(
            "WSL2 follows the Linux support boundary; keep repositories and run artifacts in the WSL filesystem for predictable permissions and path behavior."
        )
    elif environment == "wsl-unknown":
        diagnostics.append(
            "A WSL environment was detected but WSL2 could not be confirmed; upgrade to or verify WSL2 before relying on the Linux support boundary."
        )
    elif environment == "unsupported":
        diagnostics.append("This operating system is not in the tested support matrix.")
    if not dirfd:
        diagnostics.append(
            "Safe efficacy report generation is unavailable because required dirfd operations are missing; listing remains available and WSL2/Linux/macOS is recommended."
        )

    scanner_execution = {
        "native-windows": "experimental-docker-desktop-linux-containers",
        "wsl2": "supported-local-docker-or-podman",
        "linux": "supported-local-docker-or-podman",
        "macos": "experimental-local-docker",
    }.get(environment, "unsupported")
    return {
        "status": "warning" if diagnostics and environment in {"native-windows", "wsl-unknown", "unsupported"} else "ok",
        "environment": environment,
        "wsl_detected": environment in {"wsl2", "wsl-unknown"},
        "wsl2_confirmed": environment == "wsl2",
        "dirfd_report_writes_supported": dirfd,
        "features": {
            "package_install_and_resource_discovery": "supported" if environment not in {"wsl-unknown", "unsupported"} else "unsupported",
            "audit_prepare": "supported" if environment not in {"wsl-unknown", "unsupported"} else "unsupported",
            "workflow_plan_execute_resume": "supported" if environment not in {"wsl-unknown", "unsupported"} else "unsupported",
            "efficacy_listing": "supported" if environment not in {"wsl-unknown", "unsupported"} else "unsupported",
            "efficacy_report_generation": (
                "experimental-untested-wsl"
                if environment == "wsl-unknown"
                else "supported" if dirfd else "unsupported-fail-closed"
            ),
            "scanner_planning": "supported" if environment not in {"wsl-unknown", "unsupported"} else "unsupported",
            "scanner_execution": scanner_execution,
        },
        "diagnostics": diagnostics,
    }
