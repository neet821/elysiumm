"""Resolve release impact from one versioned path-rule map."""

from __future__ import annotations

from dataclasses import dataclass
import fnmatch
import json
from pathlib import Path, PurePosixPath
import subprocess
from typing import Iterable, Mapping

import yaml


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


def load_impact_map(path: Path) -> tuple[int, tuple[ImpactRule, ...], ImpactRule]:
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
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
    result = {
        "impact_map_version": version,
        "impact_map": str(impact_map.resolve().relative_to(root)),
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
        ["git", "diff", "--name-only", "--diff-filter=ACMRTUXB", f"{base}...{head}"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return [line for line in completed.stdout.splitlines() if line]


def resolve_impact_json(payload: Mapping[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
