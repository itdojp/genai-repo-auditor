from __future__ import annotations

import json
import re
from collections import deque
from pathlib import Path
from typing import Any

from gralib import load_context, utc_now, write_json
from scanner_normalize import redact_text

MAX_PATHS_PER_COMPONENT = 5
MAX_PATH_DEPTH = 12
MAX_TEXT_CHARS = 500
SEVERITY_ORDER = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3, "Informational": 4, "Unknown": 5}
REFERENCES = [
    "https://docs.github.com/en/rest/dependency-graph/sboms",
    "https://cyclonedx.org/specification/overview/",
    "https://spdx.github.io/spdx-spec/v2.3/package-information/",
    "https://spdx.github.io/spdx-spec/v2.3/relationships-between-SPDX-elements/",
]


def _reports_dir(run_dir: Path) -> Path:
    ctx = load_context(run_dir)
    return run_dir / ctx.get("reports_dir", "reports")


def _bounded_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        text = json.dumps(value, sort_keys=True, ensure_ascii=False)
    else:
        text = str(value)
    text = redact_text(text).replace("\r", " ").replace("\n", " ")
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > MAX_TEXT_CHARS:
        return text[:MAX_TEXT_CHARS] + "...<truncated>"
    return text


def _markdown_text(value: Any) -> str:
    text = _bounded_text(value)
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _first_str(*values: Any) -> str:
    for value in values:
        text = _bounded_text(value)
        if text:
            return text
    return ""


def _purl_ecosystem(purl: str) -> str:
    match = re.match(r"^pkg:([^/]+)/", purl or "")
    return match.group(1).lower() if match else "unknown"


def _component_id(*, purl: str, name: str, version: str, fallback: str) -> str:
    if purl:
        return purl
    if name and version:
        return f"pkg:generic/{name}@{version}"
    if name:
        return f"pkg:generic/{name}"
    return fallback


def _license_values(raw: Any) -> list[str]:
    values: list[str] = []
    if isinstance(raw, str):
        values.append(raw)
    for item in _as_list(raw):
        if isinstance(item, str):
            values.append(item)
        elif isinstance(item, dict):
            license_obj = item.get("license") if isinstance(item.get("license"), dict) else item
            value = _first_str(license_obj.get("id"), license_obj.get("name"), license_obj.get("expression"), license_obj.get("value"))
            if value:
                values.append(value)
    return sorted({value for value in values if value and value not in {"NOASSERTION", "NONE"}})


def _detect_format(parsed: Any, requested_format: str) -> str:
    if isinstance(parsed, dict) and isinstance(parsed.get("sbom"), dict):
        return "github-spdx"
    if isinstance(parsed, dict) and str(parsed.get("bomFormat", "")).lower() == "cyclonedx":
        return "cyclonedx"
    if isinstance(parsed, dict) and ("spdxVersion" in parsed or "SPDXID" in parsed or "packages" in parsed and "relationships" in parsed):
        return "spdx"
    if isinstance(parsed, dict) and "artifacts" in parsed and "artifactRelationships" in parsed:
        return "syft"
    if requested_format and requested_format != "auto":
        return requested_format.lower()
    return "unknown"


def _load_sbom(raw_path: Path) -> tuple[Any, str]:
    text = raw_path.read_text(encoding="utf-8")
    return json.loads(text), ""


def _add_component(component: dict[str, Any], components: dict[str, dict[str, Any]], ref_to_id: dict[str, str], ref: str) -> None:
    cid = component["id"]
    components.setdefault(cid, component)
    if ref:
        ref_to_id[ref] = cid
    ref_to_id[cid] = cid


def _paths_from_graph(root_refs: list[str], graph: dict[str, list[str]]) -> dict[str, list[list[str]]]:
    paths: dict[str, list[list[str]]] = {}
    queue: deque[list[str]] = deque([[root] for root in root_refs if root])
    while queue:
        path = queue.popleft()
        current = path[-1]
        for child in graph.get(current, []):
            if child in path:
                continue
            next_path = [*path, child]
            paths.setdefault(child, [])
            if len(paths[child]) < MAX_PATHS_PER_COMPONENT:
                paths[child].append(next_path)
            if len(next_path) < MAX_PATH_DEPTH:
                queue.append(next_path)
    return paths


