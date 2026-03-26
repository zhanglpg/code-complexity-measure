"""Tests for complexity_accounting.__init__ module."""
import complexity_accounting


def test_version_is_string():
    assert complexity_accounting.__version__ == "1.6.1"


def test_version_semver_format():
    parts = complexity_accounting.__version__.split(".")
    assert len(parts) == 3
    assert all(p.isdigit() for p in parts)


def test_version_major_minor_patch():
    parts = complexity_accounting.__version__.split(".")
    major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])
    assert major == 1
    assert minor == 6
    assert patch == 1
