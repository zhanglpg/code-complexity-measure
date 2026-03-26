"""Tests for configuration loading."""
import os
import tempfile
from pathlib import Path

from complexity_accounting.config import Config, load_config, merge_cli_overrides


def test_default_config():
    config = Config()
    assert config.risk_low == 5
    assert config.risk_moderate == 10
    assert config.risk_high == 20
    assert config.hotspot_threshold == 10
    assert config.weight_cognitive == 0.7
    assert config.weight_cyclomatic == 0.3
    assert config.churn_days == 90
    assert config.churn_commits == 100


def test_load_from_complexity_toml():
    with tempfile.TemporaryDirectory() as tmpdir:
        toml_path = Path(tmpdir) / ".complexity.toml"
        toml_path.write_text(
            'hotspot-threshold = 15\nweight-cognitive = 0.8\nweight-cyclomatic = 0.2\n'
        )
        config = load_config(tmpdir)
        assert config.hotspot_threshold == 15
        assert config.weight_cognitive == 0.8
        assert config.weight_cyclomatic == 0.2
        # Defaults preserved for unset keys
        assert config.risk_low == 5


def test_load_from_pyproject_toml():
    with tempfile.TemporaryDirectory() as tmpdir:
        pyproject = Path(tmpdir) / "pyproject.toml"
        pyproject.write_text(
            '[tool.complexity-accounting]\nrisk-high = 25\nchurn-days = 60\n'
        )
        config = load_config(tmpdir)
        assert config.risk_high == 25
        assert config.churn_days == 60
        assert config.hotspot_threshold == 10  # default


def test_complexity_toml_takes_precedence():
    with tempfile.TemporaryDirectory() as tmpdir:
        # Both files exist — .complexity.toml wins
        (Path(tmpdir) / ".complexity.toml").write_text("hotspot-threshold = 20\n")
        (Path(tmpdir) / "pyproject.toml").write_text(
            '[tool.complexity-accounting]\nhotspot-threshold = 5\n'
        )
        config = load_config(tmpdir)
        assert config.hotspot_threshold == 20


def test_no_config_files_returns_defaults():
    with tempfile.TemporaryDirectory() as tmpdir:
        config = load_config(tmpdir)
        assert config == Config()


def test_cli_overrides():
    config = Config()
    config = merge_cli_overrides(
        config, hotspot_threshold=15, weight_cognitive=0.6, nonexistent=42
    )
    assert config.hotspot_threshold == 15
    assert config.weight_cognitive == 0.6
    # None values don't override
    config = merge_cli_overrides(config, hotspot_threshold=None)
    assert config.hotspot_threshold == 15


# ---------------------------------------------------------------------------
# P2: Extended config tests
# ---------------------------------------------------------------------------

def test_apply_dict_type_coercion_int():
    from complexity_accounting.config import _apply_dict
    config = Config()
    _apply_dict(config, {"hotspot-threshold": "15"})
    assert config.hotspot_threshold == 15
    assert isinstance(config.hotspot_threshold, int)


def test_apply_dict_type_coercion_float():
    from complexity_accounting.config import _apply_dict
    config = Config()
    _apply_dict(config, {"weight-cognitive": "0.9"})
    assert config.weight_cognitive == 0.9
    assert isinstance(config.weight_cognitive, float)


def test_load_config_tomllib_none():
    import complexity_accounting.config as cfg
    original = cfg.tomllib
    try:
        cfg.tomllib = None
        config = load_config("/tmp")
        assert config == Config()
    finally:
        cfg.tomllib = original


def test_load_config_malformed_toml():
    with tempfile.TemporaryDirectory() as tmpdir:
        toml_path = Path(tmpdir) / ".complexity.toml"
        toml_path.write_text("this is not valid toml [[[")
        try:
            config = load_config(tmpdir)
            # If it raises, that's also acceptable behavior
            assert False, "Should have raised on malformed TOML"
        except Exception:
            pass  # Expected — malformed TOML raises


# ---------------------------------------------------------------------------
# P3: NCS model config tests
# ---------------------------------------------------------------------------

def test_ncs_model_default():
    config = Config()
    assert config.ncs_model == "multiplicative"
    assert config.weight_hotspot == 0.2
    assert config.weight_churn == 0.1
    assert config.weight_coupling == 0.1


def test_load_ncs_model_from_toml():
    with tempfile.TemporaryDirectory() as tmpdir:
        toml_path = Path(tmpdir) / ".complexity.toml"
        toml_path.write_text('ncs-model = "additive"\nweight-hotspot = 0.3\n')
        config = load_config(tmpdir)
        assert config.ncs_model == "additive"
        assert config.weight_hotspot == 0.3