def _scope_for(ref: str, root_refs: list[str], graph: dict[str, list[str]], paths: dict[str, list[list[str]]]) -> str:
    if any(ref in graph.get(root, []) for root in root_refs):
        return "direct"
    if paths.get(ref):
        return "transitive"
    return "unknown"


def _component_path_strings(paths: list[list[str]], ref_to_id: dict[str, str]) -> list[list[str]]:
    out: list[list[str]] = []
    for path in paths[:MAX_PATHS_PER_COMPONENT]:
        out.append([ref_to_id.get(ref, ref) for ref in path])
    return out


def _cyclonedx_components(parsed: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, str], dict[str, list[str]], list[str]]:
    components: dict[str, dict[str, Any]] = {}
    ref_to_id: dict[str, str] = {}
    graph: dict[str, list[str]] = {}
    metadata_component = parsed.get("metadata", {}).get("component") if isinstance(parsed.get("metadata"), dict) else None
    root_refs: list[str] = []
    if isinstance(metadata_component, dict):
        root_ref = _first_str(metadata_component.get("bom-ref"), metadata_component.get("purl"), metadata_component.get("name"))
        if root_ref:
            root_refs.append(root_ref)
            root_name = _first_str(metadata_component.get("name"), root_ref)
            root_version = _first_str(metadata_component.get("version"))
            root_purl = _first_str(metadata_component.get("purl"))
            root_id = _component_id(purl=root_purl, name=root_name, version=root_version, fallback=root_ref)
            _add_component(
                {
                    "id": root_id,
                    "name": root_name,
                    "version": root_version,
                    "ecosystem": _purl_ecosystem(root_purl),
                    "scope": "root",
                    "licenses": _license_values(metadata_component.get("licenses")),
                    "manifest": "",
                    "dependency_paths": [[root_id]],
                },
                components,
                ref_to_id,
                root_ref,
            )
    for item in _as_list(parsed.get("components")):
        if not isinstance(item, dict):
            continue
        ref = _first_str(item.get("bom-ref"), item.get("purl"), item.get("name"))
        name = _first_str(item.get("name"), ref)
        version = _first_str(item.get("version"))
        purl = _first_str(item.get("purl"))
        manifest = ""
        for prop in _as_list(item.get("properties")):
            if isinstance(prop, dict) and "manifest" in str(prop.get("name", "")).lower():
                manifest = _first_str(prop.get("value"))
                break
        _add_component(
            {
                "id": _component_id(purl=purl, name=name, version=version, fallback=ref),
                "name": name,
                "version": version,
                "ecosystem": _purl_ecosystem(purl),
                "scope": "unknown",
                "licenses": _license_values(item.get("licenses")),
                "manifest": manifest,
                "dependency_paths": [],
            },
            components,
            ref_to_id,
            ref,
        )
    for dep in _as_list(parsed.get("dependencies")):
        if isinstance(dep, dict):
            ref = _first_str(dep.get("ref"))
            graph[ref] = [_first_str(child) for child in _as_list(dep.get("dependsOn")) if _first_str(child)]
    if not root_refs and graph:
        depended = {child for children in graph.values() for child in children}
        roots = [ref for ref in graph if ref not in depended]
        root_refs = roots[:1]
    return components, ref_to_id, graph, root_refs


