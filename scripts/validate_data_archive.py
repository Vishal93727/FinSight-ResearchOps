#!/usr/bin/env python3
"""Reject unsafe app-data tar archives before any extraction is attempted."""
from __future__ import annotations

import argparse
import tarfile
from pathlib import PurePosixPath


def validate(path: str, *, max_members: int = 1_000_000, max_bytes: int = 250 * 1024**3) -> tuple[int, int]:
    files = 0
    total_bytes = 0
    member_count = 0
    with tarfile.open(path, mode="r:gz") as archive:
        for member in archive:
            member_count += 1
            if member_count > max_members:
                raise ValueError(f"archive exceeds the {max_members} member safety limit")
            name = member.name.replace("\\", "/")
            candidate = PurePosixPath(name)
            if candidate.is_absolute() or ".." in candidate.parts:
                raise ValueError(f"unsafe archive path: {member.name!r}")
            if member.issym() or member.islnk() or member.isdev() or member.isfifo():
                raise ValueError(f"unsupported special archive member: {member.name!r}")
            if not (member.isfile() or member.isdir()):
                raise ValueError(f"unsupported archive member type: {member.name!r}")
            files += int(member.isfile())
            total_bytes += max(0, member.size)
            if total_bytes > max_bytes:
                raise ValueError(f"archive exceeds the {max_bytes} byte uncompressed safety limit")
    return files, total_bytes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive")
    parser.add_argument("--max-members", type=int, default=1_000_000)
    parser.add_argument("--max-bytes", type=int, default=250 * 1024**3)
    args = parser.parse_args()
    if args.max_members < 1 or args.max_bytes < 1:
        parser.error("safety limits must be positive")
    try:
        count, size = validate(args.archive, max_members=args.max_members, max_bytes=args.max_bytes)
    except (OSError, tarfile.TarError, ValueError) as exc:
        parser.error(str(exc))
    print(f"Archive members validated: {count} files, {size} uncompressed bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
