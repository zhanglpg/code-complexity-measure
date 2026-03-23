# Complexity Accounting Tool — Improvement Roadmap

> Last updated: 2026-03-23

## Current State (v1.6.1)

- 7 supported languages: Python, Go, Java, TypeScript, JavaScript, Rust, C/C++
- Metrics: Cognitive complexity, Cyclomatic complexity, Maintainability Index, Halstead metrics, Net Complexity Score
- Features: Git comparison, trend tracking, churn/coupling/duplication factors, GitHub Action
- Shared `TreeSitterParser` base class for all tree-sitter parsers
- Multi-language coupling analysis (all 7 languages)
- Parallel file scanning via `ProcessPoolExecutor`
- Class-level metrics (WMC, method count, total complexity)
- Content-hash caching (`.complexity-cache/`)
- Output formats: text, JSON, HTML, SARIF 2.1.0
- Plugin architecture for third-party language support
- Weighted hotspot severity in NCS formula (replaces binary count)
- Additive and multiplicative NCS models (`--ncs-model`)
- NCS breakdown/explanation (`compute_ncs_explained()`)
- Language-aware risk thresholds and hotspot thresholds
- Token-based duplication/clone detection (Type-1 & Type-2 clones)

## Known Bugs

1. ~~**`compare_refs` full-scan ignores non-Python files** — `git_tracker.py:235` filters with `f.endswith('.py')` instead of checking `SUPPORTED_EXTENSIONS`. Full-scan mode silently drops Go/Java/TS/JS/Rust/C++ files.~~ **Fixed in v0.1.0**
2. ~~**README language table is stale** — Only lists Python, Go, Java, TypeScript. Missing JavaScript, Rust, and C/C++ which are fully implemented.~~ **Fixed in v0.1.0**

## Phase 1: Immediate Quick Wins ✅ Complete

| # | Item | Status |
|---|------|--------|
| 1 | Fix `compare_refs` to use `SUPPORTED_EXTENSIONS` instead of `.endswith('.py')` | ✅ Done |
| 2 | Update README language table with JS, Rust, C/C++ rows | ✅ Done |
| 3 | Add `--output FILE` flag to write results to a file | ✅ Done |
| 4 | Add `.pre-commit-hooks.yaml` for pre-commit integration | ✅ Done |

## Phase 2: Short-Term Architecture & Accuracy ✅ Complete

| # | Item | Status | Notes |
|---|------|--------|-------|
| 5 | Refactor tree-sitter parsers into shared base class | ✅ Done | `base_parser.py` with `TreeSitterParser`; ~1200 lines eliminated |
| 6 | Extend coupling analysis beyond Python | ✅ Done | Go, Java, JS, TS, Rust, C/C++ imports via tree-sitter |
| 7 | Add parallel file scanning | ✅ Done | `ProcessPoolExecutor` with `--workers N` CLI flag |
| 8 | PyPI publishing workflow | ✅ Done | `.github/workflows/publish.yml` with OIDC trusted publishing |
| 9 | Add CHANGELOG.md | ✅ Done | Keep a Changelog format, v0.1.0 and v0.2.0 entries |

## Phase 3: Medium-Term Features ✅ Complete

| # | Item | Status | Notes |
|---|------|--------|-------|
| 10 | Class-level metrics (WMC, method count, total complexity) | ✅ Done | `ClassMetrics` dataclass; all 7 languages supported |
| 11 | HTML report output (`--format html`) | ✅ Done | Self-contained HTML with embedded CSS/JS, sortable tables |
| 12 | Content-hash caching | ✅ Done | SHA-256 content hashes; `--no-cache` flag; `.complexity-cache/` directory |
| 13 | Halstead metrics for improved MI accuracy | ✅ Done | Full SEI MI formula with Halstead Volume; Python (libcst) + tree-sitter |
| 14 | SARIF output format | ✅ Done | SARIF 2.1.0; `--format sarif`; GitHub Code Scanning compatible |
| 15 | Plugin architecture for languages | ✅ Done | `LanguagePlugin` protocol; entry-point discovery; `list-plugins` command |

## Phase 4: Long-Term

| # | Item | Status | Notes |
|---|------|--------|-------|
| 16 | Duplication/clone detection | ✅ Done | Token-based Type-2 clone detection (Rabin-Karp rolling hash); `duplication.py` module; `--no-duplication` flag; NCS factor integration |
| 17 | VS Code extension | | Inline complexity display, hotspot highlighting |
| 18 | Trend visualization (sparklines/charts) | | `trend` command outputs ASCII table; no charts yet |
| 19 | Docker image | | Pre-built image with all language extras |
| 20 | Monorepo support | | Per-package thresholds and reporting |
| 21 | Weighted hotspot severity in NCS formula | ✅ Done | Replaced binary count with sum of excess complexity above threshold (see notes below) |

### Notes on Hotspot Metric Sensitivity (#21) — Resolved

Discovered during self-refactoring analysis (see `analysis.md`): the original hotspot
metric used a binary classification — a function was either above or below the threshold.
This meant the NCS formula could not distinguish between a function at CC=11 (barely a
hotspot) and one at CC=141 (extreme hotspot).

**Resolution:** The NCS formula now uses weighted hotspot severity (`models.py:251-262`):

```python
total_excess = sum(max(0, fn.cognitive_complexity - threshold) for fn in all_functions)
hotspot_ratio = total_excess / (total_functions * threshold)
```

This makes the metric proportional to _how far_ above the threshold functions are.
A function dropping from CC=141 to CC=18 reduces severity by 123 points, rather than
only registering when it crosses below the threshold entirely. Language-aware thresholds
are used via `config.get_hotspot_threshold(lang)`.

## Recommended Next Steps (Top 3)

1. **Trend visualization** (#18) — sparklines/charts for the `trend` command
2. **Docker image** (#19) — Pre-built image with all language extras
3. **Monorepo support** (#20) — Per-package thresholds and reporting
