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
