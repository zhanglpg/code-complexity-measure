# Complexity Accounting Tool

> "Complexity is the core problem of software." — Liping

Measures **Net Complexity Score (NCS)** — whether your codebase is an asset or liability to future development. CI-ready, git-aware, built for real engineering teams.

## Quick Start

```bash
# Scan a directory
python -m complexity_accounting scan /path/to/code

# JSON output (for CI)
python -m complexity_accounting scan /path/to/code --json

# Compare branches
python -m complexity_accounting compare --base main --head HEAD --repo .

# Trend over commits
python -m complexity_accounting trend --repo . --commits 20

# CI gate: fail if NCS > 8
python -m complexity_accounting scan . --fail-above 8
```

## What It Measures

| Metric | What | Why |
|--------|------|-----|
| **Cognitive Complexity** | How hard is the code to understand | Primary signal — measures human burden |
| **Cyclomatic Complexity** | Number of decision paths | Classic metric, good for test coverage estimation |
| **Net Complexity Score** | Weighted aggregate with hotspot penalty | Single number for CI gates |
| **Hotspots** | Functions above threshold (default 10) | Identifies refactoring targets |

### Net Complexity Score (NCS)

```
NCS = avg_cognitive_per_function × (1 + hotspot_ratio)
```

- **hotspot_ratio** = functions above threshold / total functions
- Penalizes codebases with concentrated complexity
- Rating: 🟢 ≤3 | 🟡 ≤6 | 🟠 ≤10 | 🔴 >10

## Architecture

```
complexity_accounting/
├── scanner.py          # Core: cognitive + cyclomatic complexity via libcst
├── git_tracker.py      # Git-aware: compare refs, track trends, PR deltas
├── __main__.py         # CLI entry point
└── __init__.py
```

- **libcst** for AST parsing (preserves comments, whitespace, position info)
- Pure Python, no external services
- Designed for multi-language extension (scanner interface is language-agnostic)

## CI Integration

### GitHub Actions

```yaml
- name: Complexity Check
  run: |
    pip install libcst
    python -m complexity_accounting scan . --json > complexity.json
    python -m complexity_accounting scan . --fail-above 8
```

### PR Comment (compare mode)

```yaml
- name: Complexity Delta
  run: |
    python -m complexity_accounting compare \
      --base origin/main --head HEAD --repo . --markdown \
      > complexity-report.md
```

## Dependencies

- Python ≥ 3.8
- libcst ≥ 1.0.0

## License

MIT
