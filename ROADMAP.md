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

## Phase 3: Medium-Term Features (1-3 months)

| # | Item | Why |
|---|------|-----|
| 10 | Class-level metrics (WMC, method count, total complexity) | OOP-heavy codebases need class-level analysis, not just function-level |
| 11 | HTML report output (`--format html`) | Rich visual reports for stakeholders and dashboards |
| 12 | Content-hash caching | Avoid re-parsing unchanged files on repeated scans |
| 13 | Halstead metrics for improved MI accuracy | Current MI formula omits the Halstead Volume term from the original SEI formula |
| 14 | SARIF output format | Integrates with GitHub Code Scanning Security tab |
| 15 | Plugin architecture for languages | `LanguagePlugin` protocol with entry-point discovery for third-party language support |

## Phase 4: Long-Term (3-6 months)

| # | Item | Why |
|---|------|-----|
| 16 | Duplication/clone detection | Major complexity signal not currently captured |
| 17 | VS Code extension | Inline complexity display, hotspot highlighting |
| 18 | Trend visualization (sparklines/charts) | `trend` command outputs plain table only |
| 19 | Docker image | Pre-built image with all language extras |
| 20 | Monorepo support | Per-package thresholds and reporting |

## Recommended Next Steps (Top 5)

1. **Class-level metrics** — OOP codebases need WMC and per-class analysis
2. **Content-hash caching** — avoid redundant re-parsing on repeated scans
3. **HTML report output** — stakeholder-friendly visual reports
4. **SARIF output** — GitHub Code Scanning integration
5. **Plugin architecture** — enable third-party language support
