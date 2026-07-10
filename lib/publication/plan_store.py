from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict


PLAN_REL_PATH = Path("reports") / "issue-publication-plan.json"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def default_plan_path(run_dir: Path) -> Path:
    return run_dir / PLAN_REL_PATH


def write_plan(plan_path: Path, plan: Dict[str, Any]) -> None:
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_plan(plan_path: Path) -> Dict[str, Any]:
    data = json.loads(plan_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("issue publication plan must be a JSON object")
    if not isinstance(data.get("selected_findings"), list):
        raise ValueError("issue publication plan must contain selected_findings array")
    for index, entry in enumerate(data["selected_findings"]):
        if not isinstance(entry, dict):
            raise ValueError(f"selected_findings[{index}] must be an object")
    return data


def plan_hash(plan_path: Path) -> str:
    return sha256_file(plan_path)
