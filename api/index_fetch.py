"""Index Fetching, Resumable Download, and Safe Extraction for RegulatorIQ.

Provides:
- Resumable HTTP Range download
- SHA-256 verification
- Path-traversal (Zip-Slip) & symlink attack guards during archive extraction
- Atomic directory swap
- CLI executable via: python -m api.index_fetch
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import shutil
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path
from typing import Optional

import httpx

from config.paths import INDEX_BASE_DIR

logger = logging.getLogger("regulatoriq.index_fetch")


def compute_file_sha256(filepath: Path) -> str:
    """Compute SHA-256 digest of a local file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def is_safe_path(base_dir: Path, target_path: Path) -> bool:
    """Check that target path does not escape base directory (Zip-Slip prevention)."""
    try:
        base_resolved = base_dir.resolve()
        target_resolved = target_path.resolve()
        return target_resolved.is_relative_to(base_resolved)
    except Exception:
        return False


def safe_extract_archive(archive_path: Path, dest_dir: Path) -> None:
    """Extract tar or zip archive safely enforcing symlink and traversal guards."""
    dest_dir.mkdir(parents=True, exist_ok=True)

    if archive_path.suffix in (".tar", ".gz", ".tgz") or ".tar." in archive_path.name:
        with tarfile.open(archive_path, "r:*") as tar:
            for member in tar.getmembers():
                target = dest_dir / member.name
                if not is_safe_path(dest_dir, target):
                    raise RuntimeError(
                        f"Zip-Slip attempt detected for archive entry: {member.name}"
                    )
                if member.issym() or member.islnk():
                    raise RuntimeError(f"Symlinks not permitted in index archive: {member.name}")
            tar.extractall(path=dest_dir)

    elif archive_path.suffix == ".zip":
        with zipfile.ZipFile(archive_path, "r") as zf:
            for info in zf.infolist():
                target = dest_dir / info.filename
                if not is_safe_path(dest_dir, target):
                    raise RuntimeError(
                        f"Zip-Slip attempt detected for archive entry: {info.filename}"
                    )
            zf.extractall(path=dest_dir)
    else:
        raise ValueError(f"Unsupported archive format: {archive_path}")


def download_with_resume(
    url: str,
    dest_path: Path,
    expected_sha256: Optional[str] = None,
    chunk_size: int = 65536,
) -> bool:
    """Download a file with HTTP Range resume and verify checksum."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    temp_download = dest_path.with_suffix(".part")

    downloaded_bytes = temp_download.stat().st_size if temp_download.exists() else 0
    headers = {}
    if downloaded_bytes > 0:
        headers["Range"] = f"bytes={downloaded_bytes}-"

    logger.info(f"Downloading {url} to {temp_download} (resume from {downloaded_bytes} bytes)...")

    with httpx.Client(follow_redirects=True, timeout=60.0) as client:
        with client.stream("GET", url, headers=headers) as resp:
            if resp.status_code == 416:  # Range Not Satisfiable -> already complete
                pass
            elif resp.status_code not in (200, 206):
                raise RuntimeError(f"Failed to download {url}: HTTP {resp.status_code}")
            else:
                mode = "ab" if resp.status_code == 206 else "wb"
                with open(temp_download, mode) as f:
                    for chunk in resp.iter_bytes(chunk_size):
                        f.write(chunk)

    # Verify SHA256 if expected
    actual_sha = compute_file_sha256(temp_download)
    if expected_sha256 and actual_sha.lower() != expected_sha256.lower():
        temp_download.unlink(missing_ok=True)
        raise ValueError(f"Checksum mismatch: expected {expected_sha256}, got {actual_sha}")

    temp_download.rename(dest_path)
    logger.info(f"Successfully downloaded archive to {dest_path}")
    return True


def fetch_index_archive(
    index_url: str,
    target_dir: Path,
    expected_sha256: Optional[str] = None,
) -> bool:
    """Download, verify, and atomically unpack index to target_dir."""
    if not index_url:
        logger.warning("INDEX_URL not configured. Cannot fetch remote index.")
        return False

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        archive_name = index_url.split("/")[-1].split("?")[0] or "index.tar.gz"
        archive_file = tmp_path / archive_name

        download_with_resume(index_url, archive_file, expected_sha256)

        extract_stage = tmp_path / "extracted"
        safe_extract_archive(archive_file, extract_stage)

        # Locate manifest inside extracted archive
        extracted_manifest = list(extract_stage.glob("**/manifest.json"))
        if not extracted_manifest:
            raise RuntimeError("Index archive does not contain a valid manifest.json")

        source_index_dir = extracted_manifest[0].parent

        # Atomic directory swap
        target_dir.parent.mkdir(parents=True, exist_ok=True)
        swap_backup = target_dir.parent / f"{target_dir.name}.old"
        if target_dir.exists():
            shutil.move(str(target_dir), str(swap_backup))

        shutil.move(str(source_index_dir), str(target_dir))
        if swap_backup.exists():
            shutil.rmtree(swap_backup, ignore_errors=True)

        logger.info(f"Successfully unpacked index to {target_dir}")
        return True


def main() -> None:
    """CLI entrypoint for standalone index fetch."""
    parser = argparse.ArgumentParser(description="Fetch and unpack RegulatorIQ index archive.")
    parser.add_argument("--url", required=True, help="Archive download URL")
    parser.add_argument("--dest", default=str(INDEX_BASE_DIR), help="Target index directory")
    parser.add_argument("--sha256", default=None, help="Expected SHA256 checksum")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        ok = fetch_index_archive(args.url, Path(args.dest), args.sha256)
        sys.exit(0 if ok else 1)
    except Exception as e:
        logger.error(f"Index fetch failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
