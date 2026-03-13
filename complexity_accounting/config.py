"""
Configuration loading for complexity-accounting.

Precedence: CLI args > .complexity.toml > pyproject.toml [tool.complexity-accounting] > defaults
"""

from __future__ import annotations

import os
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Optional

try:
    import tomllib
except ModuleNotFoundError:
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ModuleNotFoundError:
        tomllib = None  # type: ignore[assignment]


@dataclass
class Config:
    # Risk level boundaries (cognitive complexity)
    risk_low: int = 5
    risk_moderate: int = 10
    risk_high: int = 20

    # Hotspot threshold
    hotspot_threshold: int = 10

    # NCS weights
    weight_cognitive: float = 0.7
    weight_cyclomatic: float = 0.3

    # Churn settings
    churn_days: int = 90
    churn_commits: int = 100


# Map of config file keys to Config field names (they match 1:1 with underscores replaced by hyphens)
_KEY_MAP = {
    "risk-low": "risk_low",
    "risk-moderate": "risk_moderate",
    "risk-high": "risk_high",
    "hotspot-threshold": "hotspot_threshold",
    "weight-cognitive": "weight_cognitive",
    "weight-cyclomatic": "weight_cyclomatic",
    "churn-days": "churn_days",
    "churn-commits": "churn_commits",
}


def _apply_dict(config: Config, data: dict) -> None:
    """Apply a dict of settings to a Config, accepting both hyphenated and underscored keys."""
    field_names = {f.name for f in fields(Config)}
    for key, value in data.items():
        field_name = _KEY_MAP.get(key, key.replace("-", "_"))
        if field_name in field_names:
            expected_type = Config.__dataclass_fields__[field_name].type
            if expected_type == "int":
                value = int(value)
            elif expected_type == "float":
                value = float(value)
            setattr(config, field_name, value)


def load_config(project_dir: Optional[str] = None) -> Config:
    """
    Load config from .complexity.toml or pyproject.toml [tool.complexity-accounting].

    Returns Config with defaults for any missing keys.
    """
    config = Config()
    if tomllib is None:
        return config

    if project_dir is None:
        project_dir = os.getcwd()

    root = Path(project_dir)

    # Try .complexity.toml first
    complexity_toml = root / ".complexity.toml"
    if complexity_toml.is_file():
        with open(complexity_toml, "rb") as f:
            data = tomllib.load(f)
        _apply_dict(config, data)
        return config

    # Fall back to pyproject.toml
    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        with open(pyproject, "rb") as f:
            data = tomllib.load(f)
        tool_section = data.get("tool", {}).get("complexity-accounting", {})
        if tool_section:
            _apply_dict(config, tool_section)

    return config


def merge_cli_overrides(config: Config, **overrides) -> Config:
    """
    Override config values with explicitly-provided CLI arguments.

    Only non-None values are applied.
    """
    for key, value in overrides.items():
        if value is not None and hasattr(config, key):
            setattr(config, key, value)
    return config
