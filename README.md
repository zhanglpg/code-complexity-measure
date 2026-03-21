# Complexity Accounting Tool

> "Complexity is the core problem of software." — Liping

Measures **Net Complexity Score (NCS)** — whether your codebase is an asset or liability to future development. CI-ready, git-aware, multi-language, built for real engineering teams.

## Quick Start

```bash
pip install complexity-accounting

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
| **Net Complexity Score** | Weighted aggregate with hotspot, churn, and coupling penalties | Single number for CI gates |
| **Hotspots** | Functions above threshold (default 10) | Identifies refactoring targets |
| **Churn Factor** | How frequently files change | Penalizes volatile, complex code |
| **Coupling Factor** | Import fan-out (efferent coupling) | Penalizes tightly coupled modules |

### Net Complexity Score (NCS)

```
NCS = (w_cog * avg_cognitive + w_cyc * avg_cyclomatic) * (1 + hotspot_ratio) * churn_factor * coupling_factor
```

- **Weights** — cognitive: 0.7, cyclomatic: 0.3 (configurable)
- **hotspot_ratio** = functions above threshold / total functions
- **churn_factor** = 1.0 + log(avg_file_churn) / 10
- **coupling_factor** = 1.0 + avg_efferent_coupling / max_efferent_coupling
- Rating: low <=3 | moderate <=6 | concerning <=10 | critical >10

## Supported Languages

| Language | Backend | Install |
|----------|---------|---------|
| Python | libcst | included |
| Go | tree-sitter-go | `pip install complexity-accounting[go]` |
| Java | tree-sitter-java | `pip install complexity-accounting[java]` |
| TypeScript | tree-sitter-typescript | `pip install complexity-accounting[ts]` |
| JavaScript | tree-sitter-javascript | `pip install complexity-accounting[js]` |
| Rust | tree-sitter-rust | `pip install complexity-accounting[rust]` |
| C/C++ | tree-sitter-cpp | `pip install complexity-accounting[cpp]` |

## CLI Reference

### `scan` — Analyze files and directories

```bash
python -m complexity_accounting scan <path> [options]
```

| Option | Description | Default |
|--------|-------------|---------|
| `--json` | JSON output | off |
| `--threshold N` | Hotspot cognitive complexity threshold | 10 |
| `--top N` | Show top N complex functions | 20 |
| `--fail-above FLOAT` | Exit 1 if NCS exceeds value | none |
| `--config PATH` | Path to .complexity.toml | auto-detect |
| `--weights KEY=VAL` | Override NCS weights (e.g. `cognitive=0.7,cyclomatic=0.3`) | config |
| `--churn-days N` | Days of git history for churn analysis | 90 |
| `--churn-commits N` | Max commits for churn analysis | 100 |
| `--no-churn` | Skip churn factor calculation | off |
| `--no-coupling` | Skip coupling factor calculation | off |
| `--output FILE` / `-o` | Write output to file instead of stdout | stdout |

### `compare` — Diff complexity between git refs

```bash
python -m complexity_accounting compare --base REF --head REF [options]
```

| Option | Description | Default |
|--------|-------------|---------|
| `--base REF` | Base reference (branch, tag, SHA) | required |
| `--head REF` | Head reference | HEAD |
| `--repo PATH` | Git repository path | . |
| `--json` | JSON output | off |
| `--markdown` | Markdown output (for PR comments) | off |
| `--full` | Scan all files, not just changed ones | off |

### `trend` — Complexity over recent commits

```bash
python -m complexity_accounting trend --repo . [options]
```

| Option | Description | Default |
|--------|-------------|---------|
| `--repo PATH` | Git repository path | . |
| `--commits N` | Number of commits to analyze | 10 |
| `--ref REF` | Starting reference | HEAD |
| `--json` | JSON output | off |

## Configuration

Configuration precedence: **CLI args > .complexity.toml > pyproject.toml `[tool.complexity-accounting]` > defaults**

### `.complexity.toml`

```toml
hotspot-threshold = 8
weight-cognitive = 0.8
weight-cyclomatic = 0.2
risk-low = 5
risk-moderate = 10
risk-high = 20
churn-days = 90
churn-commits = 100
```

Or in `pyproject.toml`:

```toml
[tool.complexity-accounting]
hotspot-threshold = 8
weight-cognitive = 0.8
weight-cyclomatic = 0.2
```

## GitHub Action

Use this action in any repository to automatically report complexity scores on pushes and pull requests.

### Quick Start

```yaml
# .github/workflows/complexity.yml
name: Complexity Check
on: [push, pull_request]
permissions:
  contents: read
  pull-requests: write

jobs:
  complexity:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: zhanglpg/code-complexity-measure@main
        with:
          path: '.'
          fail-above: '8'
          post-comment: 'true'
