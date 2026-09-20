"""Configuration loading and path resolution.

Scope 6.5 requires that no path, threshold, or weight be hard-coded. Everything
comes from config/*.yaml and config/weights.json, and any path may be overridden
by a DSG_-prefixed environment variable.

Pure Python - no arcpy - so it is importable in CI.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


def repo_root() -> Path:
    """Repository root, resolved from this file's location (src/li/config.py)."""
    return Path(__file__).resolve().parents[2]


def config_dir() -> Path:
    return repo_root() / "config"


@lru_cache(maxsize=None)
def load_yaml(name: str) -> dict[str, Any]:
    """Load config/<name>.yaml (the .yaml suffix is optional)."""
    path = Path(name)
    if not path.is_absolute():
        if not path.suffix:
            path = path.with_suffix(".yaml")
        path = config_dir() / path
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


@lru_cache(maxsize=None)
def load_json(name: str) -> dict[str, Any]:
    path = Path(name)
    if not path.is_absolute():
        if not path.suffix:
            path = path.with_suffix(".json")
        path = config_dir() / path
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def paths() -> dict[str, str]:
    """Resolved filesystem paths.

    Precedence: DSG_<KEY> environment variable, then config/paths.yaml.
    Repo-relative values are made absolute against the repository root.
    """
    cfg = dict(load_yaml("paths"))
    root = repo_root()
    resolved: dict[str, str] = {}
    for key, value in cfg.items():
        override = os.environ.get(f"DSG_{key.upper()}")
        raw = override if override else value
        p = Path(raw)
        resolved[key] = str(p if p.is_absolute() else (root / p))
    return resolved


def schema() -> dict[str, Any]:
    return load_yaml("schema")


def screening() -> dict[str, Any]:
    return load_yaml("screening")


def criteria() -> dict[str, Any]:
    return load_yaml("criteria")


def network() -> dict[str, Any]:
    return load_yaml("network")


def sources() -> dict[str, Any]:
    return load_yaml("sources")


def weights(scenario: str | None = None) -> dict[str, Any]:
    """All weight scenarios, or one scenario's criterion weights.

    Keys beginning with an underscore are documentation, not scenarios.
    """
    data = {k: v for k, v in load_json("weights").items() if not k.startswith("_")}
    if scenario is None:
        return data
    if scenario not in data:
        raise KeyError(f"Unknown scenario '{scenario}'. Known: {sorted(data)}")
    return data[scenario]


def scenarios() -> list[str]:
    return sorted(weights().keys())


def validate_weights(tolerance: float = 1e-9) -> dict[str, float]:
    """Assert every scenario's weights sum to 1.00 (scope Section 10).

    Returns the per-scenario sums so a caller can log them.
    """
    sums: dict[str, float] = {}
    bad: list[str] = []
    for name, w in weights().items():
        total = float(sum(w.values()))
        sums[name] = total
        if abs(total - 1.0) > tolerance:
            bad.append(f"{name}={total:.6f}")
    if bad:
        raise ValueError("Weight scenarios must sum to 1.00; got " + ", ".join(bad))
    return sums
