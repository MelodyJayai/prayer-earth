#!/usr/bin/env python3
"""Create a consistent, rotating backup of the private content store."""

from __future__ import annotations

import argparse
import datetime as dt
import shutil
import sqlite3
import tarfile
import tempfile
from pathlib import Path


def backup_once(data_directory: Path, backup_directory: Path) -> Path:
    data_directory = data_directory.resolve()
    backup_directory = backup_directory.resolve()
    db_path = data_directory / "admin.sqlite3"
    media_path = data_directory / "media"
    if not db_path.is_file():
        raise FileNotFoundError(db_path)
    backup_directory.mkdir(parents=True, exist_ok=True)
    backup_directory.chmod(0o700)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    temporary = Path(tempfile.mkdtemp(prefix="prayer-backup-", dir=backup_directory))
    archive_path = backup_directory / f"prayer-earth-{stamp}.tar.gz"
    try:
        snapshot_db = temporary / "admin.sqlite3"
        source = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        target = sqlite3.connect(snapshot_db)
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()
        if media_path.exists():
            shutil.copytree(media_path, temporary / "media", symlinks=False)
        with tarfile.open(archive_path, "w:gz") as archive:
            archive.add(snapshot_db, arcname="admin.sqlite3")
            if (temporary / "media").exists():
                archive.add(temporary / "media", arcname="media")
        archive_path.chmod(0o600)
        return archive_path
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def prune(backup_directory: Path, keep: int) -> None:
    archives = sorted(backup_directory.glob("prayer-earth-*.tar.gz"), reverse=True)
    for path in archives[keep:]:
        path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-directory", type=Path, required=True)
    parser.add_argument("--backup-directory", type=Path, required=True)
    parser.add_argument("--keep", type=int, default=14)
    args = parser.parse_args()
    if args.keep < 1:
        raise SystemExit("--keep must be positive")
    archive = backup_once(args.data_directory, args.backup_directory)
    prune(args.backup_directory, args.keep)
    print(archive)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
