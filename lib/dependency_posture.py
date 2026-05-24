from __future__ import annotations

import json
import re
from collections import deque
from pathlib import Path
from typing import Any

from gralib import load_context, load_json, load_targets, utc_now, write_json, write_targets
from scanner_normalize import redact_text

MAX_PATHS_PER_COMPONENT = 5
MAX_PATH_DEPTH = 12
MAX_TEXT_CHARS = 500
MAX_TARGETS = 20
MAX_NOTE_CHARS = 500
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


def _safe_tool_name(tool: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in str(tool).lower())


def _dependency_scanner_format(parsed: Any, *, tool: str, requested_format: str, detected_format: str) -> str:
    safe_tool = _safe_tool_name(tool)
    requested = (requested_format or "").lower()
    if detected_format in {"cyclonedx", "spdx", "github-spdx", "syft"}:
        return detected_format
    if safe_tool == "trivy" or requested in {"trivy", "trivy-json"}:
        if isinstance(parsed, dict) and isinstance(parsed.get("Results"), list):
            return "trivy"
    if safe_tool == "grype" or requested in {"grype", "grype-json"}:
        if isinstance(parsed, dict) and isinstance(parsed.get("matches"), list):
            return "grype"
    return detected_format


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


def _purl_name_version(purl: str) -> tuple[str, str]:
    if not purl.startswith("pkg:"):
        return "", ""
    body = purl.split("?", 1)[0].split("#", 1)[0]
    if "@" not in body:
        return body.rsplit("/", 1)[-1], ""
    before_version, version = body.rsplit("@", 1)
    return before_version.rsplit("/", 1)[-1], version


def _scanner_ecosystem(value: str) -> str:
    token = value.lower()
    mapping = {
        "python": "pypi",
        "python-pkg": "pypi",
        "pip": "pypi",
        "npm": "npm",
        "node": "npm",
        "node-pkg": "npm",
        "yarn": "npm",
        "pnpm": "npm",
        "gem": "gem",
        "ruby": "gem",
        "go": "golang",
        "gomod": "golang",
        "go-module": "golang",
        "gobinary": "golang",
        "jar": "maven",
        "maven": "maven",
        "java": "maven",
        "composer": "composer",
        "php": "composer",
        "cargo": "cargo",
        "rust": "cargo",
        "nuget": "nuget",
        "dotnet": "nuget",
        "deb": "deb",
        "debian": "deb",
        "ubuntu": "deb",
        "rpm": "rpm",
        "redhat": "rpm",
        "centos": "rpm",
        "alpine": "apk",
        "apk": "apk",
    }
    return mapping.get(token, token or "unknown")


def _scanner_component_id(*, purl: str, name: str, version: str, ecosystem: str, fallback: str) -> str:
    if purl:
        return purl
    if name and version and ecosystem and ecosystem != "unknown":
        return f"pkg:{ecosystem}/{name}@{version}"
    return _component_id(purl="", name=name, version=version, fallback=fallback)


