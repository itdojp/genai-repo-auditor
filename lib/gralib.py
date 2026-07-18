from __future__ import annotations

import datetime as _dt
import contextlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from agent_worker import codex_worker_executable
from run_events import reports_dir as configured_reports_dir
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


def safe_run_artifact_destination(run_dir: Path, path: Path) -> Path:
    """Prepare one run-local destination without following symlink components."""

    run_root = run_dir.resolve(strict=True)
    candidate = path if path.is_absolute() else run_root / path
    try:
        rel = candidate.relative_to(run_root)
    except ValueError as exc:
        raise OSError(f'run artifact must stay under the run directory: {candidate}') from exc
    if not rel.parts:
        raise OSError('run artifact destination must name a file')
    if '..' in rel.parts:
        raise OSError(f'run artifact path must not contain parent traversal: {rel.as_posix()}')

    current = run_root
    for part in rel.parts[:-1]:
        current = current / part
        if current.is_symlink():
            raise OSError(f'run artifact path must not contain symlink components: {rel.as_posix()}')
        if current.exists():
            if not current.is_dir():
                raise OSError(f'run artifact parent must be a directory: {current}')
        else:
            current.mkdir(mode=0o700)
    if candidate.is_symlink() or (candidate.exists() and not candidate.is_file()):
        raise OSError(f'run artifact destination must be a regular non-symlink file: {rel.as_posix()}')
    return candidate


def write_run_artifact_text(run_dir: Path, path: Path, content: str) -> None:
    destination = safe_run_artifact_destination(run_dir, path)
    temporary = destination.with_name(f'.{destination.name}.{uuid.uuid4().hex}.tmp')
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0)
    fd: int | None = None
    try:
        fd = os.open(temporary, flags, 0o600)
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise OSError('run artifact temporary path must be a regular file')
        payload = content.encode('utf-8')
        offset = 0
        while offset < len(payload):
            written = os.write(fd, payload[offset:])
            if written <= 0:
                raise OSError('run artifact write made no progress')
            offset += written
        os.fsync(fd)
        os.close(fd)
        fd = None
        safe_run_artifact_destination(run_dir, destination)
        os.replace(temporary, destination)
    finally:
        if fd is not None:
            os.close(fd)
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()


def write_run_artifact_json(run_dir: Path, path: Path, data: Any) -> None:
    write_run_artifact_text(run_dir, path, json.dumps(data, indent=2, ensure_ascii=False) + '\n')


MAX_TARGETS_JSON_BYTES = 16 * 1024 * 1024


