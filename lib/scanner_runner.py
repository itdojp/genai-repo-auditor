from __future__ import annotations

import json
import contextlib
import os
import platform
import shutil
import signal
import stat
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from scanner_adapters import (
    SCHEMA_VERSION,
    ScannerAdapter,
    ScannerAdapterError,
    adapter_by_id,
    build_scan_plan,
    validate_run_directory,
)


CONTAINER_IMAGES = {
    "gitleaks": "ghcr.io/gitleaks/gitleaks@sha256:c00b6bd0aeb3071cbcb79009cb16a60dd9e0a7c60e2be9ab65d25e6bc8abbb7f",
    "syft": "ghcr.io/anchore/syft@sha256:473a60e3a58e29aca3aedb3e99e787bb4ef273917e44d10fcbea4330a07320bb",
}
EXECUTION_PROFILES = ("container", "gvisor")
_LOG_LIMIT_BYTES = 1_000_000
_POLL_SECONDS = 0.05


class ScannerExecutionError(ScannerAdapterError):
    """Raised when scanner execution cannot start safely."""


class _ScannerTermination(Exception):
    pass


def _raise_scanner_termination(_signum: int, _frame: Any) -> None:
    raise _ScannerTermination


def _safe_runtime_environment(source: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(os.environ if source is None else source)
    allowed_names = {
        "HOME",
        "LANG",
        "LOGNAME",
        "PATH",
        "SYSTEMROOT",
        "TEMP",
        "TMP",
        "TMPDIR",
        "USER",
        "WINDIR",
        "XDG_RUNTIME_DIR",
    }
    return {key: value for key, value in env.items() if key.upper() in allowed_names or key.upper().startswith("LC_")}


def _docker_endpoint(env: dict[str, str]) -> str:
    if os.name == "nt":
        return "npipe:////./pipe/docker_engine"
    candidates: list[Path] = []
    xdg = env.get("XDG_RUNTIME_DIR")
    if xdg:
        candidates.append(Path(xdg) / "docker.sock")
    home = Path.home()
    candidates.extend((home / ".docker" / "run" / "docker.sock", Path("/var/run/docker.sock")))
    for candidate in candidates:
        try:
            if stat.S_ISSOCK(candidate.stat().st_mode):
                return f"unix://{candidate}"
        except OSError:
            continue
    return "unix:///var/run/docker.sock"


def _runtime_candidates(path_env: str | None, env: dict[str, str]) -> list[tuple[list[str], str]]:
    candidates: list[tuple[list[str], str]] = []
    docker = shutil.which("docker", path=path_env)
    if docker:
        candidates.append(([docker, "--host", _docker_endpoint(env)], "docker"))
    podman = shutil.which("podman", path=path_env)
    if podman and platform.system().lower() == "linux":
        candidates.append(([podman, "--remote=false"], "podman"))
    return candidates


def _runtime_prefix(path_env: str | None, env: dict[str, str]) -> tuple[list[str], str]:
    candidates = _runtime_candidates(path_env, env)
    if not candidates:
        raise ScannerExecutionError("container execution requires local Podman or Docker on PATH")
    return candidates[0]


def _ensure_directory(path: Path, *, root: Path) -> None:
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise ScannerExecutionError("scanner output directory must stay under the run directory") from exc
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ScannerExecutionError("scanner output directory must not contain symlink components")
        if current.exists():
            if not current.is_dir():
                raise ScannerExecutionError("scanner output directory components must be directories")
            continue
        current.mkdir(mode=0o700)


def _directory_size(path: Path, limit: int) -> int:
    total = 0
    pending = [path]
    while pending:
        current = pending.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    if entry.is_symlink():
                        return limit + 1
                    if entry.is_file(follow_symlinks=False):
                        total += entry.stat(follow_symlinks=False).st_size
                    elif entry.is_dir(follow_symlinks=False):
                        pending.append(Path(entry.path))
                    else:
                        return limit + 1
                    if total > limit:
                        return total
        except OSError:
            return limit + 1
    return total


def _bounded_file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _cleanup_container(prefix: list[str], name: str, env: dict[str, str]) -> None:
    with contextlib.suppress(OSError, subprocess.SubprocessError):
        subprocess.run(
            [*prefix, "rm", "-f", name],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
            check=False,
            env=env,
        )


def _remove_staging(staging: Path, staging_root: Path) -> None:
    shutil.rmtree(staging, ignore_errors=True)
    with contextlib.suppress(OSError):
        staging_root.rmdir()


def _exit_status(adapter: ScannerAdapter, returncode: int) -> str:
    meanings = dict(adapter.exit_semantics)
    return meanings.get(str(returncode), meanings.get("other", "scanner-failure"))


def _result_count(adapter: ScannerAdapter, output: Path) -> int:
    try:
        payload = json.loads(output.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ScannerExecutionError("scanner output must be valid UTF-8 JSON") from exc
    if adapter.id == "gitleaks":
        if not isinstance(payload, list):
            raise ScannerExecutionError("gitleaks output must be a JSON array")
        return len(payload)
    if adapter.id == "syft":
        if not isinstance(payload, dict) or not isinstance(payload.get("components", []), list):
            raise ScannerExecutionError("syft CycloneDX output must contain a components array")
        return len(payload.get("components", []))
    raise ScannerExecutionError(f"result counting is not implemented for adapter {adapter.id}")


def _container_mount(source: Path, destination: str, *, readonly: bool = False) -> str:
    source_text = str(source)
    if "," in source_text or "\x00" in source_text:
        raise ScannerExecutionError("container mount source contains unsupported characters")
    suffix = ",readonly" if readonly else ""
    return f"type=bind,src={source_text},dst={destination}{suffix}"


def _selinux_enforcing() -> bool:
    if platform.system().lower() != "linux":
        return False
    try:
        return Path("/sys/fs/selinux/enforce").read_text(encoding="ascii").strip() == "1"
    except OSError:
        return False


def _container_command(
    *,
    prefix: list[str],
    runtime: str,
    profile: str,
    name: str,
    image: str,
    target: Path,
    staging: Path,
    adapter_args: list[str],
    selinux_enforcing: bool = False,
) -> list[str]:
    command = [
        *prefix,
        "run",
        "--name",
        name,
        "--rm",
        "--pull=never",
        "--network=none",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges=true",
        "--pids-limit=256",
        "--memory=1g",
        "--cpus=1",
    ]
    if runtime == "podman" and hasattr(os, "getuid"):
        command.append("--userns=keep-id")
    if selinux_enforcing:
        # Do not relabel the audited target. Keep the target unchanged and rely
        # on the remaining read-only/capability/seccomp/network boundaries.
        command.extend(("--security-opt", "label=disable"))
    if profile == "gvisor":
        command.extend(("--runtime", "runsc"))
    command.extend(
        (
            "--mount",
            _container_mount(target, "/target", readonly=True),
            "--mount",
            _container_mount(staging, "/output"),
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,nodev,size=67108864",
            image,
            *adapter_args,
        )
    )
    return command


def _publish_output(source: Path, destination: Path) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
    fd: int | None = None
    try:
        fd = os.open(temporary, flags, 0o600)
        with source.open("rb") as input_handle, os.fdopen(fd, "wb", closefd=False) as output_handle:
            while chunk := input_handle.read(64 * 1024):
                output_handle.write(chunk)
            output_handle.flush()
            os.fsync(output_handle.fileno())
        os.link(temporary, destination, follow_symlinks=False)
    except OSError as exc:
        raise ScannerExecutionError("unable to publish scanner output safely") from exc
    finally:
        if fd is not None:
            os.close(fd)
        with contextlib.suppress(OSError):
            temporary.unlink()


def execute_scan(
    run_dir: Path,
    *,
    adapter_id: str,
    sandbox_profile: str,
    network_policy: str = "disabled",
    path_env: str | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    run_dir = validate_run_directory(run_dir).absolute()
    if sandbox_profile not in EXECUTION_PROFILES:
        raise ScannerExecutionError("execution requires the container or gvisor sandbox profile")
    if network_policy != "disabled":
        raise ScannerExecutionError("scanner execution is offline-only and requires network policy disabled")
    adapter = adapter_by_id(adapter_id)
    if adapter.network_required:
        raise ScannerExecutionError(f"network-requiring adapter {adapter.id} is not executable in this release")
    image = CONTAINER_IMAGES.get(adapter.id)
    if not image or "@sha256:" not in image:
        raise ScannerExecutionError(f"adapter {adapter.id} does not declare an immutable container image")

    plan = build_scan_plan(
        run_dir,
        adapter_id=adapter.id,
        sandbox_profile=sandbox_profile,
        network_policy=network_policy,
        path_env=path_env,
    )
    target = run_dir / plan["read_paths"][0]
    if not target.is_dir() or target.is_symlink():
        raise ScannerExecutionError("target repository must be an existing non-symlink directory")
    output = run_dir / plan["raw_output_path"]
    reports_root = output.parents[2]
    target_resolved = target.resolve(strict=True)
    reports_resolved = reports_root.resolve(strict=False)
    if target_resolved == reports_resolved or target_resolved in reports_resolved.parents or reports_resolved in target_resolved.parents:
        raise ScannerExecutionError("target repository and reports directory must not overlap for execution")
    if output.exists() or output.is_symlink():
        raise ScannerExecutionError("raw scanner output already exists; use a fresh run or remove it explicitly")
    scanner_results = output.parent.parent
    _ensure_directory(scanner_results, root=run_dir)
    _ensure_directory(output.parent, root=run_dir)

    source_env = dict(os.environ if env is None else env)
    safe_env = _safe_runtime_environment(source_env)
    candidates = _runtime_candidates(path_env, source_env)
    if not candidates:
        raise ScannerExecutionError("container execution requires local Podman or Docker on PATH")
    prefix: list[str] | None = None
    runtime: str | None = None
    for candidate_prefix, candidate_runtime in candidates:
        try:
            inspected = subprocess.run(
                [*candidate_prefix, "image", "inspect", image],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=20,
                check=False,
                env=safe_env,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if inspected.returncode == 0:
            prefix, runtime = candidate_prefix, candidate_runtime
            break
    if prefix is None or runtime is None:
        raise ScannerExecutionError("pinned scanner image is not available locally; pre-pull it explicitly")

    staging_root = scanner_results / ".gra-scan-staging"
    _ensure_directory(staging_root, root=run_dir)
    staging = Path(tempfile.mkdtemp(prefix=f"{adapter.id}-", dir=staging_root))
    name = f"gra-scan-{adapter.id}-{uuid.uuid4().hex[:12]}"
    container_output = f"/output/{adapter.id}.json"
    adapter_args = [
        token.replace("{target}", "/target").replace("{output}", container_output)
        for token in adapter.argument_template
    ]
    command = _container_command(
        prefix=prefix,
        runtime=runtime,
        profile=sandbox_profile,
        name=name,
        image=image,
        target=target,
        staging=staging,
        adapter_args=adapter_args,
        selinux_enforcing=_selinux_enforcing(),
    )
    log_out = staging / ".stdout"
    log_err = staging / ".stderr"
    started = time.monotonic()
    failure: str | None = None
    previous_handlers: dict[int, Any] = {}
    if threading.current_thread() is threading.main_thread():
        for signal_number in (signal.SIGTERM, getattr(signal, "SIGHUP", signal.SIGTERM)):
            if signal_number in previous_handlers:
                continue
            previous_handlers[signal_number] = signal.getsignal(signal_number)
            signal.signal(signal_number, _raise_scanner_termination)
    try:
        with log_out.open("wb") as stdout_handle, log_err.open("wb") as stderr_handle:
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=stdout_handle,
                stderr=stderr_handle,
                env=safe_env,
            )
            while process.poll() is None:
                elapsed = time.monotonic() - started
                if elapsed > adapter.timeout_seconds:
                    failure = "timeout"
                elif _directory_size(staging, adapter.max_output_bytes + _LOG_LIMIT_BYTES) > (
                    adapter.max_output_bytes + _LOG_LIMIT_BYTES
                ):
                    failure = "output-limit-exceeded"
                elif max(_bounded_file_size(log_out), _bounded_file_size(log_err)) > _LOG_LIMIT_BYTES:
                    failure = "log-limit-exceeded"
                if failure:
                    process.kill()
                    process.wait(timeout=10)
                    _cleanup_container(prefix, name, safe_env)
                    break
                time.sleep(_POLL_SECONDS)
            returncode = process.returncode if process.returncode is not None else -1
            if failure is None:
                if max(_bounded_file_size(log_out), _bounded_file_size(log_err)) > _LOG_LIMIT_BYTES:
                    failure = "log-limit-exceeded"
                elif _directory_size(staging, adapter.max_output_bytes + _LOG_LIMIT_BYTES) > (
                    adapter.max_output_bytes + _LOG_LIMIT_BYTES
                ):
                    failure = "output-limit-exceeded"
    except (OSError, subprocess.SubprocessError) as exc:
        _cleanup_container(prefix, name, safe_env)
        _remove_staging(staging, staging_root)
        raise ScannerExecutionError("unable to execute the scanner container") from exc
    except (KeyboardInterrupt, _ScannerTermination) as exc:
        _cleanup_container(prefix, name, safe_env)
        _remove_staging(staging, staging_root)
        raise ScannerExecutionError("scanner execution was interrupted and the container was removed") from exc
    finally:
        for signal_number, previous_handler in previous_handlers.items():
            signal.signal(signal_number, previous_handler)

    duration_ms = max(0, int((time.monotonic() - started) * 1000))
    staged_output = staging / f"{adapter.id}.json"
    status = _exit_status(adapter, returncode)
    try:
        if failure:
            status = failure
        elif status == "scanner-failure":
            pass
        elif staged_output.is_symlink() or not staged_output.is_file():
            status = "missing-output"
        elif staged_output.stat().st_size > adapter.max_output_bytes:
            status = "output-limit-exceeded"
        else:
            unexpected = [
                item.name
                for item in staging.iterdir()
                if item.name not in {staged_output.name, log_out.name, log_err.name}
            ]
            if unexpected:
                status = "unexpected-output"
            else:
                try:
                    count = _result_count(adapter, staged_output)
                except ScannerExecutionError:
                    status = "invalid-output"
                else:
                    if count > adapter.max_results:
                        status = "result-limit-exceeded"
                    else:
                        try:
                            _publish_output(staged_output, output)
                        except ScannerExecutionError:
                            status = "output-publication-failed"
                        else:
                            return {
                                "schema_version": SCHEMA_VERSION,
                                "mode": "execute",
                                "scanner_executed": True,
                                "network_accessed": False,
                                "run_id": plan["run_id"],
                                "adapter_id": adapter.id,
                                "sandbox_profile": sandbox_profile,
                                "network_policy": network_policy,
                                "runtime": runtime,
                                "image": image,
                                "status": status,
                                "exit_code": returncode,
                                "duration_ms": duration_ms,
                                "result_count": count,
                                "raw_output_path": plan["raw_output_path"],
                                "result_classification": adapter.result_classification,
                                "finding_status": "review-only",
                            }
    finally:
        _remove_staging(staging, staging_root)

    return {
        "schema_version": SCHEMA_VERSION,
        "mode": "execute",
        "scanner_executed": True,
        "network_accessed": False,
        "run_id": plan["run_id"],
        "adapter_id": adapter.id,
        "sandbox_profile": sandbox_profile,
        "network_policy": network_policy,
        "runtime": runtime,
        "image": image,
        "status": status,
        "exit_code": returncode,
        "duration_ms": duration_ms,
        "result_count": 0,
        "raw_output_path": None,
        "result_classification": adapter.result_classification,
        "finding_status": "review-only",
    }
