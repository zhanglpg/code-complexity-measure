# Plan: Duplication/Clone Detection (Roadmap #16)

## Goal
Add code duplication detection as a new NCS factor, following the established coupling/churn pattern. Duplicated code is a major complexity signal — it inflates maintenance cost, increases bug surface, and makes refactoring harder.

## Approach: Token-Based Rolling Hash (Type-2 Clones)

Detect **Type-1** (exact) and **Type-2** (renamed identifiers) clones using:
1. Tokenize source via tree-sitter (or libcst for Python) — reuse Halstead infrastructure patterns
2. Normalize tokens: replace identifiers/literals with placeholders, keep operators and keywords
3. Use a rolling hash (Rabin-Karp) over sliding windows of N tokens to find matching blocks
4. Group matches into clone sets (cross-file and within-file)
5. Compute a duplication ratio per file and an aggregate duplication factor for NCS

This is the industry-standard approach (used by PMD CPD, jscpd, etc.) and balances accuracy with performance.

---

## Step 1: Create `complexity_accounting/duplication.py`

**Data structures:**
```python
@dataclass
class CloneBlock:
    file_path: str
    start_line: int
    end_line: int
    token_count: int

@dataclass
class CloneSet:
    blocks: List[CloneBlock]  # 2+ blocks that are duplicates of each other
    token_count: int

@dataclass
class DuplicationMetrics:
    file_path: str
    duplicated_lines: int
    total_lines: int
    duplication_ratio: float  # duplicated_lines / total_lines
    clone_blocks: List[CloneBlock]  # blocks in this file that are clones
```

**Core algorithm:**
- `tokenize_file(file_path) -> List[Token]`: Extract normalized token stream
  - For Python: walk libcst AST (similar to halstead.py pattern)
  - For tree-sitter languages: walk tree-sitter nodes (similar to `_TS_OPERATOR_TYPES` pattern in halstead.py)
  - Normalize: identifiers → `$ID`, string literals → `$STR`, number literals → `$NUM`, keep keywords/operators/structure
  - Each token carries its source line number

- `find_clones(file_tokens: Dict[str, List[Token]], min_tokens: int = 50) -> List[CloneSet]`:
  - Build hash map: `{rolling_hash_value: [(file, token_index)]}`
  - Sliding window of `min_tokens` tokens over each file's token stream
  - Extend matching regions greedily beyond the minimum window
  - Deduplicate overlapping matches
  - Group into CloneSet instances

- `analyze_directory_duplication(directory, exclude_patterns=None, include_tests=False, min_tokens=50) -> Dict[str, DuplicationMetrics]`:
  - Call `scanner.discover_files()` to get file list
  - Tokenize all files
  - Run `find_clones()` across all token streams
  - Map clone blocks back to per-file DuplicationMetrics
  - Return `{relative_file_path: DuplicationMetrics}`

- `compute_duplication_factor(duplication_data: Dict[str, DuplicationMetrics]) -> float`:
  - Compute average duplication_ratio across all files
  - Formula: `1.0 + avg_duplication_ratio` (bounded to [1.0, 2.0])
  - Returns 1.0 when no duplicates (neutral multiplier)

## Step 2: Update `complexity_accounting/config.py`

Add to `Config` dataclass:
- `weight_duplication: float = 0.15` — weight in additive NCS model
- `duplication_min_tokens: int = 50` — minimum token sequence length to count as a clone (~6-8 lines)

Add to `_KEY_MAP`:
- `"weight-duplication"` → `"weight_duplication"`
- `"duplication-min-tokens"` → `"duplication_min_tokens"`

## Step 3: Update `complexity_accounting/models.py`

Modify `compute_ncs()` (line ~270):
- Add parameter: `duplication_factor: float = 1.0`
- **Multiplicative model** (line 308): multiply by `duplication_factor`
- **Additive model**: add `+ config.weight_duplication * ((duplication_factor - 1) * 10)`

Modify `compute_ncs_explained()` (line ~310):
- Add `duplication_factor` parameter
- Include `duplication_factor` and `duplication_contribution` in returned dict
- Consider duplication in `dominant_factor` identification