def _component_lookup(components: list[dict[str, Any]]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for component in components:
        if not isinstance(component, dict):
            continue
        cid = _bounded_text(component.get("id"))
        name = _bounded_text(component.get("name")).lower()
        version = _bounded_text(component.get("version"))
        ecosystem = _bounded_text(component.get("ecosystem")).lower()
        if cid:
            lookup[f"id:{cid}"] = cid
        if name and version and ecosystem:
            lookup[f"name-version-ecosystem:{name}@{version}:{ecosystem}"] = cid
        if name and version:
            lookup[f"name-version:{name}@{version}"] = cid
    return lookup


def _resolve_component_id(
    *,
    lookup: dict[str, str],
    purl: str,
    name: str,
    version: str,
    ecosystem: str,
) -> str:
    candidates = []
    if purl:
        candidates.append(f"id:{purl}")
    if name and version and ecosystem:
        candidates.append(f"name-version-ecosystem:{name.lower()}@{version}:{ecosystem.lower()}")
    if name and version:
        candidates.append(f"name-version:{name.lower()}@{version}")
    for candidate in candidates:
        if candidate in lookup:
            return lookup[candidate]
    return ""


def _component_by_id(components: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        str(component.get("id")): component
        for component in components
        if isinstance(component, dict) and component.get("id")
    }


def _scanner_component(
    *,
    component_id: str,
    name: str,
    version: str,
    ecosystem: str,
    manifest: str,
    purl: str,
    existing_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    if not component_id:
        return None
    existing = existing_by_id.get(component_id)
    if existing:
        return dict(existing)
    purl_name, purl_version = _purl_name_version(purl)
    ecosystem_value = ecosystem if ecosystem and ecosystem != "unknown" else _purl_ecosystem(purl)
    return {
        "id": component_id,
        "name": name or purl_name or component_id,
        "version": version or purl_version,
        "ecosystem": ecosystem_value,
        "scope": "unknown",
        "licenses": [],
        "manifest": manifest,
        "dependency_paths": [],
    }


def _parse_trivy(parsed: dict[str, Any], existing_components: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    lookup = _component_lookup(existing_components)
    existing_by_id = _component_by_id(existing_components)
    components: dict[str, dict[str, Any]] = {}
    vulnerabilities: list[dict[str, Any]] = []
    for result in _as_list(parsed.get("Results")):
        if not isinstance(result, dict):
            continue
        result_type = _first_str(result.get("Type"))
        ecosystem = _scanner_ecosystem(result_type)
        manifest = _first_str(result.get("Target"))
        for vuln in _as_list(result.get("Vulnerabilities")):
            if not isinstance(vuln, dict):
                continue
            vid = _first_str(vuln.get("VulnerabilityID"), vuln.get("VulnerabilityId"), vuln.get("ID"))
            if not vid:
                continue
            identifier = vuln.get("PkgIdentifier") if isinstance(vuln.get("PkgIdentifier"), dict) else {}
            purl = _first_str(identifier.get("PURL"), vuln.get("PURL"))
            name = _first_str(vuln.get("PkgName"), vuln.get("PkgID"))
            version = _first_str(vuln.get("InstalledVersion"))
            if purl:
                purl_name, purl_version = _purl_name_version(purl)
                name = name or purl_name
                version = version or purl_version
            component_id = _resolve_component_id(lookup=lookup, purl=purl, name=name, version=version, ecosystem=ecosystem)
            if not component_id and (purl or (name and version)):
                component_id = _scanner_component_id(
                    purl=purl,
                    name=name,
                    version=version,
                    ecosystem=ecosystem,
                    fallback=_first_str(vuln.get("PkgID"), vid),
                )
            component = _scanner_component(
                component_id=component_id,
                name=name,
                version=version,
                ecosystem=ecosystem,
                manifest=manifest,
                purl=purl,
                existing_by_id=existing_by_id,
            )
            if component:
                components[component["id"]] = component
            vulnerabilities.append(
                {
                    "id": vid,
                    "component": component_id if component else "",
                    "severity": _first_str(vuln.get("Severity")).title() or "Unknown",
                    "fixed_version": _first_str(vuln.get("FixedVersion")),
                    "source": "trivy",
                    "evidence_ref": _first_str(vuln.get("PrimaryURL"), vuln.get("PkgID"), vid),
                    "dependency_paths": component.get("dependency_paths", []) if component else [],
                }
            )
    return list(components.values()), vulnerabilities


def _parse_grype(parsed: dict[str, Any], existing_components: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    lookup = _component_lookup(existing_components)
    existing_by_id = _component_by_id(existing_components)
    components: dict[str, dict[str, Any]] = {}
    vulnerabilities: list[dict[str, Any]] = []
    for match in _as_list(parsed.get("matches")):
        if not isinstance(match, dict):
            continue
        vuln = match.get("vulnerability") if isinstance(match.get("vulnerability"), dict) else {}
        artifact = match.get("artifact") if isinstance(match.get("artifact"), dict) else {}
        vid = _first_str(vuln.get("id"))
        if not vid:
            continue
        purl = _first_str(artifact.get("purl"))
        name = _first_str(artifact.get("name"))
        version = _first_str(artifact.get("version"))
        ecosystem = _scanner_ecosystem(_first_str(artifact.get("type")))
        if purl:
            purl_name, purl_version = _purl_name_version(purl)
            name = name or purl_name
            version = version or purl_version
            ecosystem = _purl_ecosystem(purl) or ecosystem
        locations = [location for location in _as_list(artifact.get("locations")) if isinstance(location, dict)]
        manifest = _first_str(locations[0].get("path") if locations else "")
        component_id = _resolve_component_id(lookup=lookup, purl=purl, name=name, version=version, ecosystem=ecosystem)
        if not component_id and (purl or (name and version)):
            component_id = _scanner_component_id(
                purl=purl,
                name=name,
                version=version,
                ecosystem=ecosystem,
                fallback=_first_str(artifact.get("id"), vid),
            )
        component = _scanner_component(
            component_id=component_id,
            name=name,
            version=version,
            ecosystem=ecosystem,
            manifest=manifest,
            purl=purl,
            existing_by_id=existing_by_id,
        )
        if component:
            components[component["id"]] = component
        fix = vuln.get("fix") if isinstance(vuln.get("fix"), dict) else {}
        fixed_versions = [_bounded_text(version) for version in _as_list(fix.get("versions")) if _bounded_text(version)]
        vulnerabilities.append(
            {
                "id": vid,
                "component": component_id if component else "",
                "severity": _first_str(vuln.get("severity")).title() or "Unknown",
                "fixed_version": ", ".join(fixed_versions),
                "source": "grype",
                "evidence_ref": _first_str(vuln.get("dataSource"), artifact.get("id"), vid),
                "dependency_paths": component.get("dependency_paths", []) if component else [],
            }
        )
    return list(components.values()), vulnerabilities


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
        # Partial SBOMs may include vulnerability evidence for components that
        # are omitted from the inventory. Preserve the evidence_ref but do not
        # emit a dangling component id that would fail downstream validation.
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


def analyze_dependencies(
    *,
    run_dir: Path,
    raw_path: Path,
    raw_result_ref: str,
    tool: str,
    requested_format: str,
    existing_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ctx = load_context(run_dir)
    parse_error = ""
    parsed: Any = {}
    try:
        parsed, _ = _load_sbom(raw_path)
    except Exception as exc:  # noqa: BLE001 - dependency artifact should record bad local input safely
        parse_error = _bounded_text(exc)
    detected_format = _detect_format(parsed, requested_format) if not parse_error else "invalid"
    if not parse_error:
        detected_format = _dependency_scanner_format(
            parsed,
            tool=tool,
            requested_format=requested_format,
            detected_format=detected_format,
        )
    if not isinstance(existing_data, dict):
        existing_data = {}
    existing_components = [
        component
        for component in (existing_data or {}).get("components", [])
        if isinstance(component, dict)
    ]
    existing_vulnerabilities = [
        vulnerability
        for vulnerability in (existing_data or {}).get("vulnerabilities", [])
        if isinstance(vulnerability, dict)
    ]
    merge_existing = detected_format in {"trivy", "grype"} and bool(existing_components or existing_vulnerabilities)
    components: list[dict[str, Any]] = []
    vulnerabilities: list[dict[str, Any]] = []
    try:
        if detected_format == "cyclonedx":
            components, vulnerabilities = _parse_cyclonedx(parsed)
        elif detected_format in {"spdx", "github-spdx"}:
            components, vulnerabilities = _parse_spdx(parsed)
        elif detected_format == "syft":
            components, vulnerabilities = _parse_syft(parsed)
        elif detected_format == "trivy":
            components, vulnerabilities = _parse_trivy(parsed, existing_components)
        elif detected_format == "grype":
            components, vulnerabilities = _parse_grype(parsed, existing_components)
    except Exception as exc:  # noqa: BLE001 - keep ingestion deterministic for untrusted SBOM shapes
        parse_error = _bounded_text(exc)
        components = []
        vulnerabilities = []
    if merge_existing:
        components = [*existing_components, *components]
        vulnerabilities = [*existing_vulnerabilities, *vulnerabilities]
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
    existing_data = load_json(reports / "dependencies.json", {}) or {}
    if not isinstance(existing_data, dict):
        existing_data = {}
    data = analyze_dependencies(
        run_dir=run_dir,
        raw_path=raw_path,
        raw_result_ref=raw_result_ref,
        tool=tool,
        requested_format=requested_format,
        existing_data=existing_data,
    )
    write_json(reports / "dependencies.json", data)
    (reports / "DEPENDENCY_RISK.md").write_text(render_dependency_markdown(data), encoding="utf-8")
    return data


def _target_id(index: int) -> str:
    return f"TGT-DEPENDENCY-{index:03d}"


def _dependency_target_risk(severity: str) -> str:
    return "critical" if severity == "Critical" else "high"


def _dependency_target_priority(severity: str, scope: str) -> int:
    if severity == "Critical" and scope == "direct":
        return 95
    if severity == "High" and scope == "direct":
        return 85
    if severity == "Critical":
        return 80
    return 70


def _dependency_target_scope(vulnerability: dict[str, Any]) -> str:
    return f"Dependency vulnerability: {vulnerability.get('id', '')} on {vulnerability.get('component', '')}"


def _dependency_target_note(vulnerability: dict[str, Any], component: dict[str, Any]) -> str:
    paths = vulnerability.get("dependency_paths") if isinstance(vulnerability.get("dependency_paths"), list) else []
    path_text = "; ".join(" -> ".join(str(part) for part in path) for path in paths if isinstance(path, list))
    pieces = [
        "Generated from reports/dependencies.json.",
        f"Dependency vulnerability evidence: {vulnerability.get('id', '')}.",
        f"Component: {component.get('name') or vulnerability.get('component', '')} {component.get('version') or ''}.",
        f"Scope: {component.get('scope') or 'unknown'}.",
        f"Severity: {vulnerability.get('severity') or 'Unknown'}.",
        f"Fixed version: {vulnerability.get('fixed_version') or 'not provided'}.",
        f"Source: {vulnerability.get('source') or 'unknown'}.",
        f"Dependency paths: {path_text or 'not provided'}.",
        "Treat this as dependency evidence until manifest context and reachability are reviewed.",
    ]
    note = " ".join(piece for piece in pieces if piece)
    if len(note) <= MAX_NOTE_CHARS:
        return note
    suffix = "...<truncated>"
    prefix_length = max(0, MAX_NOTE_CHARS - len(suffix))
    return (note[:prefix_length] + suffix)[:MAX_NOTE_CHARS]


def _dependency_targets_from_data(data: dict[str, Any]) -> list[dict[str, Any]]:
    components = {
        str(component.get("id")): component
        for component in data.get("components") or []
        if isinstance(component, dict) and component.get("id")
    }
    candidates: list[dict[str, Any]] = []
    for vulnerability in data.get("vulnerabilities") or []:
        if not isinstance(vulnerability, dict):
            continue
        severity = str(vulnerability.get("severity") or "Unknown")
        component_id = str(vulnerability.get("component") or "")
        component = components.get(component_id)
        paths = vulnerability.get("dependency_paths")
        if severity not in {"Critical", "High"} or not component or not isinstance(paths, list) or not paths:
            continue
        scope = str(component.get("scope") or "unknown")
        if scope not in {"direct", "transitive"}:
            continue
        if not any(isinstance(path, list) and path for path in paths):
            continue
        candidates.append({"vulnerability": vulnerability, "component": component})
    candidates.sort(
        key=lambda item: (
            SEVERITY_ORDER.get(str(item["vulnerability"].get("severity") or "Unknown"), 9),
            str(item["component"].get("scope") or "unknown") != "direct",
            str(item["vulnerability"].get("id") or ""),
            str(item["vulnerability"].get("component") or ""),
        )
    )
    targets: list[dict[str, Any]] = []
    for item in candidates[:MAX_TARGETS]:
        vulnerability = item["vulnerability"]
        component = item["component"]
        severity = str(vulnerability.get("severity") or "Unknown")
        component_id = str(vulnerability.get("component") or "")
        component_scope = str(component.get("scope") or "unknown")
        manifest = str(component.get("manifest") or "")
        dependency_paths = vulnerability.get("dependency_paths") or []
        first_path = next((path for path in dependency_paths if isinstance(path, list) and path), [])
        entry_points = [manifest] if manifest else [component_id]
        target = {
            "category": "Dependency Risk",
            "title": f"Review {severity} dependency vulnerability {vulnerability.get('id', '')}",
            "risk": _dependency_target_risk(severity),
            "priority": _dependency_target_priority(severity, component_scope),
            "status": "queued",
            "scope": _dependency_target_scope(vulnerability),
            "entry_points": entry_points,
            "trust_boundaries": ["upstream dependency package -> repository build or runtime"],
            "sinks": [component_id, str(component.get("ecosystem") or "unknown")],
            "security_invariants": [
                "Dependency posture records are evidence and must not be treated as confirmed findings without reachability review.",
                "Dependency remediation should preserve intended package constraints and release process controls.",
            ],
            "review_questions": [
                "Is the vulnerable dependency reachable from repository runtime, build, or deployment paths?",
                "Is the affected version constrained by a manifest or lockfile in this repository?",
                "Is the fixed version compatible with the repository's supported dependency range?",
                "Should this remain an informational dependency posture item or be promoted to a confirmed finding?",
            ],
            "candidate_files": [manifest] if manifest else [],
            "recommended_mode": "exec",
            "notes": _dependency_target_note(vulnerability, component),
            "taxonomies": [
                {"name": "Supply Chain Posture", "id": "SC-DEPENDENCY-UPDATE", "label": "Dependency Update Tooling"}
            ],
        }
        if first_path:
            target["review_questions"].append("Does the dependency path reflect a direct or transitive dependency used by the audited code path?")
        targets.append(target)
    return targets


def append_dependency_posture_targets(run_dir: Path) -> list[dict[str, Any]]:
    reports = _reports_dir(run_dir)
    data = load_json(reports / "dependencies.json", {}) or {}
    if not isinstance(data, dict):
        return []
    generated_targets = _dependency_targets_from_data(data)
    if not generated_targets:
        return []
    targets = load_targets(run_dir)
    existing_scopes = {str(target.get("scope")) for target in targets if isinstance(target, dict)}
    existing_ids = {str(target.get("id")) for target in targets if isinstance(target, dict)}
    next_index = 1
    added: list[dict[str, Any]] = []
    for target in generated_targets:
        scope = str(target.get("scope") or "")
        if not scope or scope in existing_scopes:
            continue
        while _target_id(next_index) in existing_ids:
            next_index += 1
        target["id"] = _target_id(next_index)
        targets.append(target)
        added.append(target)
        existing_ids.add(target["id"])
        existing_scopes.add(scope)
        next_index += 1
    if added:
        write_targets(run_dir, targets)
    return added


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
    } or fmt.lower() in {"cyclonedx", "cyclonedx-json", "spdx", "github-spdx", "github-dependency-graph", "syft", "syft-json"} or (
        safe_tool in {"trivy", "grype"} and fmt.lower() in {"json", "trivy", "trivy-json", "grype", "grype-json"}
    )
