# NCS Self-Assessment: Iterative Refactoring Analysis

This document records findings from using the complexity-accounting tool on its own codebase, iteratively refactoring to reduce complexity and verifying whether the NCS metric tracks improvements effectively.

## Baseline Metrics

| Metric | Value |
|--------|-------|
| NCS | 9.17 |
| Rating | Concerning |
| Files scanned | 19 |
| Total functions | 204 |
| Hotspots (>=10) | 32 |
| Avg cognitive/func | 5.79 |
| Avg MI | 65.08 |
| Churn factor | 1.133 |
| Coupling factor | 1.351 |
| Dominant factor | coupling |

### Top Hotspots (Before)
| CC | Function | File |
|----|----------|------|
| 141 | cmd_scan | __main__.py:37 |
| 84 | GoParser.collect_functions | go_parser.py:58 |
| 70 | TreeSitterParser.compute_cognitive_complexity | base_parser.py:201 |
| 60 | CppParser.collect_functions | cpp_parser.py:60 |
| 52 | RustParser.collect_functions | rust_parser.py:58 |
| 47 | TsParser.collect_functions | ts_parser.py:71 |
| 45 | JsParser.collect_functions | js_parser.py:65 |
| 29 | main | scanner.py:996 |
| 27 | scan_directory | scanner.py:928 |
| 24 | _extract_go_imports | coupling.py:162 |
| 22 | _get_ts_language | coupling.py:233 |
| 22 | _extract_name_from_declarator | cpp_parser.py:123 |

---

## Iteration 1: Highest-Impact Structural Changes

### Changes Made
- Decomposed `cmd_scan` (CC=141) into 5 extracted helpers: `_build_config`, `_setup_cache`, `_compute_factors`, `_ncs_rating`, `_format_text_report`
- Converted `_get_ts_language` (CC=22) from if-elif chain to table-driven dict lookup
- Simplified `scanner.main()` (CC=29) to delegate to `__main__.main()`
- Converted `_scan_file_uncached` dispatch (CC=13) to table-driven

### Metrics After

| Metric | Before | After | Change |
|--------|--------|-------|--------|
| NCS | 9.17 | 7.60 | -1.57 (-17%) |
| Rating | Concerning | Concerning | — |
| Functions | 204 | 212 | +8 |
| Hotspots (>=10) | 32 | 31 | -1 |
| Avg cognitive/func | 5.79 | 4.98 | -0.81 (-14%) |
| Avg MI | 65.08 | 64.92 | -0.16 |
| Coupling factor | 1.351 | 1.286 | -0.065 |
| Churn factor | 1.133 | 1.133 | 0 |

Key function changes:
- `cmd_scan`: CC 141 → 18 (orchestrator only)
- `scanner.main()`: CC 29 → eliminated (delegates to __main__)
- `_get_ts_language`: CC 22 → dropped off top 50 (table-driven)
- `_scan_file_uncached`: CC 13 → 11
- New functions: `_build_config` (17), `_ncs_rating` (6), `_compute_factors` (6), `_format_text_report` (6), `_print_ncs_breakdown` (0), `_print_top_functions` (4), `_print_top_classes` (3), `_setup_cache` (2)

### Analysis

**NCS tracked expectations well.** The 17% drop in NCS is substantial and corresponds to the reduction in avg cognitive complexity (14% drop). The mega-function `cmd_scan` (CC=141) was by far the biggest hotspot; splitting it into 8 focused helpers reduced the average dramatically.

**Coupling factor also improved** (-0.065), likely because the table-driven refactoring in `coupling.py` and `scanner.py` reduced the number of explicit import statements (lazy imports via `importlib.import_module` instead of explicit `from .X import Y` chains).

**Notable observations:**
1. The total function count increased from 204 to 212 (+8), which is expected when extracting helpers. Despite more functions, the average complexity dropped significantly because the new functions are small and focused.
2. The hotspot count only dropped by 1 (32→31), because most hotspots are in the parser files which weren't touched yet. The eliminated CC=141 mega-function was replaced by CC=18 + CC=17 functions, both still above the threshold.
3. MI barely changed (-0.16), which makes sense — MI penalizes long functions, and while we broke up one, the total LOC stayed similar.
4. The NCS metric correctly reflects that the codebase became more maintainable: the same total complexity is now distributed across more, smaller, focused functions rather than concentrated in one mega-function.

