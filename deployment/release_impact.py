"""Resolve release impact from one versioned path-rule map."""

from __future__ import annotations

from dataclasses import dataclass
import fnmatch
import json
from pathlib import Path, PurePosixPath
import subprocess
from typing import Iterable, Mapping

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - exercised on minimal servers
    yaml = None


_COMPONENT_ORDER = ("frontend", "backend", "infra")


class ImpactMapError(ValueError):
    """The impact map or changed path list is invalid."""


@dataclass(frozen=True)
class ImpactRule:
    rule_id: str
    paths: tuple[str, ...]
    components: tuple[str, ...]
    validation: tuple[str, ...]

    def matches(self, changed_path: str) -> bool:
        return any(fnmatch.fnmatchcase(changed_path, pattern) for pattern in self.paths)


def _as_string_tuple(value: object, *, field: str, rule_id: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value or not all(isinstance(item, str) and item for item in value):
        raise ImpactMapError(f"{rule_id}.{field} must be a non-empty string list")
    return tuple(value)


def _inline_list(value: str, *, field: str) -> list[str]:
    value = value.strip()
    if not (value.startswith("[") and value.endswith("]")):
        raise ImpactMapError(f"{field} must use an inline YAML list")
    items = [item.strip().strip("'\"") for item in value[1:-1].split(",") if item.strip()]
    if not items or not all(items):
        raise ImpactMapError(f"{field} must be a non-empty string list")
    return items


def _minimal_yaml_load(text: str) -> dict[str, object]:
    """Parse this deliberately small impact-map shape without PyYAML.

    Production frontend-only deploys are allowed to use the host Python and
    must not depend on the backend virtualenv.  The checked-in map is limited
    to scalar version values, rule ids, and string lists, so a strict fallback
    is safer than silently treating a malformed map as empty.
    """

    document: dict[str, object] = {"rules": []}
    section = ""
    current: dict[str, object] | None = None
    list_field: str | None = None
    for line_number, raw in enumerate(text.splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()
        if indent == 0 and line == "rules:":
            section = "rules"
            current = None
            list_field = None
            continue
        if indent == 0 and line == "defaults:":
            section = "defaults"
            current = None
            list_field = None
            document["defaults"] = {}
            continue
        if section == "rules" and indent == 2 and line.startswith("- id:"):
            rule_id = line.split(":", 1)[1].strip().strip("'\"")
            if not rule_id:
                raise ImpactMapError(f"impact map line {line_number} has an empty rule id")
            current = {"id": rule_id}
            rules = document.setdefault("rules", [])
            if not isinstance(rules, list):
                raise ImpactMapError("impact map rules must be a list")
            rules.append(current)
            list_field = None
            continue
        if section == "rules" and indent == 4 and current is not None and line.endswith(":"):
            list_field = line[:-1]
            current[list_field] = []
            continue
        if section == "rules" and indent == 4 and current is not None and ":" in line:
            key, value = line.split(":", 1)
            current[key.strip()] = _inline_list(value, field=key.strip()) if value.strip().startswith("[") else value.strip().strip("'\"")
            list_field = None
            continue
        if section == "rules" and indent == 6 and line.startswith("-") and current is not None and list_field:
            values = current.get(list_field)
            if not isinstance(values, list):
                raise ImpactMapError(f"impact map line {line_number} has an invalid list")
            values.append(line[1:].strip().strip("'\""))
            continue
        if section == "defaults" and indent == 2 and ":" in line:
            key, value = line.split(":", 1)
            defaults = document["defaults"]
            if not isinstance(defaults, dict):
                raise ImpactMapError("impact map defaults must be a mapping")
            defaults[key.strip()] = _inline_list(value, field=f"defaults.{key.strip()}")
            continue
        if indent == 0 and line.startswith("version:"):
            try:
                document["version"] = int(line.split(":", 1)[1].strip())
            except ValueError as exc:
                raise ImpactMapError("impact map version must be an integer") from exc
            section = ""
            current = None
            list_field = None
            continue
        raise ImpactMapError(f"unsupported impact map syntax at line {line_number}")
    return document


def load_impact_map(path: Path) -> tuple[int, tuple[ImpactRule, ...], ImpactRule]:
    try:
        source = path.read_text(encoding="utf-8")
        document = yaml.safe_load(source) if yaml is not None else _minimal_yaml_load(source)
    except (OSError, UnicodeError, ValueError, ImpactMapError) as exc:
        raise ImpactMapError(f"cannot load impact map {path}: {exc}") from exc
    except Exception as exc:
        raise ImpactMapError(f"cannot load impact map {path}: {exc}") from exc
    if not isinstance(document, dict) or not isinstance(document.get("version"), int):
        raise ImpactMapError("impact map must contain an integer version")
    raw_rules = document.get("rules")
    if not isinstance(raw_rules, list) or not raw_rules:
        raise ImpactMapError("impact map must contain a non-empty rules list")
    rules: list[ImpactRule] = []
    seen_ids: set[str] = set()
    for raw_rule in raw_rules:
        if not isinstance(raw_rule, dict):
            raise ImpactMapError("each impact rule must be a mapping")
        rule_id = raw_rule.get("id")
        if not isinstance(rule_id, str) or not rule_id or rule_id in seen_ids:
            raise ImpactMapError(f"invalid or duplicate rule id: {rule_id!r}")
        seen_ids.add(rule_id)
        components = _as_string_tuple(raw_rule.get("components"), field="components", rule_id=rule_id)
        validation = _as_string_tuple(raw_rule.get("validation"), field="validation", rule_id=rule_id)
        unknown = set(components) - set(_COMPONENT_ORDER)
        if unknown:
            raise ImpactMapError(f"{rule_id}.components has unknown values: {sorted(unknown)}")
        rules.append(
            ImpactRule(
                rule_id=rule_id,
                paths=_as_string_tuple(raw_rule.get("paths"), field="paths", rule_id=rule_id),
                components=components,
                validation=validation,
            )
        )
    raw_defaults = document.get("defaults")
    if not isinstance(raw_defaults, dict):
        raise ImpactMapError("impact map must contain defaults")
    defaults = ImpactRule(
        rule_id="__defaults__",
        paths=(),
        components=_as_string_tuple(raw_defaults.get("components"), field="components", rule_id="defaults"),
        validation=_as_string_tuple(raw_defaults.get("validation"), field="validation", rule_id="defaults"),
    )
    unknown_defaults = set(defaults.components) - set(_COMPONENT_ORDER)
    if unknown_defaults:
        raise ImpactMapError(f"defaults.components has unknown values: {sorted(unknown_defaults)}")
    return document["version"], tuple(rules), defaults


def normalize_changed_path(path: str) -> str:
    if not isinstance(path, str) or not path or "\\" in path:
        raise ImpactMapError(f"invalid changed path: {path!r}")
    pure = PurePosixPath(path)
    if pure.is_absolute() or ".." in pure.parts or "." in pure.parts:
        raise ImpactMapError(f"changed path must be repository-relative: {path!r}")
    return pure.as_posix()


def resolve_impact(
    changed_paths: Iterable[str],
    *,
    impact_map: Path,
    root: Path | None = None,
) -> dict[str, object]:
    root = (root or impact_map.parent.parent).resolve()
    version, rules, defaults = load_impact_map(impact_map)
    normalized = sorted({normalize_changed_path(item) for item in changed_paths})
    components: set[str] = set()
    validation: set[str] = set()
    matched_rules: list[dict[str, object]] = []
    unmatched: list[str] = []
    for changed_path in normalized:
        matching = [rule for rule in rules if rule.matches(changed_path)]
        if not matching:
            unmatched.append(changed_path)
            matching = [defaults]
        for rule in matching:
            components.update(rule.components)
            validation.update(rule.validation)
            if rule.rule_id != "__defaults__" and rule.rule_id not in {item["id"] for item in matched_rules}:
                matched_rules.append(
                    {"id": rule.rule_id, "paths": list(rule.paths), "components": list(rule.components), "validation": list(rule.validation)}
                )
    if not normalized:
        components.update(defaults.components)
        validation.update(defaults.validation)
    resolved_map = impact_map.resolve()
    try:
        rendered_map = str(resolved_map.relative_to(root))
    except ValueError:
        # A production deploy may execute a versioned payload from a staging
        # directory while its durable root contains only the bare repository
        # and immutable releases.  Keep that provenance explicit instead of
        # manufacturing a relative path that cannot be resolved from root.
        rendered_map = str(resolved_map)
    result = {
        "impact_map_version": version,
        "impact_map": rendered_map,
        "components": [item for item in _COMPONENT_ORDER if item in components],
        "validation_profiles": sorted(validation),
        "matched_rules": matched_rules,
        "changed_paths": normalized,
        "unmatched_paths": unmatched,
        "requires_full_validation": bool(unmatched or "full" in validation),
    }
    return result


def changed_paths_from_git(root: Path, base: str, head: str) -> list[str]:
    completed = subprocess.run(
        # Keep deletions in the impact set.  A deleted unit/config still needs
        # an explicit production target so deployment cannot silently leave
        # the old file installed.
        ["git", "diff", "--name-only", "--diff-filter=ACDMRTUXB", f"{base}...{head}"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return [line for line in completed.stdout.splitlines() if line]


def resolve_impact_json(payload: Mapping[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