```

### Inputs

| Input | Description | Default |
|-------|-------------|---------|
| `path` | Path to scan | `.` |
| `threshold` | Cognitive complexity hotspot threshold | `10` |
| `fail-above` | Fail the check if NCS exceeds this value | _(none)_ |
| `output-format` | Output format: `json` or `markdown` | `markdown` |
| `python-version` | Python version to use | `3.11` |
| `post-comment` | Post results as a PR comment (`true`/`false`) | `false` |
| `update-comment` | Update existing PR comment instead of creating duplicates | `true` |
| `extras` | Comma-separated language extras to install (e.g. `go,java,cpp`) | _(none)_ |

### Outputs

| Output | Description |
|--------|-------------|
| `ncs` | Net Complexity Score (float) |
| `hotspot-count` | Number of hotspot functions (int) |
| `pass` | Whether the scan passed the threshold (`true`/`false`) |
| `delta` | NCS delta from comparison, if available (float) |

### Features

- **Job Summary** — Every run writes a complexity report to the GitHub Actions Job Summary, visible on the workflow run page.
- **PR Comments** — When `post-comment: 'true'`, posts a detailed comparison report as a PR comment. Subsequent pushes update the same comment instead of creating duplicates.
- **Push & PR Support** — On `pull_request` events, compares the PR base vs head. On `push` events, compares `HEAD~1` vs `HEAD`.
- **Threshold Gating** — Set `fail-above` to fail the check if NCS exceeds the value. The Job Summary and PR comment are always posted, even when the check fails.
- **Multi-Language** — Set `extras: 'go,java'` to install Go and Java support via tree-sitter.
- **Pip Caching** — Dependencies are cached across runs for faster execution.

### Full Example

```yaml
name: Complexity Check
on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read
  pull-requests: write  # Required for PR comments

jobs:
  complexity:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0  # Full history needed for comparison

      - name: Complexity Check
        id: complexity
        uses: zhanglpg/code-complexity-measure@main
        with:
          path: 'src'
          threshold: '10'
          fail-above: '8'
          post-comment: 'true'
          extras: 'go'

      - name: Use outputs
        if: always()
        run: |
          echo "NCS: ${{ steps.complexity.outputs.ncs }}"
          echo "Hotspots: ${{ steps.complexity.outputs.hotspot-count }}"
          echo "Passed: ${{ steps.complexity.outputs.pass }}"
          echo "Delta: ${{ steps.complexity.outputs.delta }}"
```

> **Note:** `fetch-depth: 0` is required for comparison reports. `permissions: pull-requests: write` is required for PR comments.

See [`examples/complexity-check.yml`](examples/complexity-check.yml) for a copy-pasteable workflow.

### Manual Workflow Step

You can also use the CLI directly without the composite action:

```yaml
- name: Complexity Gate
  run: |
    pip install complexity-accounting
    python -m complexity_accounting scan . --fail-above 8

- name: PR Complexity Delta
  run: |
    python -m complexity_accounting compare \
      --base origin/main --head HEAD --repo . --markdown \
      > complexity-report.md
```

## Pre-commit Hook

Add complexity checking to your [pre-commit](https://pre-commit.com/) config:

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/zhanglpg/code-complexity-measure
    rev: main
    hooks:
      - id: complexity-check
        args: ['--fail-above', '8']
```

## Architecture

```
complexity_accounting/
├── scanner.py          # Core: cognitive + cyclomatic complexity via libcst
├── git_tracker.py      # Git-aware: compare refs, track trends, PR deltas
├── churn.py            # Git churn analysis (modification frequency)
├── coupling.py         # Import coupling analysis (efferent coupling)
├── go_parser.py        # Go support via tree-sitter
├── java_parser.py      # Java support via tree-sitter
├── ts_parser.py        # TypeScript support via tree-sitter
├── js_parser.py        # JavaScript support via tree-sitter
├── rust_parser.py      # Rust support via tree-sitter
├── cpp_parser.py       # C/C++ support via tree-sitter
├── config.py           # Configuration loading (.complexity.toml, pyproject.toml)
├── __main__.py         # CLI entry point
└── __init__.py
```

- **libcst** for Python AST parsing (preserves comments, whitespace, position info)
- **tree-sitter** for Go, Java, TypeScript, JavaScript, Rust, and C/C++ parsing
- Pure Python, no external services
- Graceful degradation — churn/coupling are optional, tool works without git

## Installation

```bash
# Core (Python analysis only)
pip install complexity-accounting

# With Go support
pip install complexity-accounting[go]

# With Java support
pip install complexity-accounting[java]

# Everything
pip install complexity-accounting[go,java]

# Development
pip install complexity-accounting[dev]
```

### Requirements

- Python >= 3.8
- libcst >= 1.0.0
- tomli >= 1.0.0 (Python < 3.11 only)

## Testing

```bash
# All tests
pytest

# With coverage
pytest --cov --cov-report=term-missing

# Skip optional language tests
pytest -m "not go and not java"

# End-to-end only
pytest -m e2e
```

## License

MIT
