from __future__ import annotations

import contextlib
import re
import sys
import tempfile
from pathlib import Path
from unittest import TestCase, main, mock

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "lib"))

from scanner_adapters import ADAPTERS  # noqa: E402
from scanner_runner import (  # noqa: E402
    CONTAINER_IMAGES,
    CONTAINER_TOOL_VERSIONS,
    ScannerExecutionError,
    _container_command,
    _directory_size,
    _publish_output,
    _runtime_prefix,
    _safe_runtime_environment,
)


class ScannerRunnerTests(TestCase):
    def test_every_adapter_uses_an_immutable_container_digest(self) -> None:
        self.assertEqual(set(ADAPTERS), set(CONTAINER_IMAGES))
        self.assertEqual(set(ADAPTERS), set(CONTAINER_TOOL_VERSIONS))
        for image in CONTAINER_IMAGES.values():
            self.assertRegex(image, re.compile(r"^[a-z0-9.-]+/[a-z0-9./-]+@sha256:[a-f0-9]{64}$"))
            self.assertNotIn(":latest", image)
        for version in CONTAINER_TOOL_VERSIONS.values():
            self.assertRegex(version, re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$"))

    def test_runtime_environment_removes_remote_and_credential_configuration(self) -> None:
        safe = _safe_runtime_environment(
            {
                "PATH": "/safe/bin",
                "HOME": "/safe/home",
                "LANG": "C.UTF-8",
                "GH_TOKEN": "sensitive",
                "DOCKER_HOST": "tcp://external.example:2376",
                "CONTAINER_HOST": "ssh://external.example/run/podman.sock",
                "HTTPS_PROXY": "https://proxy.example",
                "OPENAI_API_KEY": "sensitive",
            }
        )
        self.assertEqual({"PATH": "/safe/bin", "HOME": "/safe/home", "LANG": "C.UTF-8"}, safe)

    def test_missing_local_runtime_fails_closed(self) -> None:
        with mock.patch("scanner_runner.shutil.which", return_value=None):
            with self.assertRaisesRegex(ScannerExecutionError, "Podman or Docker"):
                _runtime_prefix("/missing", {})

    def test_runtime_specific_user_mapping_is_safe_for_rootless_podman(self) -> None:
        common = {
            "profile": "container",
            "name": "gra-scan-test",
            "image": next(iter(CONTAINER_IMAGES.values())),
            "target": Path("/run/repo"),
            "staging": Path("/run/output"),
            "adapter_args": ["/target", "/output/result.json"],
        }
        podman = _container_command(prefix=["podman"], runtime="podman", selinux_enforcing=True, **common)
        docker = _container_command(prefix=["docker"], runtime="docker", **common)
        self.assertIn("--userns=keep-id", podman)
        self.assertIn("label=disable", podman)
        self.assertNotIn("--userns=keep-id", docker)
        self.assertNotIn("--user", docker)

    def test_output_publication_is_exclusive_and_does_not_replace_races(self) -> None:
        tmp_parent = REPO_ROOT / ".test-tmp"
        tmp_parent.mkdir(exist_ok=True)
        try:
            with tempfile.TemporaryDirectory(dir=tmp_parent) as tmp:
                root = Path(tmp)
                source = root / "source.json"
                destination = root / "result.json"
                source.write_text("[]\n", encoding="utf-8")
                _publish_output(source, destination)
                self.assertEqual("[]\n", destination.read_text(encoding="utf-8"))
                destination.write_text("existing\n", encoding="utf-8")
                with self.assertRaisesRegex(ScannerExecutionError, "publish"):
                    _publish_output(source, destination)
                self.assertEqual("existing\n", destination.read_text(encoding="utf-8"))
        finally:
            with contextlib.suppress(OSError):
                tmp_parent.rmdir()

    def test_directory_size_rejects_symlinks_without_traversal(self) -> None:
        tmp_parent = REPO_ROOT / ".test-tmp"
        tmp_parent.mkdir(exist_ok=True)
        try:
            with tempfile.TemporaryDirectory(dir=tmp_parent) as tmp:
                root = Path(tmp)
                outside = root / "outside"
                staging = root / "staging"
                outside.mkdir()
                staging.mkdir()
                (outside / "large").write_bytes(b"x" * 100)
                try:
                    (staging / "link").symlink_to(outside, target_is_directory=True)
                except OSError as exc:
                    self.skipTest(f"symlink not available: {exc}")
                self.assertGreater(_directory_size(staging, 10), 10)
        finally:
            with contextlib.suppress(OSError):
                tmp_parent.rmdir()


if __name__ == "__main__":
    main()
