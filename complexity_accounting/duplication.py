"""
Code duplication (clone) detection.

Detects Type-1 (exact) and Type-2 (renamed identifiers) clones using
token-based rolling hash (Rabin-Karp). Produces a duplication factor
for the NCS formula, following the same pattern as coupling and churn.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .scanner import EXTENSION_LANGUAGE_MAP


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class CloneBlock:
    """A contiguous block of code that is duplicated elsewhere."""
    file_path: str
    start_line: int
    end_line: int
    token_count: int


@dataclass
class CloneSet:
    """A group of 2+ code blocks that are duplicates of each other."""
    blocks: List[CloneBlock]
    token_count: int


@dataclass
class DuplicationMetrics:
    """Per-file duplication summary."""
    file_path: str
    duplicated_lines: int = 0
    total_lines: int = 0
    clone_blocks: List[CloneBlock] = field(default_factory=list)

    @property
    def duplication_ratio(self) -> float:
        if self.total_lines == 0:
            return 0.0
        return self.duplicated_lines / self.total_lines


# ---------------------------------------------------------------------------
# Token representation
# ---------------------------------------------------------------------------

@dataclass
class _Token:
    """A normalized token with its source line number."""
    kind: str  # normalized token text
    line: int


# ---------------------------------------------------------------------------
# Tokenization — Python (libcst)
# ---------------------------------------------------------------------------

_PYTHON_KEYWORDS = frozenset({
    "if", "else", "elif", "for", "while", "def", "class", "return", "yield",
    "try", "except", "finally", "with", "as", "import", "from", "raise",
    "assert", "pass", "break", "continue", "and", "or", "not", "in", "is",
    "lambda", "global", "nonlocal", "del", "async", "await",
})


# Python 3.12+ added FSTRING_START/MIDDLE/END; older versions don't have them.
import tokenize as _tokenize_mod
_FSTRING_TOKEN_TYPES = frozenset(
    getattr(_tokenize_mod, name)
    for name in ("FSTRING_START", "FSTRING_MIDDLE", "FSTRING_END")
    if hasattr(_tokenize_mod, name)
)


def _classify_python_token(tok_type: int, tok_string: str) -> str:
    """Map a Python token to a normalized kind string."""
    import tokenize
    if tok_type == tokenize.NAME:
        return tok_string if tok_string in _PYTHON_KEYWORDS else "$ID"
    if tok_type == tokenize.NUMBER:
        return "$NUM"
    if tok_type == tokenize.STRING or tok_type in _FSTRING_TOKEN_TYPES:
        return "$STR"
    return tok_string


def _tokenize_python(source: str) -> List[_Token]:
    """Tokenize Python source into normalized tokens using the stdlib tokenizer."""
    import tokenize
    import io

    _SKIP_TYPES = frozenset({
        tokenize.ENCODING, tokenize.NEWLINE, tokenize.NL,
        tokenize.INDENT, tokenize.DEDENT, tokenize.COMMENT,
        tokenize.ENDMARKER,
    })

    tokens: List[_Token] = []
    try:
        readline = io.BytesIO(source.encode("utf-8")).readline
        for tok in tokenize.tokenize(readline):
            if tok.type in _SKIP_TYPES:
                continue
            tokens.append(_Token(
                kind=_classify_python_token(tok.type, tok.string),
                line=tok.start[0],
            ))
    except tokenize.TokenError:
        pass
    return tokens


# ---------------------------------------------------------------------------
# Tokenization — Tree-sitter (all other languages)
# ---------------------------------------------------------------------------

# Node types that represent identifiers (normalized to $ID)
_TS_ID_TYPES = frozenset({
    "identifier", "type_identifier", "field_identifier",
    "property_identifier", "shorthand_property_identifier",
})

# Node types that represent literals (normalized to $NUM / $STR)
_TS_NUM_TYPES = frozenset({
    "number_literal", "integer_literal", "float_literal",
    "decimal_integer_literal", "decimal_floating_point_literal",
    "hex_integer_literal",
})
_TS_STR_TYPES = frozenset({
    "string_literal", "interpreted_string_literal", "raw_string_literal",
    "template_string", "string_content", "string_fragment",
    "character_literal", "char_literal",
})

# Keyword node types to keep as-is
_TS_KEYWORD_TYPES = frozenset({
    "if", "else", "for", "while", "do", "switch", "case", "default",
    "return", "break", "continue", "try", "catch", "throw", "finally",
    "class", "struct", "enum", "interface", "impl", "trait", "fn",
    "func", "function", "var", "let", "const", "mut", "pub", "static",
    "new", "this", "self", "super", "import", "export", "package",
    "async", "await", "yield", "match",
})

_TS_LANG_REGISTRY = {
    "go": ("tree_sitter_go", "language"),
    "java": ("tree_sitter_java", "language"),
    "javascript": ("tree_sitter_javascript", "language"),
    "typescript": ("tree_sitter_typescript", "language_typescript"),
    "rust": ("tree_sitter_rust", "language"),
    "cpp": ("tree_sitter_cpp", "language"),
}


def _get_ts_language(lang_name: str):
    """Get tree-sitter language object. Returns None if unavailable."""
    entry = _TS_LANG_REGISTRY.get(lang_name)
    if entry is None:
        return None
    mod_name, factory = entry
    try:
        import importlib
        import tree_sitter as ts
        mod = importlib.import_module(mod_name)
        return ts.Language(getattr(mod, factory)())
    except (ImportError, ValueError, AttributeError):
        return None


def _classify_ts_token(ntype: str, text: str) -> str:
    """Classify a tree-sitter leaf token into a normalized kind."""
    if ntype in _TS_ID_TYPES:
        return "$ID"
    if ntype in _TS_NUM_TYPES:
        return "$NUM"
    if ntype in _TS_STR_TYPES:
        return "$STR"
    if ntype in _TS_KEYWORD_TYPES or text in _TS_KEYWORD_TYPES:
        return text
    return text


def _tokenize_tree_sitter(source: str, language: str) -> List[_Token]:
    """Tokenize source using tree-sitter for a given language."""
    import tree_sitter as ts

    lang_obj = _get_ts_language(language)
    if lang_obj is None:
        return []

    parser = ts.Parser(lang_obj)
    tree = parser.parse(source.encode("utf-8"))

    tokens: List[_Token] = []

    def walk(node):
        if len(node.children) == 0:
            line = node.start_point[0] + 1
            text = node.text.decode() if node.text else node.type
            tokens.append(_Token(kind=_classify_ts_token(node.type, text), line=line))

        for child in node.children:
            walk(child)

    walk(tree.root_node)
    return tokens


# ---------------------------------------------------------------------------
# Unified tokenization
# ---------------------------------------------------------------------------

def tokenize_file(file_path: str) -> List[_Token]:
    """Tokenize a source file into normalized tokens."""
    ext = Path(file_path).suffix.lower()
    language = EXTENSION_LANGUAGE_MAP.get(ext)
    if language is None:
        return []

    try:
        source = Path(file_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    if not source.strip():
        return []

    if language == "python":
        return _tokenize_python(source)

    return _tokenize_tree_sitter(source, language)


# ---------------------------------------------------------------------------
# Rolling hash (Rabin-Karp) clone detection
# ---------------------------------------------------------------------------

_HASH_BASE = 31
_HASH_MOD = (1 << 61) - 1  # Mersenne prime for good distribution


def _rolling_hashes(tokens: List[_Token], window: int) -> List[Tuple[int, int]]:
    """
    Compute rolling hashes over a token stream.

    Returns list of (hash_value, start_index) for each window position.
    """
    if len(tokens) < window:
        return []

    # Precompute base^(window-1) mod p
    power = pow(_HASH_BASE, window - 1, _HASH_MOD)

    # Initial hash
    h = 0
    for i in range(window):
        h = (h * _HASH_BASE + hash(tokens[i].kind)) % _HASH_MOD

    result = [(h, 0)]

    for i in range(1, len(tokens) - window + 1):
        old_val = hash(tokens[i - 1].kind)
        new_val = hash(tokens[i + window - 1].kind)
        h = ((h - old_val * power) * _HASH_BASE + new_val) % _HASH_MOD
        result.append((h, i))

    return result


def _build_hash_index(
    file_tokens: Dict[str, List[_Token]],
    min_tokens: int,
) -> Dict[int, List[Tuple[str, int]]]:
    """Build a rolling-hash index mapping hash values to (file, offset) pairs."""
    hash_index: Dict[int, List[Tuple[str, int]]] = {}
    for fpath, tokens in file_tokens.items():
        for h, idx in _rolling_hashes(tokens, min_tokens):
            hash_index.setdefault(h, []).append((fpath, idx))
    return hash_index


def _verify_match(
    toks_a: List[_Token], start_a: int,
    toks_b: List[_Token], start_b: int,
    length: int,
) -> bool:
    """Return True if two token windows match token-by-token."""
    for k in range(length):
        if toks_a[start_a + k].kind != toks_b[start_b + k].kind:
            return False
    return True


def _group_verified_locations(
    locations: List[Tuple[str, int]],
    file_tokens: Dict[str, List[_Token]],
    min_tokens: int,
) -> List[List[Tuple[str, int]]]:
    """Group hash-colliding locations into verified match groups."""
    matched_groups: List[List[Tuple[str, int]]] = []
    used = [False] * len(locations)

    for i in range(len(locations)):
        if used[i]:
            continue
        fp_i, idx_i = locations[i]
        toks_i = file_tokens[fp_i]
        group = [(fp_i, idx_i)]
        used[i] = True

        for j in range(i + 1, len(locations)):
            if used[j]:
                continue
            fp_j, idx_j = locations[j]
            if fp_i == fp_j and abs(idx_i - idx_j) < min_tokens:
                continue
            if _verify_match(toks_i, idx_i, file_tokens[fp_j], idx_j, min_tokens):
                group.append((fp_j, idx_j))
                used[j] = True

        if len(group) >= 2:
            matched_groups.append(group)
    return matched_groups


def _build_clone_set(
    group: List[Tuple[str, int]],
    file_tokens: Dict[str, List[_Token]],
    min_tokens: int,
    claimed: Dict[str, set],
) -> Optional[CloneSet]:
    """Build a CloneSet from a verified group, respecting claimed ranges."""
    for fp, idx in group:
        token_range = set(range(idx, idx + min_tokens))
        if len(token_range & claimed[fp]) > min_tokens // 2:
            return None

    blocks = []
    for fp, idx in group:
        toks = file_tokens[fp]
        blocks.append(CloneBlock(
            file_path=fp,
            start_line=toks[idx].line,
            end_line=toks[idx + min_tokens - 1].line,
            token_count=min_tokens,
        ))
        claimed[fp].update(range(idx, idx + min_tokens))

    return CloneSet(blocks=blocks, token_count=min_tokens) if len(blocks) >= 2 else None


def find_clones(
    file_tokens: Dict[str, List[_Token]],
    min_tokens: int = 50,
) -> List[CloneSet]:
    """
    Find duplicate code blocks across all files.

    Uses Rabin-Karp rolling hash to find matching token windows,
    then extends matches greedily and groups into CloneSets.
    """
    if not file_tokens:
        return []

    hash_index = _build_hash_index(file_tokens, min_tokens)
    claimed: Dict[str, set] = {fp: set() for fp in file_tokens}
    clone_sets: List[CloneSet] = []

    for locations in hash_index.values():
        if len(locations) < 2:
            continue
        for group in _group_verified_locations(locations, file_tokens, min_tokens):
            cs = _build_clone_set(group, file_tokens, min_tokens, claimed)
            if cs is not None:
                clone_sets.append(cs)

    return clone_sets


# ---------------------------------------------------------------------------
# Directory analysis and factor computation
# ---------------------------------------------------------------------------

def analyze_directory_duplication(
    directory: str,
    exclude_patterns: Optional[List[str]] = None,
    include_tests: bool = False,
    min_tokens: int = 50,
) -> Dict[str, DuplicationMetrics]:
    """
    Analyze code duplication for all supported source files in a directory.

    Returns {relative_file_path: DuplicationMetrics}.
    """
    root = Path(directory)
    if root.is_file():
        # Single file — no cross-file clones possible, check within-file only
        tokens = tokenize_file(str(root))
        total_lines = _count_lines(str(root))
        clones = find_clones({str(root): tokens}, min_tokens)
        dup_lines = _count_duplicated_lines(str(root), clones)
        return {
            str(root): DuplicationMetrics(
                file_path=str(root),
                duplicated_lines=dup_lines,
                total_lines=total_lines,
            )
        }

    from .scanner import discover_files

    files = discover_files(directory, exclude_patterns, include_tests)
    if not files:
        return {}

    # Tokenize all files
    file_tokens: Dict[str, List[_Token]] = {}
    file_lines: Dict[str, int] = {}
    for fp in files:
        tokens = tokenize_file(fp)
        if tokens:
            file_tokens[fp] = tokens
        file_lines[fp] = _count_lines(fp)

    # Find clones across all files
    clones = find_clones(file_tokens, min_tokens)

    # Build per-file metrics
    results: Dict[str, DuplicationMetrics] = {}
    for fp in files:
        rel = str(Path(fp).relative_to(root))
        dup_lines = _count_duplicated_lines(fp, clones)
        clone_blocks = [
            b for cs in clones for b in cs.blocks if b.file_path == fp
        ]
        results[rel] = DuplicationMetrics(
            file_path=fp,
            duplicated_lines=dup_lines,
            total_lines=file_lines.get(fp, 0),
            clone_blocks=clone_blocks,
        )

    return results


def _count_lines(file_path: str) -> int:
    """Count total lines in a file."""
    try:
        return len(Path(file_path).read_text(encoding="utf-8", errors="replace").splitlines())
    except OSError:
        return 0


def _count_duplicated_lines(file_path: str, clone_sets: List[CloneSet]) -> int:
    """Count distinct lines involved in clones for a given file."""
    dup_lines: set = set()
    for cs in clone_sets:
        for block in cs.blocks:
            if block.file_path == file_path:
                dup_lines.update(range(block.start_line, block.end_line + 1))
    return len(dup_lines)


def compute_duplication_factor(duplication_data: Dict[str, DuplicationMetrics]) -> float:
    """
    Compute a duplication multiplier for NCS.

    Returns 1.0 (neutral) when no data or no duplicates.
    Formula: 1 + avg_duplication_ratio (bounded to [1.0, 2.0])
    """
    if not duplication_data:
        return 1.0
    ratios = [m.duplication_ratio for m in duplication_data.values()]
    avg_ratio = sum(ratios) / len(ratios)
    return round(min(2.0, 1.0 + avg_ratio), 4)