## Step 4: Update `complexity_accounting/__main__.py`

**CLI flags** (in scan argparse setup, ~line 409):
- `--no-duplication` flag (like `--no-churn`, `--no-coupling`)
- `--duplication-min-tokens INT` to override default minimum

**Factor computation** (`_compute_factors()`, ~line 96):
- Add duplication branch following coupling/churn pattern:
  ```python
  if not args.no_duplication:
      dup_data = analyze_directory_duplication(path, ...)
      duplication_factor = compute_duplication_factor(dup_data)
  ```
- Return duplication_factor alongside churn_factor and coupling_factor

**Pass factor through:**
- `compute_ncs(..., duplication_factor=duplication_factor)`
- `compute_ncs_explained(..., duplication_factor=duplication_factor)`

**NCS breakdown display** (`_print_ncs_breakdown()`, ~line 155):
- Add duplication_contribution line to text output

**JSON/HTML/SARIF outputs:**
- Include duplication_factor and duplication_contribution in output dicts (they come from `compute_ncs_explained()` automatically)

## Step 5: Create `tests/test_duplication.py`

Following test_coupling.py and test_churn.py patterns:

- **Factor computation tests:**
  - `test_compute_duplication_factor_empty()` — returns 1.0
  - `test_compute_duplication_factor_no_duplicates()` — returns 1.0
  - `test_compute_duplication_factor_with_duplicates()` — returns expected value
  - `test_compute_duplication_factor_bounded()` — never exceeds 2.0

- **Tokenization tests:**
  - `test_tokenize_python_file()` — basic tokenization
  - `test_tokenize_normalizes_identifiers()` — var names replaced with placeholders
  - `test_tokenize_preserves_structure()` — keywords/operators kept

- **Clone detection tests:**
  - `test_find_clones_identical_functions()` — two identical functions detected
  - `test_find_clones_renamed_variables()` — Type-2 clone detected
  - `test_find_clones_below_threshold()` — short duplicates ignored
  - `test_find_clones_cross_file()` — clones across different files

- **Directory analysis tests:**
  - `test_analyze_directory_duplication()` — end-to-end with temp files
  - `test_analyze_directory_empty()` — no files

- **NCS integration tests:**
  - `test_ncs_with_duplication_factor()` — factor applied correctly in both models

## Step 6: Update documentation

- **ROADMAP.md**: Mark #16 as Done
- **CHANGELOG.md**: Add entry for duplication detection feature
- **README.md**: Add duplication section to metrics documentation, update CLI reference with new flags

---

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Clone detection level | Token-based (Type-2) | Best balance of accuracy and simplicity; catches renamed clones without needing full AST diff |
| Minimum threshold | 50 tokens (~6-8 lines) | Avoids false positives from boilerplate (imports, simple getters) |
| Factor range | [1.0, 2.0] | Consistent with coupling factor bounding |
| Tokenization | Reuse tree-sitter/libcst infrastructure | Already proven for all 7 languages via Halstead |
| Rolling hash | Rabin-Karp | O(n) per file, O(n·m) for comparison; well-understood algorithm |
| Within-file clones | Yes, included | Important signal — copy-paste within a file is common |

## Files Changed

| File | Change |
|------|--------|
| `complexity_accounting/duplication.py` | **New** — core duplication detection module |
| `complexity_accounting/config.py` | Add weight_duplication, duplication_min_tokens |
| `complexity_accounting/models.py` | Add duplication_factor to NCS formulas |
| `complexity_accounting/__main__.py` | Add CLI flags, factor computation, display |
| `tests/test_duplication.py` | **New** — comprehensive test suite |
| `ROADMAP.md` | Mark #16 as Done |
| `CHANGELOG.md` | Add entry |
| `README.md` | Document new feature |

## Estimated Scope
- `duplication.py`: ~300-400 lines (tokenizer + rolling hash + metrics)
- `config.py`: ~10 lines changed
- `models.py`: ~30 lines changed
- `__main__.py`: ~40 lines changed
- `test_duplication.py`: ~250-300 lines
- Docs: ~30 lines across 3 files
