"""Tests for code duplication (clone) detection."""
import tempfile
from pathlib import Path

from complexity_accounting.duplication import (
    CloneBlock,
    CloneSet,
    DuplicationMetrics,
    analyze_directory_duplication,
    compute_duplication_factor,
    find_clones,
    tokenize_file,
    _Token,
    _tokenize_python,
    _rolling_hashes,
)


# ---------------------------------------------------------------------------
# Factor computation tests
# ---------------------------------------------------------------------------

def test_compute_duplication_factor_empty():
    assert compute_duplication_factor({}) == 1.0


def test_compute_duplication_factor_no_duplicates():
    data = {
        "a.py": DuplicationMetrics(file_path="a.py", duplicated_lines=0, total_lines=100),
        "b.py": DuplicationMetrics(file_path="b.py", duplicated_lines=0, total_lines=50),
    }
    assert compute_duplication_factor(data) == 1.0


def test_compute_duplication_factor_with_duplicates():
    data = {
        "a.py": DuplicationMetrics(file_path="a.py", duplicated_lines=50, total_lines=100),
        "b.py": DuplicationMetrics(file_path="b.py", duplicated_lines=0, total_lines=100),
    }
    # avg ratio = (0.5 + 0.0) / 2 = 0.25
    factor = compute_duplication_factor(data)
    assert factor == round(1.0 + 0.25, 4)


def test_compute_duplication_factor_bounded():
    """Factor should never exceed 2.0 even with 100% duplication."""
    data = {
        "a.py": DuplicationMetrics(file_path="a.py", duplicated_lines=100, total_lines=100),
        "b.py": DuplicationMetrics(file_path="b.py", duplicated_lines=100, total_lines=100),
    }
    factor = compute_duplication_factor(data)
    assert factor <= 2.0


def test_duplication_ratio_property():
    m = DuplicationMetrics(file_path="x.py", duplicated_lines=25, total_lines=100)
    assert m.duplication_ratio == 0.25


def test_duplication_ratio_zero_lines():
    m = DuplicationMetrics(file_path="x.py", duplicated_lines=0, total_lines=0)
    assert m.duplication_ratio == 0.0


# ---------------------------------------------------------------------------
# Tokenization tests
# ---------------------------------------------------------------------------

def test_tokenize_python_basic():
    source = "x = 1\ny = 2\n"
    tokens = _tokenize_python(source)
    assert len(tokens) > 0
    # Identifiers should be normalized
    id_tokens = [t for t in tokens if t.kind == "$ID"]
    assert len(id_tokens) >= 2  # x and y


def test_tokenize_python_normalizes_identifiers():
    source1 = "foo = bar + baz\n"
    source2 = "abc = xyz + qux\n"
    tokens1 = _tokenize_python(source1)
    tokens2 = _tokenize_python(source2)
    # Both should produce the same normalized token sequence
    kinds1 = [t.kind for t in tokens1]
    kinds2 = [t.kind for t in tokens2]
    assert kinds1 == kinds2


def test_tokenize_python_preserves_keywords():
    source = "if x > 0:\n    return x\n"
    tokens = _tokenize_python(source)
    kinds = [t.kind for t in tokens]
    assert "if" in kinds
    assert "return" in kinds


def test_tokenize_python_normalizes_numbers():
    source = "x = 42\n"
    tokens = _tokenize_python(source)
    num_tokens = [t for t in tokens if t.kind == "$NUM"]
    assert len(num_tokens) == 1


def test_tokenize_file_nonexistent():
    tokens = tokenize_file("/nonexistent/file.py")
    assert tokens == []


def test_tokenize_file_unsupported_extension():
    with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False) as f:
        f.write("hello world")
        f.flush()
        tokens = tokenize_file(f.name)
    assert tokens == []


def test_tokenize_file_empty():
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        f.write("")
        f.flush()
        tokens = tokenize_file(f.name)
    assert tokens == []


# ---------------------------------------------------------------------------
# Rolling hash tests
# ---------------------------------------------------------------------------

def test_rolling_hashes_basic():
    tokens = [_Token(kind=f"tok{i}", line=1) for i in range(10)]
    hashes = _rolling_hashes(tokens, window=5)
    assert len(hashes) == 6  # 10 - 5 + 1


def test_rolling_hashes_too_short():
    tokens = [_Token(kind="a", line=1) for _ in range(3)]
    hashes = _rolling_hashes(tokens, window=5)
    assert hashes == []


def test_rolling_hashes_identical_windows():
    """Identical token sequences should produce the same hash."""
    tokens = [_Token(kind="a", line=1)] * 10
    hashes = _rolling_hashes(tokens, window=5)
    # All windows are identical, so all hashes should be the same
    hash_values = [h for h, _ in hashes]
    assert len(set(hash_values)) == 1


# ---------------------------------------------------------------------------
# Clone detection tests
# ---------------------------------------------------------------------------

def test_find_clones_no_files():
    assert find_clones({}) == []


def test_find_clones_single_file_no_duplication():
    """A file with all unique token sequences should have no clones."""
    tokens = [_Token(kind=f"unique_{i}", line=i) for i in range(100)]
    clones = find_clones({"a.py": tokens}, min_tokens=10)
    assert len(clones) == 0


def test_find_clones_cross_file_identical():
    """Two files with identical token sequences should be detected as clones."""
    shared = [_Token(kind=f"t{i % 5}", line=i + 1) for i in range(20)]
    file_a = shared.copy()
    file_b = shared.copy()
    clones = find_clones({"a.py": file_a, "b.py": file_b}, min_tokens=10)
    assert len(clones) >= 1
    # Both files should be represented
    files_in_clones = set()
    for cs in clones:
        for b in cs.blocks:
            files_in_clones.add(b.file_path)
    assert "a.py" in files_in_clones
    assert "b.py" in files_in_clones