def load_targets_artifact(run_dir: Path, default: Any = None) -> Any:
    """Read targets.json through a bounded, no-follow file descriptor."""

    path = configured_reports_dir(run_dir) / 'targets.json'
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)
    try:
        fd = os.open(path, flags)
    except FileNotFoundError:
        return default
    except OSError as exc:
        raise OSError('targets.json must be a regular non-symlink file') from exc
    try:
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode):
            raise OSError('targets.json must be a regular non-symlink file')
        if metadata.st_size > MAX_TARGETS_JSON_BYTES:
            raise OSError(f'targets.json exceeds the {MAX_TARGETS_JSON_BYTES}-byte limit')
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(fd, min(1024 * 1024, MAX_TARGETS_JSON_BYTES + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > MAX_TARGETS_JSON_BYTES:
                raise OSError(f'targets.json exceeds the {MAX_TARGETS_JSON_BYTES}-byte limit')
        return json.loads(b''.join(chunks).decode('utf-8'))
    finally:
        os.close(fd)


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
    # CPython on Windows requires SYSTEMROOT in an explicitly supplied child
    # environment. Preserve only bounded runtime variables; do not inherit PATH,
    # credential variables, Python module paths, or the rest of the host environment.
    child_env = {
        key: os.environ[key]
        for key in ('SYSTEMROOT', 'WINDIR', 'PYTHONHASHSEED')
        if key in os.environ
    }
    child_env.update(env)
    subprocess.run(cmd, check=True, env=child_env)


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
    executable: Optional[str] = None,
    sandbox: str = 'workspace-write',
    ephemeral: bool = False,
    ignore_user_config: bool = False,
    ignore_rules: bool = False,
    output_schema: Optional[Path] = None,
) -> List[str]:
    if sandbox not in {'read-only', 'workspace-write'}:
        raise ValueError(f'unsupported Codex sandbox mode: {sandbox}')
    args = [
        executable or codex_worker_executable(), 'exec',
        '--cd', str(run_dir),
        '--skip-git-repo-check',
        '--model', model,
        '--sandbox', sandbox,
        '--color', 'never',
        '--output-last-message', str(output_last),
        '-c', codex_config_arg('approval_policy', approval),
        '-c', codex_config_arg('model_reasoning_effort', effort),
        '-c', codex_config_arg('web_search', 'disabled'),
        '-c', codex_config_arg('sandbox_workspace_write.network_access', network),
    ]
    if ephemeral:
        args.append('--ephemeral')
    if ignore_user_config:
        args.append('--ignore-user-config')
    if ignore_rules:
        args.append('--ignore-rules')
    if output_schema is not None:
        args.extend(('--output-schema', str(output_schema)))
    args.extend(('--json', '-'))
    return args


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
    from run_state import paused_error

    pause_message = paused_error(run_dir, action=f"Codex exec for {prompt_file.name}")
    if pause_message:
        print(pause_message, file=sys.stderr)
        return 5
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


def load_targets(run_dir: Path, *, include_deferred: bool = False) -> List[Dict[str, Any]]:
    data = load_targets_artifact(run_dir)
    if data is None:
        return []
    if not isinstance(data, dict):
        raise ValueError('targets artifact must be an object')
    active = data.get('targets')
    if not isinstance(active, list) or any(not isinstance(target, dict) for target in active):
        raise ValueError('targets artifact targets must be a list of objects')
    targets = list(active)
    if include_deferred:
        deferred = data.get('deferred_targets') or []
        if not isinstance(deferred, list) or any(not isinstance(target, dict) for target in deferred):
            raise ValueError('targets artifact deferred_targets must be a list of objects')
        targets.extend(deferred)
    return targets


def target_ids_with_lineage(targets: List[Dict[str, Any]]) -> set[str]:
    ids = {str(target.get('id') or '') for target in targets if target.get('id')}
    for target in targets:
        lineage = target.get('source_lineage')
        if not isinstance(lineage, list):
            continue
        ids.update(
            str(item.get('target_id') or '')
            for item in lineage
            if isinstance(item, dict) and item.get('target_id')
        )
    return ids


def write_targets(run_dir: Path, targets: List[Dict[str, Any]]) -> None:
    from target_coverage_guardrails import append_coverage_normalization_log, normalize_targets_coverage_for_write

    ctx = load_context(run_dir)
    reports_dir = configured_reports_dir(run_dir)
    data = load_targets_artifact(run_dir, {}) or {}
    if not isinstance(data, dict):
        raise ValueError('targets artifact must be an object')
    if isinstance(data.get('queue_summary'), dict):
        from target_queue import validate_target_queue_artifact

        queue_errors = validate_target_queue_artifact(data)
        if queue_errors:
            raise ValueError(queue_errors[0])
    normalized_targets, coverage_changes = normalize_targets_coverage_for_write(targets)
    data.update({
        'run_id': ctx.get('run_id', run_dir.name),
        'repo': ctx.get('repo', ''),
        'branch': ctx.get('branch', ''),
        'commit': ctx.get('commit', ''),
        'generated_at': data.get('generated_at') or utc_now(),
        'targets': normalized_targets,
    })
    if isinstance(data.get('queue_summary'), dict):
        from target_queue import preserve_target_queue_membership

        deferred_targets = data.get('deferred_targets') or []
        if not isinstance(deferred_targets, list) or any(not isinstance(item, dict) for item in deferred_targets):
            raise ValueError('stored deferred target queue is invalid')
        normalized_deferred, deferred_changes = normalize_targets_coverage_for_write(deferred_targets)
        normalized_active, normalized_deferred, summary = preserve_target_queue_membership(
            normalized_targets,
            normalized_deferred,
            summary=data['queue_summary'],
        )
        data.update({
            'targets': normalized_active,
            'deferred_targets': normalized_deferred,
            'queue_summary': summary,
        })
        coverage_changes.extend(deferred_changes)
        queue_errors = validate_target_queue_artifact(data)
        if queue_errors:
            raise ValueError(queue_errors[0])
    write_run_artifact_json(run_dir, reports_dir / 'targets.json', data)
    append_coverage_normalization_log(reports_dir, coverage_changes)


def write_model_generated_targets(run_dir: Path, targets: List[Dict[str, Any]]) -> None:
    """Replace untrusted model output with a clean, source-bound seed list."""

    from target_coverage_guardrails import append_coverage_normalization_log, normalize_targets_coverage_for_write

    if any(not isinstance(target, dict) for target in targets):
        raise ValueError('model target entries must be objects')
    ctx = load_context(run_dir)
    reports_dir = configured_reports_dir(run_dir)
    sanitized: list[Dict[str, Any]] = []
    for target in targets:
        value = dict(target)
        value['queue_source'] = 'model_generated'
        value.pop('queue_fingerprint', None)
        value.pop('source_lineage', None)
        sanitized.append(value)
    normalized, coverage_changes = normalize_targets_coverage_for_write(sanitized)
    data = load_targets_artifact(run_dir, {}) or {}
    generated_at = data.get('generated_at') if isinstance(data, dict) else None
    clean = {
        'run_id': ctx.get('run_id', run_dir.name),
        'repo': ctx.get('repo', ''),
        'branch': ctx.get('branch', ''),
        'commit': ctx.get('commit', ''),
        'generated_at': generated_at or utc_now(),
        'targets': normalized,
    }
    write_run_artifact_json(run_dir, reports_dir / 'targets.json', clean)
    append_coverage_normalization_log(reports_dir, coverage_changes)


def append_source_generated_targets(
    run_dir: Path,
    *,
    baseline: Dict[str, Any],
    generated_targets: List[Dict[str, Any]],
    source: str,
) -> List[Dict[str, Any]]:
    """Restore a trusted baseline and append only newly generated source seeds."""

    from target_queue import TARGET_SOURCES, validate_target_queue_artifact

    if source not in TARGET_SOURCES or source in {'model_generated', 'gapfill'}:
        raise ValueError('generated target source is not allowed for this append path')
    if not isinstance(baseline, dict) or any(not isinstance(item, dict) for item in generated_targets):
        raise ValueError('generated target artifact is invalid')
    baseline_errors = validate_target_queue_artifact(baseline)
    if baseline_errors:
        raise ValueError(baseline_errors[0])
    active = baseline.get('targets') or []
    deferred = baseline.get('deferred_targets') or []
    if not isinstance(active, list) or not isinstance(deferred, list) or any(
        not isinstance(item, dict) for item in [*active, *deferred]
    ):
        raise ValueError('baseline target artifact is invalid')
    protected_ids = target_ids_with_lineage([*active, *deferred])
    additions: List[Dict[str, Any]] = []
    seen_ids = set(protected_ids)
    for target in generated_targets:
        target_id = str(target.get('id') or '')
        if not target_id or target_id in seen_ids:
            continue
        value = dict(target)
        value['queue_source'] = source
        value.pop('queue_fingerprint', None)
        value.pop('source_lineage', None)
        additions.append(value)
        seen_ids.add(target_id)
    write_run_artifact_json(run_dir, configured_reports_dir(run_dir) / 'targets.json', baseline)
    write_targets(run_dir, [*active, *additions])
    return additions


def _resolved_target_queue(
    data: Dict[str, Any],
    *,
    total_budget: int | None = None,
    source_budgets: Dict[str, int] | None = None,
    policy: str | None = None,
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    from target_queue import BUDGETED_TARGET_SOURCES, TargetBudgets, TargetQueueError, apply_target_queue_policy, default_budgets

    if not isinstance(data, dict):
        raise TargetQueueError('targets artifact must be an object')
    existing_summary = data.get('queue_summary')
    if existing_summary is not None and not isinstance(existing_summary, dict):
        raise TargetQueueError('stored queue summary must be an object')
    existing_summary = existing_summary or {}
    existing_budgets = existing_summary.get('budgets')
    if existing_summary and (
        not isinstance(existing_budgets, dict)
        or set(existing_budgets) != {'total', 'by_source'}
        or not isinstance(existing_budgets.get('by_source'), dict)
        or set(existing_budgets.get('by_source') or {}) != set(BUDGETED_TARGET_SOURCES)
    ):
        raise TargetQueueError('stored target queue budgets are invalid')
    existing_budgets = existing_budgets or {}
    defaults = default_budgets()
    stored_by_source = existing_budgets.get('by_source') or {}
    overrides = source_budgets or {}
    unknown_sources = set(overrides) - set(BUDGETED_TARGET_SOURCES)
    if unknown_sources:
        raise TargetQueueError('per-source budget override uses an unknown source')
    resolved_by_source = {
        source: overrides.get(source, stored_by_source.get(source, defaults.by_source[source]))
        for source in BUDGETED_TARGET_SOURCES
    }
    budgets = TargetBudgets(
        total=total_budget if total_budget is not None else existing_budgets.get('total', defaults.total),
        by_source=resolved_by_source,
    )
    targets = data.get('targets') or []
    deferred = data.get('deferred_targets') or []
    if not isinstance(targets, list) or not isinstance(deferred, list):
        raise TargetQueueError('active and deferred targets must be lists')
    if any(not isinstance(item, dict) for item in [*targets, *deferred]):
        raise TargetQueueError('active and deferred target entries must be objects')
    return apply_target_queue_policy(
        [*targets, *deferred],
        budgets=budgets,
        policy=policy or str(existing_summary.get('policy') or 'risk-weighted'),
    )


def rebalance_target_queue(
    run_dir: Path,
    *,
    total_budget: int | None = None,
    source_budgets: Dict[str, int] | None = None,
    policy: str | None = None,
) -> Dict[str, Any]:
    from target_coverage_guardrails import append_coverage_normalization_log, normalize_targets_coverage_for_write
    from target_queue import validate_target_queue_artifact

    ctx = load_context(run_dir)
    reports_dir = configured_reports_dir(run_dir)
    path = reports_dir / 'targets.json'
    data = load_targets_artifact(run_dir, {}) or {}
    active, deferred, summary = _resolved_target_queue(
        data,
        total_budget=total_budget,
        source_budgets=source_budgets,
        policy=policy,
    )
    normalized_active, coverage_changes = normalize_targets_coverage_for_write(active)
    normalized_deferred, deferred_changes = normalize_targets_coverage_for_write(deferred)
    data.update({
        'run_id': ctx.get('run_id', run_dir.name),
        'repo': ctx.get('repo', ''),
        'branch': ctx.get('branch', ''),
        'commit': ctx.get('commit', ''),
        'generated_at': data.get('generated_at') or utc_now(),
        'targets': normalized_active,
        'deferred_targets': normalized_deferred,
        'queue_summary': summary,
    })
    queue_errors = validate_target_queue_artifact(data)
    if queue_errors:
        raise ValueError(queue_errors[0])
    write_run_artifact_json(run_dir, path, data)
    append_coverage_normalization_log(reports_dir, [*coverage_changes, *deferred_changes])
    return summary


def find_target(run_dir: Path, target_id: str) -> Dict[str, Any]:
    for t in load_targets(run_dir):
        if str(t.get('id')) == target_id:
            return t
    raise KeyError(f'target not found: {target_id}')


def load_findings(run_dir: Path) -> List[Dict[str, Any]]:
    data = load_json(configured_reports_dir(run_dir) / 'findings.json', {}) or {}
    findings = data.get('findings') or []
    return [f for f in findings if isinstance(f, dict)]


def find_finding(run_dir: Path, finding_id: str) -> Dict[str, Any]:
    for f in load_findings(run_dir):
        if str(f.get('id')) == finding_id:
            return f
    raise KeyError(f'finding not found: {finding_id}')


def slug(text: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-') or 'item'
