from __future__ import annotations

import datetime as _dt
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from template_env import validate_template_env_key


def utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding='utf-8'))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def load_context(run_dir: Path) -> Dict[str, Any]:
    ctx = load_json(run_dir / 'context.json', {}) or {}
    ctx.setdefault('run_id', run_dir.name)
    ctx.setdefault('target_repo_dir', 'repo')
    ctx.setdefault('reports_dir', 'reports')
    ctx.setdefault('repo_dir', str(run_dir / 'repo'))
    return ctx


def env_from_context(run_dir: Path, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    ctx = load_context(run_dir)
    mapping = {
        'RUN_ID': ctx.get('run_id', run_dir.name),
        'REPO': ctx.get('repo', ''),
        'REPO_SLUG': ctx.get('repo_slug', ''),
        'BRANCH': ctx.get('branch', ''),
        'COMMIT': ctx.get('commit', ''),
        'VISIBILITY': ctx.get('visibility', 'UNKNOWN'),
        'RUN_DIR': str(run_dir),
        'REPO_DIR': str(run_dir / 'repo'),
        'TARGET_REPO_DIR': ctx.get('target_repo_dir', 'repo'),
        'REPORTS_DIR': ctx.get('reports_dir', 'reports'),
        'REPORT_DIR': str(run_dir / ctx.get('reports_dir', 'reports')),
    }
    env: Dict[str, str] = {}
    for k, v in mapping.items():
        validate_template_env_key(k)
        env[k] = '' if v is None else str(v)
    if extra:
        for k, v in extra.items():
            validate_template_env_key(k)
            env[k] = '' if v is None else str(v)
    return env


def render_template(lab_root: Path, template: Path, out: Path, env: Dict[str, str]) -> None:
    cmd = [sys.executable, str(lab_root / 'lib' / 'render_template.py'), str(template), str(out)]
    subprocess.run(cmd, check=True, env=env)


def ensure_taxonomy_templates(lab_root: Path, run_dir: Path) -> None:
    """Copy controlled taxonomy profiles and alias config into a run directory."""

    source_dir = lab_root / "templates" / "taxonomies"
    target_dir = run_dir / "templates" / "taxonomies"
    if source_dir.exists():
        target_dir.mkdir(parents=True, exist_ok=True)
        for source in sorted(source_dir.glob("*.json")):
            shutil.copyfile(source, target_dir / source.name)
    alias_src = lab_root / "templates" / "taxonomy-aliases.json"
    if alias_src.exists():
        alias_dst = run_dir / "templates" / "taxonomy-aliases.json"
        alias_dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(alias_src, alias_dst)


def _toml_string(value: str) -> str:
    return json.dumps(str(value))


def codex_config_arg(key: str, value: object) -> str:
    if isinstance(value, bool):
        rendered = 'true' if value else 'false'
    else:
        rendered = _toml_string(str(value))
    return f'{key}={rendered}'


def build_codex_exec_args(
    *,
    run_dir: Path,
    model: str,
    effort: str,
    network: bool = False,
    output_last: Path,
    approval: str = 'never',
) -> List[str]:
    return [
        'codex', 'exec',
        '--cd', str(run_dir),
        '--skip-git-repo-check',
        '--model', model,
        '--sandbox', 'workspace-write',
        '--color', 'never',
        '--output-last-message', str(output_last),
        '-c', codex_config_arg('approval_policy', approval),
        '-c', codex_config_arg('model_reasoning_effort', effort),
        '-c', codex_config_arg('web_search', 'disabled'),
        '-c', codex_config_arg('sandbox_workspace_write.network_access', network),
        '--json',
        '-',
    ]


def run_codex_exec(
    *,
    run_dir: Path,
    prompt_file: Path,
    model: str,
    effort: str,
    network: bool = False,
    output_last: Path,
    events_file: Path,
    stderr_file: Path,
    approval: str = 'never',
) -> int:
    args = build_codex_exec_args(
        run_dir=run_dir,
        model=model,
        effort=effort,
        network=network,
        output_last=output_last,
        approval=approval,
    )
    output_last.parent.mkdir(parents=True, exist_ok=True)
    events_file.parent.mkdir(parents=True, exist_ok=True)
    stderr_file.parent.mkdir(parents=True, exist_ok=True)
    with prompt_file.open('r', encoding='utf-8') as stdin, events_file.open('w', encoding='utf-8') as stdout, stderr_file.open('w', encoding='utf-8') as stderr:
        proc = subprocess.run(args, stdin=stdin, stdout=stdout, stderr=stderr, text=True)
    return proc.returncode


def normalize_repo_slug(repo: str) -> str:
    repo = repo.replace('https://github.com/', '').replace('http://github.com/', '').removesuffix('.git')
    return repo.replace('/', '__').replace(':', '__')


def load_targets(run_dir: Path) -> List[Dict[str, Any]]:
    ctx = load_context(run_dir)
    data = load_json(run_dir / ctx.get('reports_dir', 'reports') / 'targets.json', {}) or {}
    targets = data.get('targets') or []
    return [t for t in targets if isinstance(t, dict)]


def write_targets(run_dir: Path, targets: List[Dict[str, Any]]) -> None:
    ctx = load_context(run_dir)
    reports_dir = run_dir / ctx.get('reports_dir', 'reports')
    data = load_json(reports_dir / 'targets.json', {}) or {}
    data.update({
        'run_id': ctx.get('run_id', run_dir.name),
        'repo': ctx.get('repo', ''),
        'branch': ctx.get('branch', ''),
        'commit': ctx.get('commit', ''),
        'generated_at': data.get('generated_at') or utc_now(),
        'targets': targets,
    })
    write_json(reports_dir / 'targets.json', data)


def find_target(run_dir: Path, target_id: str) -> Dict[str, Any]:
    for t in load_targets(run_dir):
        if str(t.get('id')) == target_id:
            return t
    raise KeyError(f'target not found: {target_id}')


def load_findings(run_dir: Path) -> List[Dict[str, Any]]:
    data = load_json(run_dir / 'reports' / 'findings.json', {}) or {}
    findings = data.get('findings') or []
    return [f for f in findings if isinstance(f, dict)]


def find_finding(run_dir: Path, finding_id: str) -> Dict[str, Any]:
    for f in load_findings(run_dir):
        if str(f.get('id')) == finding_id:
            return f
    raise KeyError(f'finding not found: {finding_id}')


def slug(text: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-') or 'item'
