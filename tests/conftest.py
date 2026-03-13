"""Shared pytest fixtures for complexity-accounting tests."""

import os
import subprocess
import tempfile
import textwrap

import pytest


@pytest.fixture
def tmp_python_file():
    """Factory fixture: create temporary Python files from source strings."""
    paths = []

    def _create(source):
        fd, path = tempfile.mkstemp(suffix=".py")
        os.write(fd, textwrap.dedent(source).encode())
        os.close(fd)
        paths.append(path)
        return path

    yield _create
    for p in paths:
        try:
            os.unlink(p)
        except OSError:
            pass


@pytest.fixture
def tmp_go_file():
    """Factory fixture: create temporary Go files from source strings."""
    paths = []

    def _create(source):
        fd, path = tempfile.mkstemp(suffix=".go")
        os.write(fd, textwrap.dedent(source).encode())
        os.close(fd)
        paths.append(path)
        return path

    yield _create
    for p in paths:
        try:
            os.unlink(p)
        except OSError:
            pass


@pytest.fixture
def tmp_git_repo(tmp_path):
    """Create a real git repository in a temporary directory.

    Returns a pathlib.Path to the repo root. The repo is pre-configured
    with user.name and user.email so commits work without global config.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(
        ["git", "init"], cwd=str(repo), capture_output=True, check=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=str(repo), capture_output=True, check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=str(repo), capture_output=True, check=True,
    )
    # Disable commit signing so tests work without GPG/SSH keys
    subprocess.run(
        ["git", "config", "commit.gpgsign", "false"],
        cwd=str(repo), capture_output=True, check=True,
    )
    return repo


@pytest.fixture
def tmp_java_file():
    """Factory fixture: create temporary Java files from source strings."""
    paths = []

    def _create(source):
        fd, path = tempfile.mkstemp(suffix=".java")
        os.write(fd, textwrap.dedent(source).encode())
        os.close(fd)
        paths.append(path)
        return path

    yield _create
    for p in paths:
        try:
            os.unlink(p)
        except OSError:
            pass


@pytest.fixture
def tmp_cpp_file():
    """Factory fixture: create temporary C++ files from source strings."""
    paths = []

    def _create(source):
        fd, path = tempfile.mkstemp(suffix=".cpp")
        os.write(fd, textwrap.dedent(source).encode())
        os.close(fd)
        paths.append(path)
        return path

    yield _create
    for p in paths:
        try:
            os.unlink(p)
        except OSError:
            pass


@pytest.fixture
def tmp_c_file():
    """Factory fixture: create temporary C files from source strings."""
    paths = []

    def _create(source):
        fd, path = tempfile.mkstemp(suffix=".c")
        os.write(fd, textwrap.dedent(source).encode())
        os.close(fd)
        paths.append(path)
        return path

    yield _create
    for p in paths:
        try:
            os.unlink(p)
        except OSError:
            pass


def _has_tree_sitter_go():
    try:
        import tree_sitter_go  # noqa: F401
        return True
    except ImportError:
        return False


def _has_tree_sitter_java():
    try:
        import tree_sitter_java  # noqa: F401
        return True
    except ImportError:
        return False


requires_go = pytest.mark.skipif(
    not _has_tree_sitter_go(),
    reason="tree-sitter-go not installed",
)

requires_java = pytest.mark.skipif(
    not _has_tree_sitter_java(),
    reason="tree-sitter-java not installed",
)


def _has_tree_sitter_cpp():
    try:
        import tree_sitter_cpp  # noqa: F401
        return True
    except ImportError:
        return False


requires_cpp = pytest.mark.skipif(
    not _has_tree_sitter_cpp(),
    reason="tree-sitter-cpp not installed",
)
