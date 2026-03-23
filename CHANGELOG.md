# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.6.1] - 2026-03-23

### Added
- **Duplication/clone detection**: Token-based Type-1 and Type-2 clone detection using Rabin-Karp rolling hash. Detects duplicate code blocks across and within files, with normalized identifiers/literals for renamed-variable clone matching. New `duplication.py` module.
- **Duplication factor in NCS**: `duplication_factor` integrated into both multiplicative and additive NCS formulas. Penalizes codebases with high levels of copy-paste duplication.
- `--no-duplication` CLI flag to skip duplication analysis
- `--duplication-min-tokens N` CLI flag to configure minimum token sequence length for clone detection (default: 50)
- `weight_duplication` (default: 0.15) and `duplication_min_tokens` (default: 50) config fields
- `duplication_factor` and `duplication_contribution` in NCS breakdown and JSON/HTML output
- 29 new tests covering factor computation, tokenization, rolling hash, clone detection, directory analysis, and NCS integration

## [1.6.0] - 2026-03-21

### Added
- **Class-level metrics**: `ClassMetrics` dataclass with WMC (Weighted Methods per Class), method count, total cognitive/cyclomatic complexity, and average method complexity. Supported across all 7 languages.
- **Halstead metrics**: Operator/operand counting for Python (libcst) and all tree-sitter languages. Maintainability Index now uses the full SEI formula (`MI = 171 - 5.2*ln(HV) - 0.23*CC - 16.2*ln(LOC)`) when Halstead Volume is available. Falls back to simplified formula gracefully.
- **Content-hash caching**: SHA-256 based file content caching in `.complexity-cache/` directory. Automatic cache invalidation on file changes or tool version updates. `--no-cache` CLI flag to bypass.
- **HTML report output**: Self-contained HTML reports with embedded CSS and JavaScript. Sortable tables, NCS gauge, class metrics section. Use `--format html -o report.html`.
- **SARIF 2.1.0 output**: GitHub Code Scanning compatible output. Hotspot functions reported as SARIF results with risk-based severity levels. Use `--format sarif`.
- **Plugin architecture**: `LanguagePlugin` protocol for third-party language support. Entry-point discovery via `complexity_accounting.languages` group. `list-plugins` CLI command.
- **`--format` flag**: Unified output format selection (`text`, `json`, `html`, `sarif`). `--json` remains as backward-compatible shorthand.
- **`list-plugins` command**: Shows discovered language plugins and their extensions.
- `halstead_volume` field on `FunctionMetrics` dataclass
- `classes` field on `FileMetrics` dataclass
- New modules: `halstead.py`, `cache.py`, `html_report.py`, `sarif.py`, `plugin.py`

### Changed
- `compute_mi()` now accepts optional `halstead_volume` parameter for improved accuracy
- `ScanResult.to_dict()` includes `classes` array per file
- `scan_file()` supports caching and plugin fallback for unknown file extensions
- Human-readable output now shows top complex classes when present

## [0.2.0] - 2026-03-21

### Added
- Shared `TreeSitterParser` base class for all tree-sitter language parsers, reducing ~1000 lines of duplication
- Multi-language coupling analysis: import fan-out is now computed for Go, Java, JavaScript, TypeScript, Rust, and C/C++ (previously Python-only)
- Parallel file scanning via `ProcessPoolExecutor` with `--workers N` CLI flag
- PyPI publishing workflow (`.github/workflows/publish.yml`)
- This CHANGELOG

### Changed
- `analyze_directory_coupling()` now scans all supported languages, not just `*.py` files
- `scan_directory()` accepts a `workers` parameter for parallel execution
- All tree-sitter parsers (Go, Java, JS, TS, Rust, C++) refactored to subclass `TreeSitterParser`

## [0.1.0] - 2026-03-21

### Added
- Core complexity metrics: Cognitive Complexity, Cyclomatic Complexity, Maintainability Index
- Net Complexity Score (NCS) with multiplicative and additive formulas
- 7 language support: Python (libcst), Go, Java, JavaScript, TypeScript, Rust, C/C++ (tree-sitter)
- CLI commands: `scan`, `compare`, `trend`
- Git-aware comparison (`compare --base main --head HEAD`)
- Trend tracking over recent commits (`trend --commits 20`)
- Churn factor (file modification frequency)
- Coupling factor (Python import fan-out)
- Hotspot detection with configurable thresholds
- JSON and human-readable output formats
- CI gate with `--fail-above` flag
- Output redirection with `--output` flag
- Configuration via `.complexity.toml` or `pyproject.toml`
- Language-specific configuration overrides
- GitHub Action (`action.yml`) with PR comment posting
- Pre-commit hook support (`.pre-commit-hooks.yaml`)
- 97.6% test coverage
