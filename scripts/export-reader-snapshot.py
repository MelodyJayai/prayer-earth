#!/usr/bin/env python3
"""Send only public snapshot files over SSH; never export the data directory."""

import fcntl
import hashlib
import json
import sys
import tarfile
from pathlib import Path, PurePosixPath

SNAPSHOTS = Path("/opt/prayer-earth-trial/snapshots")


def main():
    # Shared with the snapshot systemd unit. The lock is outside current/,
    # which the generator replaces and deletes on each successful refresh.
    with (SNAPSHOTS / "export.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_SH)
        root = (SNAPSHOTS / "current").resolve()
        known = json.load(sys.stdin)
        if not isinstance(known, dict) or len(known) > 20000:
            raise ValueError("invalid known-file manifest")
        manifest = json.loads((root / "manifest.json").read_text())
        files = manifest["files"]
        if len(files) > 20000:
            raise ValueError("snapshot exceeds export limit")
        with tarfile.open(fileobj=sys.stdout.buffer, mode="w|") as archive:
            for name in ["manifest.json", "health.json", *files]:
                relative = PurePosixPath(name)
                if relative.is_absolute() or any(part in (".", "..") for part in relative.parts):
                    raise ValueError("invalid snapshot path")
                source = root / name
                if source.is_symlink() or not source.resolve().is_relative_to(root) or not source.is_file():
                    raise ValueError("snapshot file is not a regular file")
                expected = files.get(name)
                if expected and known.get(name) == expected:
                    continue
                if expected and hashlib.sha256(source.read_bytes()).hexdigest() != expected:
                    raise ValueError("snapshot hash mismatch")
                archive.add(source, arcname=name, recursive=False)


if __name__ == "__main__":
    main()