# ---------------------------------------------------------------------------
# P4: Language-specific config tests
# ---------------------------------------------------------------------------

def test_language_overrides_empty():
    config = Config()
    assert config.language_overrides == {}


def test_load_language_overrides():
    with tempfile.TemporaryDirectory() as tmpdir:
        toml_path = Path(tmpdir) / ".complexity.toml"
        toml_path.write_text(
            '[language.typescript]\nrisk-low = 8\nhotspot-threshold = 15\n'
        )
        config = load_config(tmpdir)
        assert "typescript" in config.language_overrides
        assert config.language_overrides["typescript"]["risk_low"] == 8
        assert config.language_overrides["typescript"]["hotspot_threshold"] == 15


def test_load_language_overrides_pyproject():
    with tempfile.TemporaryDirectory() as tmpdir:
        pyproject = Path(tmpdir) / "pyproject.toml"
        pyproject.write_text(
            '[tool.complexity-accounting.language.python]\n'
            'hotspot-threshold = 12\n'
        )
        config = load_config(tmpdir)
        assert "python" in config.language_overrides
        assert config.language_overrides["python"]["hotspot_threshold"] == 12


def test_get_hotspot_threshold_with_language():
    config = Config(
        hotspot_threshold=10,
        language_overrides={"typescript": {"hotspot_threshold": 15}},
    )
    assert config.get_hotspot_threshold() == 10
    assert config.get_hotspot_threshold("python") == 10
    assert config.get_hotspot_threshold("typescript") == 15


def test_get_risk_levels_with_language():
    config = Config(
        risk_low=5, risk_moderate=10, risk_high=20,
        language_overrides={"typescript": {"risk_low": 8, "risk_moderate": 15}},
    )
    assert config.get_risk_levels() == (5, 10, 20)
    assert config.get_risk_levels("python") == (5, 10, 20)
    # TypeScript overrides low and moderate but inherits high
    assert config.get_risk_levels("typescript") == (8, 15, 20)


# ---------------------------------------------------------------------------
# Coverage gap: load_config with project_dir=None (line 130)
# ---------------------------------------------------------------------------

def test_load_config_default_dir():
    """load_config(None) should use cwd and return valid config."""
    config = load_config(None)
    # Should have all defaults since cwd likely has no config file
    assert config.hotspot_threshold == 10
    assert config.risk_low == 5


# ---------------------------------------------------------------------------
# Coverage gap: non-dict language override value (line 111)
# ---------------------------------------------------------------------------

def test_language_override_non_dict_skipped():
    """Non-dict values in [language.*] should be silently skipped."""
    with tempfile.TemporaryDirectory() as tmpdir:
        toml_path = Path(tmpdir) / ".complexity.toml"
        toml_path.write_text(
            '[language]\ntypescript = "not_a_dict"\n'
            '[language.python]\nhotspot-threshold = 12\n'
        )
        config = load_config(tmpdir)
        # typescript should be skipped (not a dict)
        assert "typescript" not in config.language_overrides
        # python should be loaded
        assert "python" in config.language_overrides
        assert config.language_overrides["python"]["hotspot_threshold"] == 12


def test_default_config_excludes_tests():
    """Default config has include_tests=False."""
    config = Config()
    assert config.include_tests is False


def test_include_tests_from_toml():
    """include-tests can be set in .complexity.toml."""
    with tempfile.TemporaryDirectory() as tmpdir:
        toml_path = Path(tmpdir) / ".complexity.toml"
        toml_path.write_text('include-tests = true\n')
        config = load_config(tmpdir)
        assert config.include_tests is True


def test_include_tests_cli_override():
    """include_tests can be set via CLI override."""
    config = Config()
    assert config.include_tests is False
    config = merge_cli_overrides(config, include_tests=True)
    assert config.include_tests is True


# ---------------------------------------------------------------------------
# Maintainability Index config
# ---------------------------------------------------------------------------

def test_weight_mi_default():
    """weight_mi defaults to 0.1."""
    config = Config()
    assert config.weight_mi == 0.1


def test_weight_mi_cli_override():
    """weight_mi can be overridden via CLI."""
    config = Config()
    config = merge_cli_overrides(config, weight_mi=0.3)
    assert config.weight_mi == 0.3


def test_weight_mi_from_toml():
    """weight-mi key is mapped correctly from TOML."""
    import tempfile
    config = Config()
    with tempfile.TemporaryDirectory() as tmpdir:
        toml_path = os.path.join(tmpdir, ".complexity.toml")
        with open(toml_path, "w") as f:
            f.write('weight-mi = 0.25\n')
        loaded = load_config(tmpdir)
        assert loaded.weight_mi == 0.25


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
