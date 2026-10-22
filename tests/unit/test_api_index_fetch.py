"""Unit tests for index_fetch archive safety and preflight checks."""

import tarfile
import tempfile
from pathlib import Path

import pytest

from api.index_fetch import is_safe_path, safe_extract_archive
from api.preflight import check_port_bindable, run_preflight


def test_is_safe_path():
    base = Path("/app/data/index")
    assert is_safe_path(base, Path("/app/data/index/manifest.json"))
    assert is_safe_path(base, Path("/app/data/index/sub/file.bin"))

    # Path traversal attempts
    assert not is_safe_path(base, Path("/app/data/other/file.bin"))
    assert not is_safe_path(base, Path("/etc/passwd"))


def test_zip_slip_rejection():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        tar_path = tmp_path / "malicious.tar"

        # Create archive with path traversal entry
        with tarfile.open(tar_path, "w") as tar:
            info = tarfile.TarInfo(name="../escaped.txt")
            info.size = 0
            tar.addfile(info)

        dest = tmp_path / "dest"
        with pytest.raises(RuntimeError, match="Zip-Slip attempt detected"):
            safe_extract_archive(tar_path, dest)


def test_port_bindable():
    # An open ephemeral port should be bindable
    assert check_port_bindable("127.0.0.1", 29876) is True


def test_preflight_run():
    report = run_preflight()
    assert "status" in report
    assert "checks" in report