def _cyclonedx_vulnerabilities(parsed: dict[str, Any], ref_to_id: dict[str, str], paths: dict[str, list[list[str]]]) -> list[dict[str, Any]]:
    vulnerabilities: list[dict[str, Any]] = []
    for vuln in _as_list(parsed.get("vulnerabilities")):
        if not isinstance(vuln, dict):
            continue
        vid = _first_str(vuln.get("id"), vuln.get("bom-ref"))
        if not vid:
            continue
        severity = "Unknown"
        for rating in _as_list(vuln.get("ratings")):
            if isinstance(rating, dict) and rating.get("severity"):
                severity = _first_str(rating.get("severity")).title()
                break
        source = vuln.get("source") if isinstance(vuln.get("source"), dict) else {}
        recommendation = _first_str(vuln.get("recommendation"))
        fixed_version = ""
        if recommendation:
            match = re.search(r"(?:fixed in|upgrade to|>=|version)\s+([A-Za-z0-9_.:+~-]+)", recommendation, re.IGNORECASE)
            fixed_version = match.group(1) if match else ""
        affects = _as_list(vuln.get("affects")) or [{}]
        for affected in affects:
            ref = _first_str(affected.get("ref") if isinstance(affected, dict) else "")
            component = ref_to_id.get(ref, ref)
            for version in _as_list(affected.get("versions") if isinstance(affected, dict) else None):
                if isinstance(version, dict) and _first_str(version.get("status")).lower() == "fixed":
                    fixed_version = _first_str(version.get("version"), fixed_version)
                    break
            vulnerabilities.append(
                {
                    "id": vid,
                    "component": component,
                    "severity": severity if severity in SEVERITY_ORDER else "Unknown",
                    "fixed_version": fixed_version,
                    "source": _first_str(source.get("name"), source.get("url"), "cyclonedx") or "cyclonedx",
                    "evidence_ref": ref or vid,
                    "dependency_paths": _component_path_strings(paths.get(ref, []), ref_to_id),
                }
            )
    return vulnerabilities


