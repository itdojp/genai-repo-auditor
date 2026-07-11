from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from pathlib import Path, PurePosixPath
from typing import Any


MAX_JSON_BYTES = 512_000
MAX_FIXTURE_BYTES = 128_000
CONTENT_VERSION_RE = re.compile(r"^(?P<release>[0-9]+\.[0-9]+\.[0-9]+)\+sha256\.(?P<digest>[a-f0-9]{64})$")
OPEN_SUPPORTS_DIR_FD = (
    os.open in os.supports_dir_fd
    and bool(getattr(os, "O_DIRECTORY", 0))
    and bool(getattr(os, "O_NOFOLLOW", 0))
)
SEVERITY_ORDER = {"Low": 0, "Medium": 1, "High": 2, "Critical": 3}
CATEGORY_SUITES = {
    "python-web": "appsec",
    "github-actions": "automation",
    "ai-agent-mcp": "agentic",
    "dependency-supply-chain": "supply-chain",
}
FORBIDDEN_PUBLIC_MARKERS = (
    "http://",
    "https://",
    "ssh://",
    "git@",
    "-----begin ",
    "ghp_",
    "github_pat_",
    "glpat-",
    "subprocess",
    "os.system",
    "child_process",
)
FORBIDDEN_PUBLIC_HELPER_RE = re.compile(r"(?<![a-z0-9_-])(?:curl|wget)(?![a-z0-9_-])")
SUPPORTED_SCHEMA_KEYS = {
    "$defs",
    "$ref",
    "$schema",
    "additionalProperties",
    "const",
    "enum",
    "items",
    "maximum",
    "maxItems",
    "maxLength",
    "minimum",
    "minItems",
    "minLength",
    "pattern",
    "properties",
    "required",
    "title",
    "type",
    "uniqueItems",
}


class EfficacyCorpusError(RuntimeError):
    """Raised when the synthetic efficacy corpus violates its public-safe contract."""


def _read_bounded_fd(fd: int, *, maximum: int, label: str) -> tuple[bytes, os.stat_result]:
    try:
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode):
            raise EfficacyCorpusError(f"{label} must be a regular file")
        if metadata.st_size > maximum:
            raise EfficacyCorpusError(f"{label} exceeds the {maximum}-byte limit")
        chunks: list[bytes] = []
        total = 0
        while chunk := os.read(fd, min(65_536, maximum + 1 - total)):
            chunks.append(chunk)
            total += len(chunk)
            if total > maximum:
                raise EfficacyCorpusError(f"{label} exceeds the {maximum}-byte limit")
        return b"".join(chunks), metadata
    except OSError as exc:
        raise EfficacyCorpusError(f"{label} could not be read safely") from exc


def _safe_relative_path(relative: Any, *, label: str) -> PurePosixPath:
    if isinstance(relative, PurePosixPath):
        relative = relative.as_posix()
    if not isinstance(relative, str) or not relative:
        raise EfficacyCorpusError(f"{label} must be a non-empty relative path")
    pure = PurePosixPath(relative)
    if (
        pure.is_absolute()
        or pure.as_posix() != relative
        or "." in pure.parts
        or ".." in pure.parts
        or "\\" in relative
        or ":" in relative
    ):
        raise EfficacyCorpusError(f"{label} must stay under the corpus root")
    return pure


