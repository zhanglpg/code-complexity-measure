---
name: refactor-complexity
description: Complexity-metric-driven iterative refactoring. Scans a codebase with complexity-accounting, identifies high-impact refactoring opportunities, applies them, and verifies NCS improvement. Use when you want to systematically reduce code complexity.
argument-hint: "[path] [--iterations N] [--threshold NCS]"
---

# Complexity-Driven Iterative Refactoring

You are performing metric-driven refactoring using the complexity-accounting tool. The goal is to **measurably reduce the Net Complexity Score (NCS)** while improving readability and maintainability.

## Prerequisites

Before running this skill, ensure the complexity-accounting tool is installed and available.

### Installation

```bash
# Core (Python-only analysis)
pip install complexity-accounting

# With additional language support
pip install complexity-accounting[go]          # Go
pip install complexity-accounting[java]        # Java
pip install complexity-accounting[ts]          # TypeScript
pip install complexity-accounting[js]          # JavaScript
pip install complexity-accounting[rust]        # Rust
pip install complexity-accounting[cpp]         # C/C++
```

### Requirements

- **Python >= 3.8**
- **libcst >= 1.0.0** (included with the package)
- **Git** — required for churn and coupling analysis; the tool works without git but those factors will be skipped
- **tomli >= 1.0.0** — only needed on Python < 3.11

### Verify Installation

Run a quick check to confirm the tool is available:

```bash
python -m complexity_accounting scan --help
```

If the command fails, install the package first. If the target codebase uses a non-Python language, install the corresponding extra (see above).

## Process

Run an iterative loop. Each iteration: scan → identify → refactor → verify. Stop when the target is reached, the codebase is clean enough, or you've done 3 iterations on similar patterns.

### Arguments

Parse `$ARGUMENTS` for:
- **path**: directory or file to refactor (default: current directory)
- **--iterations N**: max iterations (default: 3)
- **--threshold NCS**: stop when NCS drops below this value (default: none, iterate until diminishing returns)

### Step 0: Baseline Scan

Run the complexity scan on the target path to establish the baseline:

```
python -m complexity_accounting scan <path> --top 30
```

Record the baseline metrics: NCS, avg cognitive/func, hotspot count, coupling factor, dominant factor.

If NCS is already in the "Healthy" range (≤ 3), report that and stop — no refactoring needed.

### Step 1: Identify Refactoring Opportunities

From the scan output, identify the highest-impact opportunities using this priority order:

**Priority 1 — Mega-functions (CC > 40)**
Functions with extreme cognitive complexity. These dominate avg complexity and hotspot severity. Look for:
- Multiple responsibilities in one function (config + logic + output)
- Long sequential blocks that can be extracted into named helpers
- The function should become a short orchestrator calling focused helpers

**Priority 2 — If-elif dispatch chains (CC > 15, 4+ branches)**
Long chains mapping values to actions. Replace with:
- Dictionary lookup + lazy import (for language/extension dispatch)
- Registry pattern (for plugin-style dispatch)

**Priority 3 — Deep nesting (max_nesting >= 4)**
Deeply nested code that's hard to follow. Fix by:
- Extracting the inner logic into a helper function
- Using early returns to flatten conditionals

**Priority 4 — Duplicated handler blocks**
Near-identical code blocks differing only in a type check. Merge into:
- Single block with `if x in (type_a, type_b):` check
- Shared helper called from both sites

**Priority 5 — Dead/duplicate code**
Legacy entry points, copy-pasted logic across modules. Fix by:
- Delegation wrappers for backward-compat entry points
- Shared utility extraction for duplicated logic

**Priority 6 — Coupling reduction (architectural)**
Only pursue this after structural improvements plateau. Look for:
- God modules that everything imports from — extract data models to a standalone module
- Duplicated infrastructure (file discovery, language mapping) — extract shared utilities
- Modules importing heavy dependencies just for data types — split data from logic

### Step 2: Refactor (Focused)

Pick **2-4 related refactorings** from the opportunities identified. Do NOT try to fix everything at once.

Rules:
- Read the code before changing it
- Preserve all existing behavior — these are pure refactorings
- Don't add features, comments, or type annotations to untouched code
- Keep extracted helpers near their callers unless coupling reduction is the goal
- Name helpers descriptively (what they do, not how)

### Step 3: Verify

After each iteration:

1. **Run tests**: `pytest` (or the project's test command). All tests must pass. If a test hardcodes an expected NCS value, update it to match the new formula behavior.

2. **Run the scan again**: `python -m complexity_accounting scan <path> --top 30`

3. **Compare metrics**: Record before/after for:
   - NCS (primary metric)
   - Avg cognitive/func
   - Hotspot count
   - Coupling factor (if architectural changes were made)

4. **Assess whether to continue**:
   - If NCS dropped meaningfully (> 3%), continue to next iteration
   - If NCS barely moved (< 1%), the remaining complexity is likely inherent — stop
   - If you've done 3 iterations on similar patterns (e.g., all function decomposition), stop and suggest architectural changes instead
   - If NCS is at or below the `--threshold`, stop

### Step 4: Report

After the final iteration, provide a summary:

```
## Refactoring Summary

Baseline NCS: X.XX → Final NCS: Y.YY (−Z%)
Iterations: N

### Changes by iteration
1. [what was done] — NCS X.XX → Y.YY
2. [what was done] — NCS X.XX → Y.YY
...

### Remaining hotspots
- [function]: CC=N — [why it's inherently complex or what could be done next]

### Recommendation
[Whether further refactoring is worthwhile, and if so, what type
(structural vs architectural)]
```

## Key Principles

1. **Measure, don't guess.** Every change is validated by the NCS metric. If the score doesn't improve, the refactoring wasn't effective.

2. **Structural before architectural.** Function decomposition and deduplication (iterations 1-2) give the biggest bang per effort. Module extraction and coupling reduction (iteration 3+) require more planning but address the coupling factor specifically.

3. **Diminishing returns are real.** The first iteration typically captures 50-70% of the total improvement. By iteration 3, you're polishing. Stop when the effort exceeds the benefit.

4. **Inherent complexity exists.** A complexity analyzer computing cognitive complexity across 8 node types WILL have moderate CC. A CLI with 4 subcommands and 15 flags WILL have some structural complexity. The goal is to separate inherent complexity from accidental complexity.

5. **NCS factors are independent.** Structural refactoring improves cognitive complexity but not coupling. Architectural refactoring (module extraction) improves coupling. Both are needed for significant overall improvement. If NCS stalls, check which factor is dominant and switch strategy.
