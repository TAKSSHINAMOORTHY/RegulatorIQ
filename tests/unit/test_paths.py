"""Unit tests for paths configuration."""

from config.paths import (
    DATA_DIR,
    DOCS_DIR,
    MANIFEST_JSONL_PATH,
    ROOT,
    find_repo_root,
)


def test_repo_root_discovery():
    root = find_repo_root()
    assert (root / "pyproject.toml").exists()
    assert root == ROOT


def test_paths_exist():
    assert DATA_DIR.exists()
    assert DOCS_DIR.exists()
    assert MANIFEST_JSONL_PATH.parent.exists()