def test_find_clones_within_file():
    """Repeated blocks within a single file should be detected."""
    block = [_Token(kind=f"t{i % 5}", line=1) for i in range(15)]
    # Create a file with the same block repeated twice, separated by unique tokens
    separator = [_Token(kind=f"sep_{i}", line=20) for i in range(20)]
    # Assign different line numbers to the second block
    block2 = [_Token(kind=t.kind, line=40 + i) for i, t in enumerate(block)]
    tokens = block + separator + block2
    clones = find_clones({"a.py": tokens}, min_tokens=15)
    assert len(clones) >= 1


def test_find_clones_below_threshold():
    """Sequences shorter than min_tokens should not be flagged."""
    tokens_a = [_Token(kind="x", line=1)] * 5
    tokens_b = [_Token(kind="x", line=1)] * 5
    clones = find_clones({"a.py": tokens_a, "b.py": tokens_b}, min_tokens=10)
    assert len(clones) == 0


# ---------------------------------------------------------------------------
# Directory analysis tests
# ---------------------------------------------------------------------------

def test_analyze_directory_duplication_empty():
    with tempfile.TemporaryDirectory() as tmpdir:
        result = analyze_directory_duplication(tmpdir)
        assert result == {}


def test_analyze_directory_duplication_no_clones():
    with tempfile.TemporaryDirectory() as tmpdir:
        (Path(tmpdir) / "a.py").write_text("x = 1\n")
        (Path(tmpdir) / "b.py").write_text("y = 2\n")
        result = analyze_directory_duplication(tmpdir, min_tokens=5)
        assert len(result) == 2
        for m in result.values():
            assert m.duplicated_lines == 0


def test_analyze_directory_duplication_with_clones():
    """Two files with identical non-trivial content should show duplication."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create two identical files with enough code to exceed min_tokens
        code = "\n".join(
            f"def func_{i}(a, b):\n    result = a + b * {i}\n    return result\n"
            for i in range(20)
        )
        (Path(tmpdir) / "a.py").write_text(code)
        (Path(tmpdir) / "b.py").write_text(code)
        result = analyze_directory_duplication(tmpdir, min_tokens=20)
        assert len(result) == 2
        total_dup = sum(m.duplicated_lines for m in result.values())
        assert total_dup > 0


# ---------------------------------------------------------------------------
# NCS integration tests
# ---------------------------------------------------------------------------

def test_ncs_multiplicative_with_duplication_factor():
    from complexity_accounting.models import ScanResult, FileMetrics, FunctionMetrics
    from complexity_accounting.config import Config

    fm = FunctionMetrics(
        name="f", qualified_name="f", file_path="a.py",
        line=1, end_line=10, cognitive_complexity=10, cyclomatic_complexity=5,
        nloc=10,
    )
    result = ScanResult(files=[FileMetrics(path="a.py", functions=[fm])])
    config = Config()

    ncs_no_dup = result.compute_ncs(config, duplication_factor=1.0)
    ncs_with_dup = result.compute_ncs(config, duplication_factor=1.5)
    assert ncs_with_dup > ncs_no_dup
    # Multiplicative: ncs_with_dup should be ~1.5x ncs_no_dup
    assert abs(ncs_with_dup / ncs_no_dup - 1.5) < 0.01


def test_ncs_additive_with_duplication_factor():
    from complexity_accounting.models import ScanResult, FileMetrics, FunctionMetrics
    from complexity_accounting.config import Config

    fm = FunctionMetrics(
        name="f", qualified_name="f", file_path="a.py",
        line=1, end_line=10, cognitive_complexity=10, cyclomatic_complexity=5,
        nloc=10,
    )
    result = ScanResult(files=[FileMetrics(path="a.py", functions=[fm])])
    config = Config(ncs_model="additive")

    ncs_no_dup = result.compute_ncs(config, duplication_factor=1.0)
    ncs_with_dup = result.compute_ncs(config, duplication_factor=1.5)
    assert ncs_with_dup > ncs_no_dup


def test_ncs_explained_includes_duplication():
    from complexity_accounting.models import ScanResult, FileMetrics, FunctionMetrics
    from complexity_accounting.config import Config

    fm = FunctionMetrics(
        name="f", qualified_name="f", file_path="a.py",
        line=1, end_line=10, cognitive_complexity=10, cyclomatic_complexity=5,
        nloc=10,
    )
    result = ScanResult(files=[FileMetrics(path="a.py", functions=[fm])])
    config = Config()

    explanation = result.compute_ncs_explained(config, duplication_factor=1.5)
    assert "duplication_factor" in explanation
    assert "duplication_contribution" in explanation
    assert explanation["duplication_factor"] == 1.5
    assert explanation["duplication_contribution"] > 0


def test_ncs_explained_empty_includes_duplication():
    from complexity_accounting.models import ScanResult

    result = ScanResult(files=[])
    explanation = result.compute_ncs_explained(duplication_factor=1.2)
    assert "duplication_factor" in explanation
    assert "duplication_contribution" in explanation
    assert explanation["duplication_factor"] == 1.2


# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------

def test_config_has_duplication_fields():
    from complexity_accounting.config import Config
    config = Config()
    assert hasattr(config, "weight_duplication")
    assert hasattr(config, "duplication_min_tokens")
    assert config.weight_duplication == 0.15
    assert config.duplication_min_tokens == 50


if __name__ == "__main__":
    import traceback

    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = failed = 0
    for test in tests:
        try:
            test()
            print(f"  ✅ {test.__name__}")
            passed += 1
        except Exception as e:
            print(f"  ❌ {test.__name__}: {e}")
            traceback.print_exc()
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
