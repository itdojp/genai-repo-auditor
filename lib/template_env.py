from __future__ import annotations

import re
from typing import Dict, Mapping

CONTROLLED_PREFIX = 'GRA_TEMPLATE_'
PLACEHOLDER_RE = re.compile(r'^[A-Z0-9_]+$')
PLACEHOLDER_PATTERN = re.compile(r'{{([A-Z0-9_]+)}}')
DENYLIST_RE = re.compile(r'(?:TOKEN|SECRET|KEY|PASSWORD|COOKIE|SESSION|CREDENTIAL)')

# Explicitly supported template placeholders. Values may come from defaults,
# same-named environment variables, or controlled GRA_TEMPLATE_<NAME> variables.
DEFAULT_TEMPLATE_VALUES: Dict[str, str] = {
    'RUN_ID': '',
    'REPO': '',
    'REPO_SLUG': '',
    'BRANCH': '',
    'COMMIT': '',
    'VISIBILITY': 'UNKNOWN',
    'RUN_DIR': '',
    'REPO_DIR': '',
    'TARGET_REPO_DIR': 'repo',
    'REPORTS_DIR': 'reports',
    'REPORT_DIR': '',
    'TARGET_ID': '',
    'TARGET_CATEGORY': '',
    'TARGET_SCOPE': '',
    'TARGET_FILE': '',
    'FINDING_ID': '',
    'VARIANT_SOURCE': '',
    'SCANNER_INDEX': 'reports/scanner-results/scanner-index.json',
    'VALIDATION_SELECTION': '',
    'VALIDATION_SUBJECTS_FILE': '',
    'VALIDATION_OUTPUT_JSON': 'reports/validation.json',
    'VALIDATION_OUTPUT_MD': 'reports/VALIDATION.md',
    'VALIDATION_VOTES': '1',
    'VALIDATION_POLICY': 'human-review-on-split',
    'VALIDATION_VOTE_ID': 'VOTE-001',
    'VALIDATION_VOTE_INDEX': '1',
    'CHAINS_OUTPUT_JSON': 'reports/chains.json',
    'CHAINS_OUTPUT_MD': 'reports/ATTACK_CHAINS.md',
    'PROOF_SELECTION': '',
    'PROOF_SUBJECTS_FILE': '',
    'PROOFS_OUTPUT_JSON': 'reports/proofs.json',
    'PROOFS_OUTPUT_MD': 'reports/PROOFS.md',
    'PROOFS_DIR': 'reports/proofs',
    'REMEDIATION_SELECTION': '',
    'REMEDIATION_SUBJECTS_FILE': '',
    'REMEDIATION_OUTPUT_JSON': 'reports/remediation/remediation-candidates.json',
    'REMEDIATION_OUTPUT_MD': 'reports/remediation/REMEDIATION_CANDIDATES.md',
    'REMEDIATION_DIR': 'reports/remediation',
    'GAPFILL_TARGET_FILE': '',
    'GAPFILL_OUTPUT_MD': '',
    'GAPFILL_COVERAGE_FILE': 'reports/COVERAGE.md',
    'TRACE_FINDING_ID': '',
    'TRACE_SUBJECTS_FILE': '',
    'TRACE_OUTPUT_JSON': 'reports/traces.json',
    'TRACE_OUTPUT_MD': 'reports/TRACE.md',
    'TRACE_PRODUCER_RUN_DIR': '',
    'TRACE_CONSUMER_RUN_DIR': '',
    'TRACE_CONSUMER_REPO': '',
    'TRACE_CONSUMER_REPO_DIR': '',
}


def is_denied_placeholder(name: str) -> bool:
    return bool(DENYLIST_RE.search(name))


def validate_template_env_key(key: str) -> None:
    if not PLACEHOLDER_RE.fullmatch(key):
        raise ValueError(f'invalid template environment key: {key}')
    if is_denied_placeholder(key):
        raise ValueError(f'denied template environment key: {key}')


def controlled_placeholder_from_env_key(key: str) -> str:
    placeholder = key[len(CONTROLLED_PREFIX):]
    if not placeholder or not PLACEHOLDER_RE.fullmatch(placeholder):
        raise ValueError(f'invalid controlled template placeholder name: {key}')
    if is_denied_placeholder(placeholder):
        raise ValueError(f'denied controlled template placeholder: {placeholder}')
    return placeholder


def build_template_values(environ: Mapping[str, str]) -> Dict[str, str]:
    values = dict(DEFAULT_TEMPLATE_VALUES)
    for key in DEFAULT_TEMPLATE_VALUES:
        if key in environ and not is_denied_placeholder(key):
            values[key] = environ[key]
    for key, value in environ.items():
        if not key.startswith(CONTROLLED_PREFIX):
            continue
        values[controlled_placeholder_from_env_key(key)] = value
    return values
