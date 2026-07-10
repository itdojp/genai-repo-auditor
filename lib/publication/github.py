from __future__ import annotations

import contextlib
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Iterable, Optional, Protocol, Tuple


class GitHubClient(Protocol):
    def repo_visibility(self, repo: str) -> str:
        """Return repository visibility as PUBLIC/PRIVATE/UNKNOWN."""
        raise NotImplementedError

    def issue_exists(self, repo: str, fingerprint: str) -> Optional[str]:
        """Return an existing open Issue URL for a fingerprint, if any."""
        raise NotImplementedError

    def ensure_label(self, repo: str, name: str, color: str = "ededed", desc: str = "GenAI Repo Auditor label") -> None:
        """Create or update a GitHub label."""
        raise NotImplementedError

    def create_issue(
        self,
        repo: str,
        *,
        title: str,
        body: str,
        labels: Iterable[str],
        assignee: Optional[str] = None,
        body_tmp_dir: Optional[Path] = None,
    ) -> str:
        """Create a GitHub Issue and return its URL."""
        raise NotImplementedError


class GhCliClient:
    def run(self, cmd: list[str], *, check: bool = True, capture: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            cmd,
            check=check,
            text=True,
            stdout=subprocess.PIPE if capture else None,
            stderr=subprocess.PIPE if capture else None,
        )

    def repo_visibility(self, repo: str) -> str:
        try:
            cp = self.run(["gh", "repo", "view", repo, "--json", "visibility", "--jq", ".visibility"], check=True)
            return cp.stdout.strip().upper() or "UNKNOWN"
        except Exception:
            return "UNKNOWN"

    def issue_exists(self, repo: str, fingerprint: str) -> Optional[str]:
        marker = f"genai-repo-auditor:fingerprint={fingerprint}"
        try:
            cp = self.run(
                [
                    "gh",
                    "issue",
                    "list",
                    "-R",
                    repo,
                    "--state",
                    "open",
                    "--search",
                    f"{marker} in:body",
                    "--json",
                    "number,title,url",
                    "--jq",
                    ".[0].url // ''",
                ],
                check=True,
            )
            return cp.stdout.strip() or None
        except subprocess.CalledProcessError:
            return None

    def ensure_label(self, repo: str, name: str, color: str = "ededed", desc: str = "GenAI Repo Auditor label") -> None:
        self.run(
            [
                "gh",
                "label",
                "create",
                name,
                "-R",
                repo,
                "--color",
                color,
                "--description",
                desc,
                "--force",
            ],
            check=False,
            capture=False,
        )

    def create_issue(
        self,
        repo: str,
        *,
        title: str,
        body: str,
        labels: Iterable[str],
        assignee: Optional[str] = None,
        body_tmp_dir: Optional[Path] = None,
    ) -> str:
        if body_tmp_dir is None:
            raise ValueError("body_tmp_dir is required for GitHub issue body files")
        tmp_dir = body_tmp_dir
        tmp_dir.mkdir(parents=True, exist_ok=True)
        tmp_path: Optional[str] = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".md", dir=tmp_dir, delete=False) as tmp:
                tmp.write(body)
                tmp_path = tmp.name
            cmd = ["gh", "issue", "create", "-R", repo, "--title", title, "--body-file", tmp_path]
            for label in labels:
                cmd.extend(["--label", str(label)])
            if assignee:
                cmd.extend(["--assignee", assignee])
            cp = self.run(cmd, check=True)
            return cp.stdout.strip()
        finally:
            if tmp_path:
                with contextlib.suppress(OSError):
                    os.unlink(tmp_path)
            with contextlib.suppress(OSError):
                tmp_dir.rmdir()


def create_default_labels(
    client: GitHubClient,
    repo: str,
    default_labels: Dict[str, Tuple[str, str]],
) -> None:
    for name, (color, desc) in default_labels.items():
        client.ensure_label(repo, name, color, desc)


def ensure_custom_labels(
    client: GitHubClient,
    repo: str,
    labels: Iterable[str],
    default_labels: Dict[str, Tuple[str, str]],
) -> None:
    for label in labels:
        if label not in default_labels:
            client.ensure_label(repo, str(label), "ededed", "GenAI Repo Auditor label")


def verify_ledger_against_github(repo: str, ledger: dict, client: GitHubClient) -> list[str]:
    drifts: list[str] = []
    for entry in ledger.get("findings") or []:
        if not isinstance(entry, dict) or not entry.get("url"):
            continue
        if str(entry.get("publication_status") or "") not in {"published", "duplicate"}:
            continue
        fingerprint = str(entry.get("fingerprint") or "")
        finding_id = str(entry.get("finding_id") or "SEC-UNKNOWN")
        if not fingerprint:
            drifts.append(f"{finding_id}: published ledger entry has no fingerprint")
            continue
        existing_url = client.issue_exists(repo, fingerprint)
        if not existing_url:
            drifts.append(f"{finding_id}: no open GitHub issue found for ledger fingerprint {fingerprint}")
        elif existing_url != entry.get("url"):
            drifts.append(f"{finding_id}: ledger url {entry.get('url')} differs from GitHub search result {existing_url}")
    return drifts
