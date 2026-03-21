# Complexity Accounting Tool — Improvement Roadmap

> Last updated: 2026-03-21

## Current State (v0.1.0)

- 7 supported languages: Python, Go, Java, TypeScript, JavaScript, Rust, C/C++
- Metrics: Cognitive complexity, Cyclomatic complexity, Maintainability Index, Net Complexity Score
- Features: Git comparison, trend tracking, churn/coupling factors, GitHub Action
- 97.6% test coverage

## Known Bugs

1. **`compare_refs` full-scan ignores non-Python files** — `git_tracker.py:235` filters with `f.endswith('.py')` instead of checking `SUPPORTED_EXTENSIONS`. Full-scan mode silently drops Go/Java/TS/JS/Rust/C++ files.
2. **README language table is stale** — Only lists Python, Go, Java, TypeScript. Missing JavaScript, Rust, and C/C++ which are fully implemented.

## Phase 1: Immediate Quick Wins

| # | Item | Why | Files |
|---|------|-----|-------|
| 1 | Fix `compare_refs` to use `SUPPORTED_EXTENSIONS` instead of `.endswith('.py')` | Correctness bug — non-Python full-scan comparisons are broken | `git_tracker.py` |
| 2 | Update README language table with JS, Rust, C/C++ rows | Users can't discover supported languages | `README.md` |
| 3 | Add `--output FILE` flag to write results to a file | Common CI need — currently requires shell redirection | `__main__.py` |
| 4 | Add `.pre-commit-hooks.yaml` for pre-commit integration | Low-effort adoption boost | New file |

## Phase 2: Short-Term Architecture & Accuracy (2-6 weeks)

| # | Item | Why | Files |
|---|------|-----|-------|
| 5 | Refactor tree-sitter parsers into shared base class | JS/TS/C++/Rust/Go parsers are ~80% identical code. A `TreeSitterParser` base class would cut ~1000 lines of duplication and make adding languages trivial. | New `base_parser.py`, all tree-sitter parsers |
| 6 | Extend coupling analysis beyond Python | `coupling.py` only globs `*.py`. Coupling factor is silently 1.0 for all other languages, making NCS systematically low for non-Python projects. | `coupling.py` |
| 7 | Add parallel file scanning | `scan_directory` processes files sequentially. `ProcessPoolExecutor` would give near-linear speedup for large codebases. | `scanner.py` |
| 8 | PyPI publishing workflow | Tool is not discoverable without PyPI. Add a GitHub Actions workflow triggered on tag push. | New `.github/workflows/publish.yml` |
| 9 | Add CHANGELOG.md | 18 PRs with no changelog is a gap for users tracking changes. | New file |

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

1. **Fix the `compare_refs` bug** — one-line fix, correctness issue
2. **Update README language table** — documentation accuracy
3. **Refactor tree-sitter parsers** — biggest code quality win, reduces ~1000 lines of duplication
4. **Extend coupling to all languages** — fixes systematic NCS underestimation for non-Python projects
5. **Add PyPI publishing** — discoverability
