"""
SARIF 2.1.0 output generator for complexity accounting.

Produces SARIF (Static Analysis Results Interchange Format) compatible with
GitHub Code Scanning and other SARIF consumers.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from . import __version__

SARIF_SCHEMA = "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/main/sarif-2.1/schema/sarif-schema-2.1.0.json"


def _risk_level_sarif(risk: str) -> str:
    """Map internal risk level to SARIF level."""
    return {
        "low": "note",
        "moderate": "warning",
        "high": "warning",
        "very_high": "error",
    }.get(risk, "note")


def _get_risk(cognitive: int, low: int = 5, moderate: int = 10, high: int = 20) -> str:
    if cognitive <= low:
        return "low"
    elif cognitive <= moderate:
        return "moderate"
    elif cognitive <= high:
        return "high"
    return "very_high"


def generate_sarif(
    scan_data: Dict[str, Any],
    config: Any = None,
    hotspot_threshold: int = 10,
) -> Dict[str, Any]:
    """Generate a SARIF 2.1.0 document from scan results.

    Args:
        scan_data: Output of ScanResult.to_dict()
        config: Config object (optional)
        hotspot_threshold: Minimum cognitive complexity for a result

    Returns:
        A dict representing the SARIF JSON structure.
    """
    threshold = config.hotspot_threshold if config else hotspot_threshold

    # Define rules
    rules = [
        {
            "id": "complexity/cognitive-moderate",
            "name": "ModerateCognitiveComplexity",
            "shortDescription": {
                "text": "Function has moderate cognitive complexity"
            },
            "fullDescription": {
                "text": "This function has a cognitive complexity score indicating moderate difficulty to understand and maintain."
            },
            "defaultConfiguration": {"level": "warning"},
            "properties": {"tags": ["maintainability", "complexity"]},
        },
        {
            "id": "complexity/cognitive-high",
            "name": "HighCognitiveComplexity",
            "shortDescription": {
                "text": "Function has high cognitive complexity"
            },
            "fullDescription": {
                "text": "This function has a high cognitive complexity score, making it difficult to understand and maintain. Consider refactoring."
            },
            "defaultConfiguration": {"level": "warning"},
            "properties": {"tags": ["maintainability", "complexity"]},
        },
        {
            "id": "complexity/cognitive-very-high",
            "name": "VeryHighCognitiveComplexity",
            "shortDescription": {
                "text": "Function has very high cognitive complexity"
            },
            "fullDescription": {
                "text": "This function has extremely high cognitive complexity. It should be refactored to improve maintainability."
            },
            "defaultConfiguration": {"level": "error"},
            "properties": {"tags": ["maintainability", "complexity"]},
        },
    ]

    rule_id_map = {
        "moderate": "complexity/cognitive-moderate",
        "high": "complexity/cognitive-high",
        "very_high": "complexity/cognitive-very-high",
    }

    # Generate results
    results = []
    for file_data in scan_data.get("files", []):
        file_path = file_data["path"]
        for fn in file_data.get("functions", []):
            cognitive = fn.get("cognitive_complexity", 0)
            if cognitive < threshold:
                continue

            risk = _get_risk(cognitive)
            if risk == "low":
                continue

            rule_id = rule_id_map.get(risk, "complexity/cognitive-moderate")
            sarif_level = _risk_level_sarif(risk)

            result = {
                "ruleId": rule_id,
                "level": sarif_level,
                "message": {
                    "text": (
                        f"Function '{fn.get('qualified_name', fn.get('name', 'unknown'))}' "
                        f"has cognitive complexity {cognitive} "
                        f"(risk: {risk}, cyclomatic: {fn.get('cyclomatic_complexity', 1)}, "
                        f"MI: {fn.get('maintainability_index', 100)})"
                    ),
                },
                "locations": [
                    {
                        "physicalLocation": {
                            "artifactLocation": {"uri": file_path},
                            "region": {
                                "startLine": fn.get("line", 1),
                                "endLine": fn.get("end_line", fn.get("line", 1)),
                            },
                        },
                    }
                ],
                "properties": {
                    "cognitive_complexity": cognitive,
                    "cyclomatic_complexity": fn.get("cyclomatic_complexity", 1),
                    "maintainability_index": fn.get("maintainability_index", 100),
                    "risk_level": risk,
                },
            }
            results.append(result)

    sarif = {
        "$schema": SARIF_SCHEMA,
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "complexity-accounting",
                        "version": __version__,
                        "informationUri": "https://github.com/zhanglpg/code-complexity-measure",
                        "rules": rules,
                    }
                },
                "results": results,
            }
        ],
    }

    return sarif


def sarif_to_json(sarif: Dict[str, Any], indent: int = 2) -> str:
    """Convert SARIF dict to JSON string."""
    return json.dumps(sarif, indent=indent)
