# Complexity Accounting Tool — Improvement Roadmap

> Last updated: 2026-03-21

## Current State (v0.2.0)

- 7 supported languages: Python, Go, Java, TypeScript, JavaScript, Rust, C/C++
- Metrics: Cognitive complexity, Cyclomatic complexity, Maintainability Index, Net Complexity Score
- Features: Git comparison, trend tracking, churn/coupling factors, GitHub Action
- Shared `TreeSitterParser` base class for all tree-sitter parsers
- Multi-language coupling analysis (all 7 languages)
- Parallel file scanning via `ProcessPoolExecutor`
- 92% test coverage

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

## Phase 4: Long-Term (3-6 months)

| # | Item | Why |
|---|------|-----|
| 16 | Duplication/clone detection | Major complexity signal not currently captured |
| 17 | VS Code extension | Inline complexity display, hotspot highlighting |
| 18 | Trend visualization (sparklines/charts) | `trend` command outputs plain table only |
| 19 | Docker image | Pre-built image with all language extras |
| 20 | Monorepo support | Per-package thresholds and reporting |
| 21 | Weighted hotspot severity in NCS formula | Binary hotspot count misses magnitude of improvements (see notes below) |

### Notes on Hotspot Metric Sensitivity (#21)

Discovered during self-refactoring analysis (see `analysis.md`): the current hotspot
metric uses a binary classification — a function is either above or below the threshold.
This means the NCS formula cannot distinguish between a function at CC=11 (barely a
hotspot) and one at CC=141 (extreme hotspot). When refactoring reduces a function from
CC=141 to CC=18, it still counts as one hotspot, and the hotspot_ratio is unchanged.

**Observed impact:** Across 3 refactoring iterations that reduced avg cognitive complexity
by 22%, the hotspot count stayed flat at 32. The NCS still improved (via avg complexity),
but the hotspot component of the formula was insensitive to meaningful quality gains.

**Proposed improvement:** Replace or supplement binary hotspot count with a **weighted
hotspot severity score**, e.g.:

```
hotspot_severity = sum(max(0, cc - threshold) for each function) / total_functions
```

This would make the metric proportional to _how far_ above the threshold functions are,
not just _whether_ they are. A function dropping from CC=141 to CC=18 would reduce
severity by 123 points, while the current binary count only changes if it crosses below
the threshold entirely.

**Trade-off:** The current binary ratio is simple and easy to explain ("15% of functions
are hotspots"). A severity score is more sensitive but harder to interpret. Consider
offering both, or using severity in the NCS formula while showing count in reports.

## Recommended Next Steps (Top 5)

1. **Weighted hotspot severity** (#21) — Low-effort NCS formula improvement informed by empirical self-analysis
2. **Duplication/clone detection** (#16) — Major complexity signal not currently captured
3. **Trend visualization** (#18) — sparklines/charts for the `trend` command
4. **Docker image** (#19) — Pre-built image with all language extras
5. **Monorepo support** (#20) — Per-package thresholds and reporting