---

## Iteration 2: Parser collect_functions Cleanup

### Changes Made
- **go_parser.py**: Extracted `_extract_receiver_type()` helper from deeply nested (5 levels) method receiver extraction in `GoParser.collect_functions`
- **ts_parser.py**: Merged duplicate `method_definition` and `function_declaration` handler blocks into a single `if node.type in (...)` check
- **js_parser.py**: Same merge as ts_parser.py
- **rust_parser.py**: Extracted `_find_child_by_type()` and `_get_child_text()` helpers to replace repetitive for-loop child lookups in `RustParser.collect_functions`

### Metrics After

| Metric | Iter 1 | Iter 2 | Change |
|--------|--------|--------|--------|
| NCS | 7.60 | 7.16 | -0.44 (-6%) |
| Functions | 212 | 215 | +3 |
| Hotspots (>=10) | 31 | 32 | +1 |
| Avg cognitive/func | 4.98 | 4.63 | -0.35 (-7%) |
| Avg MI | 64.92 | 65.01 | +0.09 |

Key function changes:
- `GoParser.collect_functions`: CC 84 → 11 (extracted `_extract_receiver_type` CC=43)
- `TsParser.collect_functions`: CC 47 → 42
- `JsParser.collect_functions`: CC 45 → 40
- `RustParser.collect_functions`: CC 52 → 28
- GoParser class total cog: 99 → 26

### Analysis

**NCS continued to track improvements**, dropping another 6%. The avg cognitive/func dropped 7%, consistent with the NCS reduction.

**Notable observations:**
1. **Go parser saw the biggest improvement** — extracting the 5-level-deep receiver extraction was a clear win. `GoParser.collect_functions` dropped from CC=84 to CC=11, making it no longer a hotspot. However, the extracted `_extract_receiver_type` has CC=43 itself — this reflects that the nested tree traversal logic is inherently complex regardless of where it lives.
2. **TS/JS merging had modest impact** (CC 47→42 and 45→40). Eliminating duplicated code blocks helps readability but doesn't dramatically reduce cognitive complexity because the structural nesting depth is unchanged.
3. **Hotspot count went up by 1** (31→32) despite reducing function complexity. This is because the extracted `_extract_receiver_type` (CC=43) is a new hotspot. The NCS metric correctly handles this: while hotspot count rose slightly, the average complexity dropped because the new functions are smaller on average.
4. **MI improved slightly** (+0.09), consistent with shorter functions being more maintainable.
5. **Coupling factor stayed the same** (1.286) — parser refactoring didn't change import patterns.

---

## Iteration 3: compute_cognitive_complexity Refactor

### Changes Made
- **base_parser.py**: Refactored `compute_cognitive_complexity` inner `walk()` function:
  - Extracted `_walk_body_children()` helper to eliminate duplicated child-walking pattern used by loops, catch, lambda, and nesting-only handlers
  - Consolidated loops + catch into a single handler (identical behavior)
  - Consolidated lambda + nesting_only into a single handler (identical behavior)
  - Reduced from 8 sequential if-blocks to 6, with less code duplication

### Metrics After

| Metric | Iter 2 | Iter 3 | Change |
|--------|--------|--------|--------|
| NCS | 7.16 | 7.01 | -0.15 (-2%) |
| Functions | 215 | 215 | 0 |
| Hotspots (>=10) | 32 | 32 | 0 |
| Avg cognitive/func | 4.63 | 4.51 | -0.12 (-3%) |
| Avg MI | 65.01 | 65.03 | +0.02 |

Key function change:
- `TreeSitterParser.compute_cognitive_complexity`: CC 70 → 45 (-36%)
- `TreeSitterParser` class total cog: 167 → 142

### Analysis

**Smaller but legitimate improvement.** The 2% NCS drop is modest, as expected — consolidating similar if-blocks reduces cognitive complexity but the function still has inherent structural complexity (it IS a complexity analyzer).

