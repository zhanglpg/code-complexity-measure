# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