def _parse_cyclonedx(parsed: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    components, ref_to_id, graph, root_refs = _cyclonedx_components(parsed)
    paths = _paths_from_graph(root_refs, graph)
    refs_by_component: dict[str, list[str]] = {}
    for ref, cid in ref_to_id.items():
        refs_by_component.setdefault(cid, []).append(ref)
    for cid, refs in refs_by_component.items():
        if cid not in components:
            continue
        if components[cid].get("scope") == "root":
            continue
        scope = "unknown"
        selected_paths: list[list[str]] = []
        for ref in refs:
            candidate_scope = _scope_for(ref, root_refs, graph, paths)
            if candidate_scope == "direct":
                scope = "direct"
                selected_paths = paths.get(ref, selected_paths)
                break
            if candidate_scope == "transitive" and scope == "unknown":
                scope = "transitive"
                selected_paths = paths.get(ref, selected_paths)
        components[cid]["scope"] = scope
        components[cid]["dependency_paths"] = _component_path_strings(selected_paths, ref_to_id)
    vulnerabilities = _cyclonedx_vulnerabilities(parsed, ref_to_id, paths)
    return list(components.values()), vulnerabilities


def _spdx_package_id(package: dict[str, Any]) -> str:
    for ref in _as_list(package.get("externalRefs")):
        if isinstance(ref, dict) and str(ref.get("referenceType", "")).lower() == "purl":
            return _bounded_text(ref.get("referenceLocator"))
    name = _first_str(package.get("name"), package.get("SPDXID"))
    version = _first_str(package.get("versionInfo"))
    return _component_id(purl="", name=name, version=version, fallback=_first_str(package.get("SPDXID"), name))


def _spdx_security_refs(package: dict[str, Any]) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    for ref in _as_list(package.get("externalRefs")):
        if not isinstance(ref, dict):
            continue
        category = _first_str(ref.get("referenceCategory")).upper()
        rtype = _first_str(ref.get("referenceType"))
        locator = _first_str(ref.get("referenceLocator"))
        comment = _first_str(ref.get("comment"))
        if category == "SECURITY" and locator:
            refs.append({"type": rtype, "locator": locator, "comment": comment})
    return refs


def _parse_spdx(parsed: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    sbom = parsed.get("sbom") if isinstance(parsed.get("sbom"), dict) else parsed
    packages = [pkg for pkg in _as_list(sbom.get("packages")) if isinstance(pkg, dict)]
    spdx_to_id: dict[str, str] = {}
    components: dict[str, dict[str, Any]] = {}
    for package in packages:
        spdx_id = _first_str(package.get("SPDXID"))
        cid = _spdx_package_id(package)
        spdx_to_id[spdx_id] = cid
        purl = cid if cid.startswith("pkg:") else ""
        components[cid] = {
            "id": cid,
            "name": _first_str(package.get("name"), spdx_id),
            "version": _first_str(package.get("versionInfo")),
            "ecosystem": _purl_ecosystem(purl),
            "scope": "unknown",
            "licenses": _license_values([package.get("licenseConcluded"), package.get("licenseDeclared")]),
            "manifest": "",
            "dependency_paths": [],
        }
    graph: dict[str, list[str]] = {}
    root_refs: list[str] = []
    for rel in _as_list(sbom.get("relationships")):
        if not isinstance(rel, dict):
            continue
        rel_type = _first_str(rel.get("relationshipType")).upper()
        source = _first_str(rel.get("spdxElementId"))
        target = _first_str(rel.get("relatedSpdxElement"))
        if rel_type == "DESCRIBES" and target:
            root_refs.append(target)
        if rel_type == "DEPENDS_ON" and source and target:
            graph.setdefault(source, []).append(target)
        elif (rel_type == "DEPENDENCY_OF" or rel_type.endswith("_DEPENDENCY_OF")) and source and target:
            graph.setdefault(target, []).append(source)
    if not root_refs and graph:
        depended = {child for children in graph.values() for child in children}
        root_refs = [ref for ref in graph if ref not in depended][:1]
    paths = _paths_from_graph(root_refs, graph)
    for spdx_id, cid in spdx_to_id.items():
        if cid not in components:
            continue
        if spdx_id in root_refs:
            components[cid]["scope"] = "root"
            components[cid]["dependency_paths"] = [[cid]]
        else:
            components[cid]["scope"] = _scope_for(spdx_id, root_refs, graph, paths)
            components[cid]["dependency_paths"] = _component_path_strings(paths.get(spdx_id, []), spdx_to_id)
    vulnerabilities: list[dict[str, Any]] = []
    for package in packages:
        cid = spdx_to_id.get(_first_str(package.get("SPDXID")), "")
        for sec_ref in _spdx_security_refs(package):
            vulnerability_id = sec_ref["locator"].rsplit("/", 1)[-1] if sec_ref["locator"].startswith("http") else sec_ref["locator"]
            severity = "Unknown"
            match = re.search(r"severity\s*[:=]\s*(critical|high|medium|low|informational)", sec_ref.get("comment", ""), re.IGNORECASE)
            if match:
                severity = match.group(1).title()
            fixed_version = ""
            fixed_match = re.search(r"fixed(?:_| |-)version\s*[:=]\s*([A-Za-z0-9_.:+~-]+)", sec_ref.get("comment", ""), re.IGNORECASE)
            if fixed_match:
                fixed_version = fixed_match.group(1)
            vulnerabilities.append(
                {
                    "id": vulnerability_id,
                    "component": cid,
                    "severity": severity,
                    "fixed_version": fixed_version,
                    "source": sec_ref.get("type") or "spdx",
                    "evidence_ref": sec_ref["locator"],
                    "dependency_paths": components.get(cid, {}).get("dependency_paths", []),
                }
            )
    return list(components.values()), vulnerabilities


def _parse_syft(parsed: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    components: dict[str, dict[str, Any]] = {}
    syft_to_id: dict[str, str] = {}
    graph: dict[str, list[str]] = {}
    for artifact in _as_list(parsed.get("artifacts")):
        if not isinstance(artifact, dict):
            continue
        name = _first_str(artifact.get("name"))
        version = _first_str(artifact.get("version"))
        purl = _first_str(artifact.get("purl"))
        artifact_id = _first_str(artifact.get("id"), purl, name)
        locations = artifact.get("locations") if isinstance(artifact.get("locations"), list) else []
        manifest = ""
        if locations and isinstance(locations[0], dict):
            manifest = _first_str(locations[0].get("path"))
        cid = _component_id(purl=purl, name=name, version=version, fallback=artifact_id)
        syft_to_id[artifact_id] = cid
        components[cid] = {
            "id": cid,
            "name": name,
            "version": version,
            "ecosystem": _purl_ecosystem(purl),
            "scope": "unknown",
            "licenses": _license_values(artifact.get("licenses")),
            "manifest": manifest,
            "dependency_paths": [],
        }
    for rel in _as_list(parsed.get("artifactRelationships")):
        if isinstance(rel, dict) and _first_str(rel.get("type")).lower() in {"depends-on", "dependency-of"}:
            rel_type = _first_str(rel.get("type")).lower()
            parent = _first_str(rel.get("parent"), rel.get("from"))
            child = _first_str(rel.get("child"), rel.get("to"))
            if parent and child and rel_type == "depends-on":
                graph.setdefault(parent, []).append(child)
            elif parent and child and rel_type == "dependency-of":
                graph.setdefault(child, []).append(parent)
    depended = {child for children in graph.values() for child in children}
    root_refs = [ref for ref in graph if ref not in depended][:1]
    paths = _paths_from_graph(root_refs, graph)
    for ref, cid in syft_to_id.items():
        components[cid]["scope"] = _scope_for(ref, root_refs, graph, paths)
        components[cid]["dependency_paths"] = _component_path_strings(paths.get(ref, []), syft_to_id)
    return list(components.values()), []


def _normalize_components(components: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    seen: set[str] = set()
    for component in components:
        cid = _bounded_text(component.get("id"))
        if not cid or cid in seen:
            continue
        seen.add(cid)
        scope = _bounded_text(component.get("scope")) or "unknown"
        if scope not in {"root", "direct", "transitive", "unknown"}:
            scope = "unknown"
        normalized.append(
            {
                "id": cid,
                "name": _bounded_text(component.get("name")),
                "version": _bounded_text(component.get("version")),
                "ecosystem": _bounded_text(component.get("ecosystem")) or "unknown",
                "scope": scope,
                "licenses": sorted({_bounded_text(value) for value in _as_list(component.get("licenses")) if _bounded_text(value)}),
                "manifest": _bounded_text(component.get("manifest")),
                "dependency_paths": [
                    [_bounded_text(part) for part in path if _bounded_text(part)]
                    for path in _as_list(component.get("dependency_paths"))
                    if isinstance(path, list)
                ][:MAX_PATHS_PER_COMPONENT],
            }
        )
    return sorted(normalized, key=lambda item: (item["scope"] != "root", item["ecosystem"], item["name"], item["version"]))


def _normalize_vulnerabilities(vulnerabilities: list[dict[str, Any]], component_ids: set[str]) -> list[dict[str, Any]]:
    normalized = []
    seen: set[tuple[str, str]] = set()
    for vuln in vulnerabilities:
        vid = _bounded_text(vuln.get("id"))
        component = _bounded_text(vuln.get("component"))
        if not vid:
            continue
        if component and component not in component_ids:
            component = ""
        key = (vid, component)
        if key in seen:
            continue
        seen.add(key)
        severity = _bounded_text(vuln.get("severity")).title() or "Unknown"
        if severity not in SEVERITY_ORDER:
            severity = "Unknown"
        normalized.append(
            {
                "id": vid,
                "component": component,
                "severity": severity,
                "fixed_version": _bounded_text(vuln.get("fixed_version")),
                "source": _bounded_text(vuln.get("source")) or "unknown",
                "evidence_ref": _bounded_text(vuln.get("evidence_ref")),
                "dependency_paths": [
                    [_bounded_text(part) for part in path if _bounded_text(part)]
                    for path in _as_list(vuln.get("dependency_paths"))
                    if isinstance(path, list)
                ][:MAX_PATHS_PER_COMPONENT],
            }
        )
    return sorted(normalized, key=lambda item: (SEVERITY_ORDER.get(item["severity"], 9), item["id"], item["component"]))


def analyze_dependencies(*, run_dir: Path, raw_path: Path, raw_result_ref: str, tool: str, requested_format: str) -> dict[str, Any]:
    ctx = load_context(run_dir)
    parse_error = ""
    parsed: Any = {}
    try:
        parsed, _ = _load_sbom(raw_path)
    except Exception as exc:  # noqa: BLE001 - dependency artifact should record bad local input safely
        parse_error = _bounded_text(exc)
    detected_format = _detect_format(parsed, requested_format) if not parse_error else "invalid"
    components: list[dict[str, Any]] = []
    vulnerabilities: list[dict[str, Any]] = []
    try:
        if detected_format == "cyclonedx":
            components, vulnerabilities = _parse_cyclonedx(parsed)
        elif detected_format in {"spdx", "github-spdx"}:
            components, vulnerabilities = _parse_spdx(parsed)
        elif detected_format == "syft":
            components, vulnerabilities = _parse_syft(parsed)
    except Exception as exc:  # noqa: BLE001 - keep ingestion deterministic for untrusted SBOM shapes
        parse_error = _bounded_text(exc)
        components = []
        vulnerabilities = []
    normalized_components = _normalize_components(components)
    component_ids = {component["id"] for component in normalized_components}
    normalized_vulns = _normalize_vulnerabilities(vulnerabilities, component_ids)
    direct_count = sum(1 for component in normalized_components if component.get("scope") == "direct")
    transitive_count = sum(1 for component in normalized_components if component.get("scope") == "transitive")
    unknown_count = sum(1 for component in normalized_components if component.get("scope") == "unknown")
    if parse_error:
        status = "invalid"
        summary = "SBOM/dependency input could not be parsed into the normalized dependency model."
    elif normalized_vulns:
        status = "vulnerabilities_observed"
        summary = f"{len(normalized_vulns)} vulnerability record(s) were present in the SBOM/dependency input. Treat them as dependency evidence until reachability is confirmed."
    elif normalized_components:
        status = "inventory_observed"
        summary = f"{len(normalized_components)} dependency component(s) were normalized."
    else:
        status = "no_components"
        summary = "No dependency components were found in the SBOM/dependency input."
    return {
        "schema_version": "1",
        "run_id": ctx.get("run_id", run_dir.name),
        "repo": ctx.get("repo", ""),
        "branch": ctx.get("branch", ""),
        "commit": ctx.get("commit", ""),
        "generated_at": utc_now(),
        "status": status,
        "summary": summary,
        "source": {
            "tool": tool,
            "format": requested_format,
            "detected_format": detected_format,
            "raw_result_ref": raw_result_ref,
        },
        "component_count": len(normalized_components),
        "vulnerability_count": len(normalized_vulns),
        "scope_counts": {
            "direct": direct_count,
            "transitive": transitive_count,
            "unknown": unknown_count,
            "root": sum(1 for component in normalized_components if component.get("scope") == "root"),
        },
        "parse_error": parse_error,
        "components": normalized_components,
        "vulnerabilities": normalized_vulns,
        "references": REFERENCES,
    }


def render_dependency_markdown(data: dict[str, Any]) -> str:
    lines = [
        "# Dependency risk posture",
        "",
        f"Repository: `{_markdown_text(data.get('repo', ''))}`",
        f"Run ID: `{_markdown_text(data.get('run_id', ''))}`",
        f"Commit: `{_markdown_text(data.get('commit', ''))}`",
        f"Status: `{_markdown_text(data.get('status', ''))}`",
        "",
        _markdown_text(data.get("summary", "")),
        "",
        "SBOM and dependency graph input is evidence, not automatically confirmed repository findings.",
        "Vulnerabilities should be promoted only after manifest context, dependency paths, and reachability are reviewed.",
        "",
        "## Source",
        "",
    ]
    source = data.get("source") or {}
    lines.extend(
        [
            f"- Raw local artifact: `{_markdown_text(source.get('raw_result_ref', ''))}`",
            f"- Requested format: `{_markdown_text(source.get('format', ''))}`",
            f"- Detected format: `{_markdown_text(source.get('detected_format', ''))}`",
            f"- Tool: `{_markdown_text(source.get('tool', ''))}`",
            "",
        ]
    )
    if data.get("parse_error"):
        lines.extend(["## Parse error", "", _markdown_text(data.get("parse_error")), ""])
    lines.extend(
        [
            "## Summary counts",
            "",
            f"- Components: `{data.get('component_count', 0)}`",
            f"- Vulnerabilities: `{data.get('vulnerability_count', 0)}`",
        ]
    )
    scope_counts = data.get("scope_counts") if isinstance(data.get("scope_counts"), dict) else {}
    for scope in ["root", "direct", "transitive", "unknown"]:
        lines.append(f"- {scope.title()} components: `{scope_counts.get(scope, 0)}`")
    lines.extend(["", "## Vulnerable components", ""])
    vulnerabilities = [v for v in _as_list(data.get("vulnerabilities")) if isinstance(v, dict)]
    if not vulnerabilities:
        lines.append("No vulnerability records were present in the normalized dependency data.")
        lines.append("")
    for vuln in vulnerabilities:
        paths = vuln.get("dependency_paths") or []
        path_text = "; ".join(" -> ".join(_markdown_text(part) for part in path) for path in paths if isinstance(path, list)) or "not provided"
        lines.extend(
            [
                f"### `{_markdown_text(vuln.get('id', ''))}`",
                "",
                f"- Component: `{_markdown_text(vuln.get('component', ''))}`",
                f"- Severity: `{_markdown_text(vuln.get('severity', 'Unknown'))}`",
                f"- Fixed version: `{_markdown_text(vuln.get('fixed_version') or 'not provided')}`",
                f"- Source: `{_markdown_text(vuln.get('source') or 'unknown')}`",
                f"- Evidence reference: `{_markdown_text(vuln.get('evidence_ref') or '')}`",
                f"- Dependency paths: {path_text}",
                "",
            ]
        )
    lines.extend(["## Component inventory", ""])
    components = [c for c in _as_list(data.get("components")) if isinstance(c, dict)]
    if not components:
        lines.append("No components were normalized.")
        lines.append("")
    for component in components[:50]:
        lines.append(
            f"- `{_markdown_text(component.get('id', ''))}` "
            f"scope=`{_markdown_text(component.get('scope', 'unknown'))}` "
            f"license=`{_markdown_text(', '.join(component.get('licenses') or []) or 'unknown')}` "
            f"manifest=`{_markdown_text(component.get('manifest') or 'unknown')}`"
        )
    if len(components) > 50:
        lines.append(f"- ... {len(components) - 50} additional component(s) omitted from Markdown summary.")
    lines.extend(
        [
            "",
            "## References",
            "",
            "- GitHub Dependency Graph SBOM export: https://docs.github.com/en/rest/dependency-graph/sboms",
            "- CycloneDX specification overview: https://cyclonedx.org/specification/overview/",
            "- SPDX 2.3 package information: https://spdx.github.io/spdx-spec/v2.3/package-information/",
            "- SPDX 2.3 relationships: https://spdx.github.io/spdx-spec/v2.3/relationships-between-SPDX-elements/",
            "",
        ]
    )
    return "\n".join(lines)


def write_dependency_artifacts(*, run_dir: Path, raw_path: Path, raw_result_ref: str, tool: str, requested_format: str) -> dict[str, Any]:
    reports = _reports_dir(run_dir)
    reports.mkdir(parents=True, exist_ok=True)
    data = analyze_dependencies(run_dir=run_dir, raw_path=raw_path, raw_result_ref=raw_result_ref, tool=tool, requested_format=requested_format)
    write_json(reports / "dependencies.json", data)
    (reports / "DEPENDENCY_RISK.md").write_text(render_dependency_markdown(data), encoding="utf-8")
    return data


def should_ingest_dependencies(*, safe_tool: str, fmt: str) -> bool:
    return safe_tool in {
        "sbom",
        "dependency-graph",
        "dependencies",
        "github-sbom",
        "github-dependency-graph",
        "cyclonedx",
        "spdx",
        "syft",
    } or fmt.lower() in {"cyclonedx", "cyclonedx-json", "spdx", "github-spdx", "github-dependency-graph", "syft", "syft-json"}