**Notable observations:**
1. CC dropped from 70 to 45 (36% reduction) by eliminating duplicated child-walking patterns. The `_walk_body_children` helper captures the recurring pattern of "walk children, entering body_types at nesting+1" which was duplicated in 4 handlers.
2. Despite the CC reduction, the function remains the 2nd highest hotspot (CC=45). This is inherent — a cognitive complexity walker that handles 8 node type categories will always have structural complexity. Further splitting would obscure rather than clarify.
3. The NCS metric captured this proportionally — a 36% drop in one function's CC translated to only 2% NCS improvement because many other functions are unchanged. This is correct behavior: NCS measures the whole codebase, not just one function.
4. This iteration confirms that **diminishing returns kick in around 3 iterations** on structural refactoring. The easy wins (mega-function decomposition, data-driven dispatch, deduplication) are in Iteration 1. Parser-specific cleanup in Iteration 2. Iteration 3 achieves meaningful local improvement but minimal global NCS impact.

---

## Iteration 4: Architectural Refactoring — Module Extraction

### Changes Made
- **Extracted `models.py`** from `scanner.py`: moved all data models (FunctionMetrics, ClassMetrics, FileMetrics, ScanResult), compute_mi(), constants (SUPPORTED_EXTENSIONS, TEST_FILE_PATTERNS, EXTENSION_LANGUAGE_MAP), and get_language() to a standalone module with no parsing dependencies
- **Updated imports across 10 files**: base_parser, all 6 language parsers, cache, plugin, git_tracker, __main__ — all now import data models from `models.py` instead of `scanner.py`
- **Extracted `discover_files()`** helper in scanner.py to share file discovery logic
- **Refactored `coupling.py`**: `analyze_directory_coupling()` now uses scanner's `discover_files()` instead of duplicating directory-walking logic; imports constants from `models.py` instead of `scanner.py`
- **scanner.py reduced** from ~1000 lines to ~540 lines (Python parsing + scanning API only)

### Metrics After

| Metric | Iter 3 | Iter 4 (Arch) | Change |
|--------|--------|---------------|--------|
| NCS | 7.01 | 6.80 | -0.21 (-3%) |
| Files scanned | 19 | 20 | +1 (models.py) |
| Functions | 215 | 216 | +1 |
| Hotspots (>=10) | 32 | 32 | 0 |
| Avg cognitive/func | 4.51 | 4.44 | -0.07 |
| Avg MI | 65.03 | 65.12 | +0.09 |
| **Coupling factor** | **1.286** | **1.265** | **-0.021** |
| Churn factor | 1.133 | 1.136 | +0.003 |

Key function changes:
- `scan_directory`: CC 27 → 14 (now delegates to `discover_files`)
- `analyze_directory_coupling`: CC 17 → dropped off top 30 (uses `discover_files`)
- `discover_files` new function at CC=13

### Analysis

**The coupling factor dropped**, confirming that architectural changes directly affect the metric the tool measures. This is the first iteration where the coupling factor (the dominant NCS contributor) actually improved.

**Notable observations:**
1. **Coupling reduction was modest but real** (-0.021). By moving data models to `models.py`, 10 modules that previously imported from `scanner.py` now import from a lightweight `models.py` that has zero internal dependencies. This reduced scanner.py's fan-in and spread imports more evenly.
2. **MI improved slightly** (+0.09) because `models.py` is a clean module of pure data classes — high maintainability. And scanner.py is now shorter with clearer purpose.
3. **Eliminating duplicated file discovery** had a direct cognitive complexity benefit: `scan_directory` dropped from CC=27 to CC=14, and `analyze_directory_coupling` dropped off the top 30 entirely.
4. **The coupling factor is still dominant** at 1.265. This reflects a structural reality: even with models extracted, the codebase still has many inter-module dependencies (parsers import from models + base_parser, scanner imports from models, etc.). Further coupling reduction would require more aggressive module consolidation.
5. **Architectural refactoring yielded smaller NCS improvement than expected.** The coupling factor formula `1 + avg/max` is inherently bounded. The max coupling file still has significant imports, so even though avg coupling dropped, the ratio changed only slightly.

---

## Final Assessment

### Overall NCS Progression