class _SafeTreeReader:
    """Read files relative to one directory handle without following symlinks."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve(strict=True)
        self._root_fd: int | None = None
        if OPEN_SUPPORTS_DIR_FD:
            try:
                self._root_fd = os.open(
                    self.root,
                    os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
                )
            except OSError as exc:
                raise EfficacyCorpusError("corpus root must be a readable directory") from exc

    def close(self) -> None:
        if self._root_fd is not None:
            os.close(self._root_fd)
            self._root_fd = None

    def __enter__(self) -> _SafeTreeReader:
        return self

    def __exit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        self.close()

    def read(self, relative: Any, *, maximum: int, label: str) -> tuple[bytes, os.stat_result]:
        pure = _safe_relative_path(relative, label=label)
        if self._root_fd is not None:
            return self._read_at(pure, maximum=maximum, label=label)
        return self._read_portable(pure, maximum=maximum, label=label)

    def _read_at(self, relative: PurePosixPath, *, maximum: int, label: str) -> tuple[bytes, os.stat_result]:
        assert self._root_fd is not None
        directory_fd = os.dup(self._root_fd)
        file_fd: int | None = None
        try:
            for component in relative.parts[:-1]:
                next_fd = os.open(
                    component,
                    os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=directory_fd,
                )
                os.close(directory_fd)
                directory_fd = next_fd
            file_fd = os.open(
                relative.parts[-1],
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=directory_fd,
            )
            return _read_bounded_fd(file_fd, maximum=maximum, label=label)
        except OSError as exc:
            raise EfficacyCorpusError(
                f"{label} must be a readable regular file without symlink components"
            ) from exc
        finally:
            if file_fd is not None:
                os.close(file_fd)
            os.close(directory_fd)

    def _read_portable(
        self,
        relative: PurePosixPath,
        *,
        maximum: int,
        label: str,
    ) -> tuple[bytes, os.stat_result]:
        # Platforms without openat-style dir_fd support receive pre/post identity
        # checks. Supported Unix platforms use _read_at and never reopen ancestors
        # by pathname after validation.
        path = self.root.joinpath(*relative.parts)
        components = [
            self.root,
            *(self.root.joinpath(*relative.parts[:index]) for index in range(1, len(relative.parts))),
        ]
        try:
            before = [os.lstat(component) for component in components]
            leaf_before = os.lstat(path)
            if any(stat.S_ISLNK(item.st_mode) for item in before) or stat.S_ISLNK(leaf_before.st_mode):
                raise EfficacyCorpusError(f"{label} must not contain symlink components")
            fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        except OSError as exc:
            raise EfficacyCorpusError(
                f"{label} must be a readable regular file without symlink components"
            ) from exc
        try:
            raw, metadata = _read_bounded_fd(fd, maximum=maximum, label=label)
            leaf = os.lstat(path)
            after = [os.lstat(component) for component in components]
            identities_before = [(item.st_dev, item.st_ino, item.st_mode) for item in before]
            identities_after = [(item.st_dev, item.st_ino, item.st_mode) for item in after]
            leaf_before_identity = (leaf_before.st_dev, leaf_before.st_ino, leaf_before.st_mode)
            leaf_after_identity = (leaf.st_dev, leaf.st_ino, leaf.st_mode)
            leaf_identity = (leaf.st_dev, leaf.st_ino)
            descriptor_identity = (metadata.st_dev, metadata.st_ino)
            if (
                identities_before != identities_after
                or leaf_before_identity != leaf_after_identity
                or leaf_identity != descriptor_identity
            ):
                raise EfficacyCorpusError(f"{label} changed while it was being read")
            return raw, metadata
        except OSError as exc:
            raise EfficacyCorpusError(f"{label} changed while it was being read") from exc
        finally:
            os.close(fd)


def _load_json(reader: _SafeTreeReader, relative: Any, *, label: str) -> tuple[dict[str, Any], bytes]:
    raw, _metadata = reader.read(relative, maximum=MAX_JSON_BYTES, label=label)
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EfficacyCorpusError(f"{label} must contain valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise EfficacyCorpusError(f"{label} must contain a JSON object")
    return value, raw


def _require_public_safe_text(raw: bytes, *, label: str) -> str:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise EfficacyCorpusError(f"{label} must contain valid UTF-8 text") from exc
    if _contains_forbidden_public_marker(text):
        raise EfficacyCorpusError(
            f"{label} contains a prohibited live-network, credential, or execution marker"
        )
    return text


def _contains_forbidden_public_marker(text: str) -> bool:
    normalized = text.lower()
    replacements = ((r"\/", "/"), (r"\u002f", "/"), (r"\x2f", "/"), (r"\u003a", ":"), (r"\x3a", ":"))
    for _attempt in range(3):
        updated = normalized
        for escaped, literal in replacements:
            updated = updated.replace(escaped, literal)
        if updated == normalized:
            break
        normalized = updated
    return any(marker in normalized for marker in FORBIDDEN_PUBLIC_MARKERS) or bool(
        FORBIDDEN_PUBLIC_HELPER_RE.search(normalized)
    )


def _require_public_safe_json(value: Any, *, label: str) -> None:
    pending = [value]
    while pending:
        current = pending.pop()
        if isinstance(current, dict):
            pending.extend(current.keys())
            pending.extend(current.values())
        elif isinstance(current, list):
            pending.extend(current)
        elif isinstance(current, str):
            if _contains_forbidden_public_marker(current):
                raise EfficacyCorpusError(
                    f"{label} contains a prohibited live-network, credential, or execution marker"
                )


def _require_supported_schema(schema: dict[str, Any], *, label: str) -> None:
    def visit(node: Any, path: str) -> None:
        if not isinstance(node, dict):
            raise EfficacyCorpusError(f"{label} must contain object-valued schema nodes")
        unsupported = set(node) - SUPPORTED_SCHEMA_KEYS
        if unsupported:
            raise EfficacyCorpusError(f"{label} contains unsupported schema keywords at {path}")
        if "$ref" in node:
            if set(node) != {"$ref"} or not isinstance(node["$ref"], str) or not node["$ref"].startswith("#/"):
                raise EfficacyCorpusError(f"{label} contains an unsupported reference form at {path}")
            return
        schema_type = node.get("type")
        schema_types = schema_type if isinstance(schema_type, list) else [schema_type]
        allowed_types = {"array", "boolean", "integer", "null", "object", "string"}
        if schema_type is not None and (
            not schema_types
            or any(not isinstance(item, str) or item not in allowed_types for item in schema_types)
            or len(schema_types) != len(set(schema_types))
        ):
            raise EfficacyCorpusError(f"{label} contains an unsupported type contract at {path}")
        if "object" in schema_types and node.get("additionalProperties") is not False:
            raise EfficacyCorpusError(f"{label} requires closed object contracts at {path}")
        if "enum" in node and (not isinstance(node["enum"], list) or not node["enum"]):
            raise EfficacyCorpusError(f"{label} contains an invalid enum at {path}")
        if "required" in node and (
            not isinstance(node["required"], list)
            or any(not isinstance(item, str) for item in node["required"])
            or len(node["required"]) != len(set(node["required"]))
        ):
            raise EfficacyCorpusError(f"{label} contains an invalid required list at {path}")
        for keyword in ("minimum", "maximum", "minItems", "maxItems", "minLength", "maxLength"):
            if keyword in node and (not isinstance(node[keyword], int) or isinstance(node[keyword], bool)):
                raise EfficacyCorpusError(f"{label} contains an invalid numeric constraint at {path}")
        if "uniqueItems" in node and not isinstance(node["uniqueItems"], bool):
            raise EfficacyCorpusError(f"{label} contains an invalid uniqueness constraint at {path}")
        if "pattern" in node:
            if not isinstance(node["pattern"], str):
                raise EfficacyCorpusError(f"{label} contains an invalid pattern at {path}")
            try:
                re.compile(node["pattern"])
            except re.error as exc:
                raise EfficacyCorpusError(f"{label} contains an invalid pattern at {path}") from exc
        for container_name in ("$defs", "properties"):
            container = node.get(container_name)
            if container is None:
                continue
            if not isinstance(container, dict):
                raise EfficacyCorpusError(f"{label} contains an invalid schema container at {path}")
            for name, child in container.items():
                visit(child, f"{path}.{container_name}.{name}")
        items = node.get("items")
        if items is not None:
            visit(items, f"{path}.items")

    visit(schema, "$")


def _json_type(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    return True


def _schema_ref(root_schema: dict[str, Any], ref: str) -> dict[str, Any]:
    if not ref.startswith("#/"):
        raise EfficacyCorpusError("corpus schemas may use only local JSON pointers")
    value: Any = root_schema
    for raw_part in ref[2:].split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if not isinstance(value, dict) or part not in value:
            raise EfficacyCorpusError("corpus schema contains an unresolved local reference")
        value = value[part]
    if not isinstance(value, dict):
        raise EfficacyCorpusError("corpus schema reference must resolve to an object")
    return value


def _validate_schema(
    value: Any,
    schema: dict[str, Any],
    root_schema: dict[str, Any],
    path: str,
    errors: list[str],
) -> None:
    if "$ref" in schema:
        _validate_schema(value, _schema_ref(root_schema, str(schema["$ref"])), root_schema, path, errors)
        return
    expected = schema.get("type")
    if expected is not None:
        choices = expected if isinstance(expected, list) else [expected]
        if not any(_json_type(value, str(choice)) for choice in choices):
            errors.append(f"{path}: unexpected JSON type")
            return
    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: value does not match the corpus constant")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: value is outside the corpus enum")
    if isinstance(value, dict):
        properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{path}.{key}: missing required field")
        if schema.get("additionalProperties") is False and set(value) - set(properties):
            errors.append(f"{path}: contains fields outside the closed corpus contract")
        for key, item in value.items():
            subschema = properties.get(key)
            if isinstance(subschema, dict):
                _validate_schema(item, subschema, root_schema, f"{path}.{key}", errors)
    if isinstance(value, list):
        minimum = schema.get("minItems")
        maximum = schema.get("maxItems")
        if isinstance(minimum, int) and len(value) < minimum:
            errors.append(f"{path}: has too few items")
        if isinstance(maximum, int) and len(value) > maximum:
            errors.append(f"{path}: has too many items")
        if schema.get("uniqueItems") is True:
            serialized = [json.dumps(item, sort_keys=True, separators=(",", ":")) for item in value]
            if len(serialized) != len(set(serialized)):
                errors.append(f"{path}: items must be unique")
        if isinstance(schema.get("items"), dict):
            for index, item in enumerate(value):
                _validate_schema(item, schema["items"], root_schema, f"{path}[{index}]", errors)
    if isinstance(value, str):
        if isinstance(schema.get("minLength"), int) and len(value) < schema["minLength"]:
            errors.append(f"{path}: string is too short")
        if isinstance(schema.get("maxLength"), int) and len(value) > schema["maxLength"]:
            errors.append(f"{path}: string is too long")
        if isinstance(schema.get("pattern"), str) and re.search(schema["pattern"], value) is None:
            errors.append(f"{path}: string does not match the corpus pattern")
    if isinstance(value, int) and not isinstance(value, bool):
        if isinstance(schema.get("minimum"), int) and value < schema["minimum"]:
            errors.append(f"{path}: integer is below the minimum")
        if isinstance(schema.get("maximum"), int) and value > schema["maximum"]:
            errors.append(f"{path}: integer exceeds the maximum")


def _require_schema(value: dict[str, Any], schema: dict[str, Any], *, label: str) -> None:
    errors: list[str] = []
    _validate_schema(value, schema, schema, label, errors)
    if errors:
        raise EfficacyCorpusError("; ".join(errors))


def _require_content_version(value: dict[str, Any], field: str, *, label: str) -> None:
    version = value.get(field)
    match = CONTENT_VERSION_RE.fullmatch(version) if isinstance(version, str) else None
    if match is None:
        raise EfficacyCorpusError(f"{label} must use a content-bound version")
    canonical = dict(value)
    canonical[field] = match.group("release")
    encoded = json.dumps(canonical, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    expected = hashlib.sha256(encoded).hexdigest()
    if match.group("digest") != expected:
        raise EfficacyCorpusError(f"{label} does not match the versioned content")


def _validate_case_semantics(
    case: dict[str, Any],
    reader: _SafeTreeReader,
    case_prefix: PurePosixPath,
) -> None:
    positive = case["ground_truth"]["positive_findings"]
    controls = case["ground_truth"]["negative_controls"]
    if case["classification"] == "positive":
        if len(positive) != 1 or controls:
            raise EfficacyCorpusError(
                "positive corpus cases require exactly one positive finding and no negative controls"
            )
    elif positive or len(controls) != 1:
        raise EfficacyCorpusError("negative-control corpus cases require exactly one control and no positive findings")
    for finding in positive:
        severity = finding["severity_range"]
        if SEVERITY_ORDER[severity["minimum"]] > SEVERITY_ORDER[severity["maximum"]]:
            raise EfficacyCorpusError("positive finding severity range is reversed")
        for location in [finding["entry_point"], finding["sink"], *finding["affected_locations"]]:
            if location["end_line"] < location["line"]:
                raise EfficacyCorpusError("ground-truth location end_line precedes line")
    for control in controls:
        if control["location"]["end_line"] < control["location"]["line"]:
            raise EfficacyCorpusError("negative-control location end_line precedes line")
    stages = case["stage_expectations"]
    stage_sets = [set(stages[name]) for name in ("required", "optional", "prohibited")]
    if stage_sets[0] & stage_sets[1] or stage_sets[0] & stage_sets[2] or stage_sets[1] & stage_sets[2]:
        raise EfficacyCorpusError("stage expectation sets must not overlap")
    if "issue-publication" not in stage_sets[2]:
        raise EfficacyCorpusError("synthetic corpus cases must prohibit Issue publication")

    file_refs = case["fixture"]["files"]
    file_paths = [item["path"] for item in file_refs]
    if file_paths != sorted(file_paths):
        raise EfficacyCorpusError("fixture file references must be sorted")
    if len(file_paths) != len(set(file_paths)):
        raise EfficacyCorpusError("fixture file paths must be unique")
    fixture_line_counts: dict[str, int] = {}
    for item in file_refs:
        fixture_relative = _safe_relative_path(item["path"], label="fixture file")
        raw, metadata = reader.read(
            case_prefix / fixture_relative,
            maximum=MAX_FIXTURE_BYTES,
            label="fixture file",
        )
        if hashlib.sha256(raw).hexdigest() != item["sha256"]:
            raise EfficacyCorpusError("fixture file digest does not match its case manifest")
        if metadata.st_mode & 0o111:
            raise EfficacyCorpusError("fixture files must not be executable")
        text = _require_public_safe_text(raw, label="fixture file")
        if fixture_relative.suffix == ".json":
            try:
                fixture_json = json.loads(text)
            except json.JSONDecodeError as exc:
                raise EfficacyCorpusError("JSON fixture file must contain valid JSON") from exc
            _require_public_safe_json(fixture_json, label="fixture file")
        fixture_line_counts[item["path"]] = len(text.splitlines())
    locations = [
        location
        for finding in positive
        for location in [finding["entry_point"], finding["sink"], *finding["affected_locations"]]
    ]
    locations.extend(control["location"] for control in controls)
    for location in locations:
        line_count = fixture_line_counts.get(location["file"])
        if line_count is None or location["line"] > line_count or location["end_line"] > line_count:
            raise EfficacyCorpusError("ground-truth location must reference a line in a declared fixture file")


def load_corpus(lab_root: Path) -> dict[str, Any]:
    """Load and validate the immutable synthetic efficacy corpus without network access."""

    corpus_path = PurePosixPath("benchmarks/corpus/core.json")
    corpus_prefix = PurePosixPath("benchmarks/corpus")
    with _SafeTreeReader(lab_root) as reader:
        corpus_schema, _ = _load_json(reader, corpus_prefix / "corpus.schema.json", label="corpus schema")
        case_schema, _ = _load_json(reader, corpus_prefix / "case.schema.json", label="case schema")
        _require_supported_schema(corpus_schema, label="corpus schema")
        _require_supported_schema(case_schema, label="case schema")
        corpus, raw_corpus = _load_json(reader, corpus_path, label="corpus index")
        _require_public_safe_text(raw_corpus, label="corpus index")
        _require_public_safe_json(corpus, label="corpus index")
        _require_schema(corpus, corpus_schema, label="corpus")

        entries = corpus["cases"]
        case_ids = [entry["case_id"] for entry in entries]
        if case_ids != sorted(case_ids) or len(case_ids) != len(set(case_ids)):
            raise EfficacyCorpusError("corpus case IDs must be unique and sorted")
        cases: list[dict[str, Any]] = []
        positive_count = 0
        negative_count = 0
        categories: set[str] = set()
        for entry in entries:
            manifest = _safe_relative_path(entry["manifest"], label="case manifest")
            expected_manifest = PurePosixPath("cases") / entry["case_id"] / "case.json"
            if manifest != expected_manifest:
                raise EfficacyCorpusError("case manifest path does not match its case ID")
            manifest_relative = corpus_prefix / manifest
            case, raw_manifest = _load_json(reader, manifest_relative, label="case manifest")
            _require_public_safe_text(raw_manifest, label="case manifest")
            _require_public_safe_json(case, label="case manifest")
            if hashlib.sha256(raw_manifest).hexdigest() != entry["manifest_sha256"]:
                raise EfficacyCorpusError("case manifest digest does not match the corpus index")
            _require_schema(case, case_schema, label=f"case[{entry['case_id']}]")
            identity_fields = ("case_id", "case_version", "classification", "category")
            if any(case[field] != entry[field] for field in identity_fields):
                raise EfficacyCorpusError("case manifest identity does not match the corpus index")
            category_suite = CATEGORY_SUITES.get(entry["category"])
            if category_suite is None:
                raise EfficacyCorpusError("case category does not have a canonical suite")
            if entry["suites"] != ["core", category_suite]:
                raise EfficacyCorpusError("case suites must contain core and the canonical category suite")
            _validate_case_semantics(case, reader, manifest_relative.parent)
            _require_content_version(case, "case_version", label="case version")
            cases.append(case)
            positive_count += case["classification"] == "positive"
            negative_count += case["classification"] == "negative_control"
            categories.add(case["category"])
        if positive_count < 5 or negative_count < 3 or len(categories) < 3:
            raise EfficacyCorpusError("core corpus must include five positives, three controls, and three categories")
        _require_content_version(corpus, "corpus_version", label="corpus version")
        return {"corpus": corpus, "cases": cases}