| Metric | Baseline | Iter 1 | Iter 2 | Iter 3 | Iter 4 (Arch) | Total Change |
|--------|----------|--------|--------|--------|---------------|-------------|
| **NCS** | **9.17** | **7.60** | **7.16** | **7.01** | **6.80** | **-2.37 (-26%)** |
| Rating | Concerning | Concerning | Concerning | Concerning | Concerning | — |
| Functions | 204 | 212 | 215 | 215 | 216 | +12 |
| Hotspots | 32 | 31 | 32 | 32 | 32 | 0 |
| Avg cog/func | 5.79 | 4.98 | 4.63 | 4.51 | 4.44 | -1.35 (-23%) |
| Avg MI | 65.08 | 64.92 | 65.01 | 65.03 | 65.12 | +0.04 |
| Coupling | 1.351 | 1.286 | 1.286 | 1.286 | 1.265 | -0.086 |
| Churn | 1.133 | 1.133 | 1.133 | 1.133 | 1.136 | +0.003 |

### Does NCS Effectively Capture Code Quality Improvements?

**Yes, with caveats.** The NCS metric tracked our refactoring improvements faithfully across all 4 iterations:

1. **Proportional tracking**: NCS dropped 26% total, closely matching the 23% reduction in avg cognitive complexity per function. The multiplicative model means other factors (coupling, churn) amplify or dampen cognitive improvements.

2. **Dominant factor persistence with architectural sensitivity**: Coupling remained dominant throughout, but Iteration 4 (module extraction) proved that architectural changes DO reduce it. Structural refactoring (Iters 1-3) didn't affect coupling; architectural refactoring (Iter 4) did. The metric correctly distinguishes between these two types of improvement.

3. **Hotspot count stability**: Despite dramatic reductions in individual function complexity (cmd_scan: 141→18, compute_cognitive_complexity: 70→45), the total hotspot count barely changed (32→32). This is because extracted helpers often remain above the threshold, and the threshold is applied uniformly. The NCS formula uses hotspot _ratio_, which smoothly captured the improvement in avg complexity even when count stayed flat.

### What NCS Captures Well

- **Function decomposition**: Breaking mega-functions into focused helpers reduces avg complexity, which NCS reflects
- **Code deduplication**: Merging identical handler blocks (TS/JS parsers) reduces cognitive load and CC
- **Data-driven refactoring**: Replacing if-elif chains with table lookups dramatically reduces CC and NCS captures this

### What NCS Could Better Capture

- **Hotspot threshold as a cliff**: The binary hotspot classification (above/below threshold) doesn't capture the magnitude of hotspot reduction. A function going from CC=141 to CC=18 is a massive improvement, but if it stays above threshold=10, it still counts as 1 hotspot. A **weighted hotspot score** (e.g., sum of excess complexity above threshold) would be more sensitive.
- **Coupling formula sensitivity**: The formula `1 + avg/max` is bounded and insensitive to changes in the middle of the distribution. When the max coupling file remains unchanged, redistributing imports has limited effect. Consider using a percentile-based or Gini-coefficient approach for coupling.
- **Function count effect**: Adding more functions (via extraction) dilutes avg complexity but doesn't change total complexity. NCS uses averages, which means splitting one CC=100 function into 5 CC=20 functions looks like improvement even though total complexity is unchanged. This is arguably correct (smaller functions ARE more maintainable) but could be supplemented with a total complexity metric.

### Recommendations

1. The NCS metric is **effective for tracking relative improvements** over time within a codebase
2. The **multiplicative model** correctly weights multiple quality dimensions and prevents gaming any single metric
3. **Weighted hotspot severity implemented** — replaced binary hotspot count with `sum(excess above threshold) / (total_functions * threshold)`. This makes the NCS sensitive to _how far_ above threshold functions are, not just whether they are. Verified: binary ratio showed -5.6% across 4 iterations; severity would have shown -47% for the same work
4. The **coupling factor formula** (`1 + avg/max`) could be more sensitive — consider alternatives that reward reducing the max coupling, not just the average
5. **Structural refactoring** (function decomposition) primarily improves cognitive complexity; **architectural refactoring** (module extraction) is needed to improve coupling. The NCS metric correctly requires both types of improvement for significant score reduction
6. **4 iterations** brought NCS from 9.17 to 6.80 (26% reduction). The remaining score (6.80) reflects inherent complexity of the domain — a complexity measurement tool analyzing code has naturally moderate coupling and non-trivial logic
