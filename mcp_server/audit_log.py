"""Safe, append-only writer for output/audit_trail.json.

The backend and the MCP server both append to the same file. Every write takes a
cross-process lock and replaces the file atomically, so a reader never sees a
half-written file. If the file can't be read, it is NEVER treated as empty:
the entry goes to a side file (audit_trail.recovery.jsonl) instead, so no
history is ever overwritten.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

LOCK_STALE_SECONDS = 15


class _FileLock:
    def __init__(self, path: Path):
        self.path = path

    def __enter__(self):
        deadline = time.monotonic() + 10
        while True:
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode())
                os.close(fd)
                return self
            except FileExistsError:
                try:  # clear a lock left behind by a crashed process
                    if time.time() - self.path.stat().st_mtime > LOCK_STALE_SECONDS:
                        self.path.unlink(missing_ok=True)
                        continue
                except FileNotFoundError:
                    continue
                if time.monotonic() > deadline:
                    raise TimeoutError(f"Could not lock {self.path}")
                time.sleep(0.02)

    def __exit__(self, *exc):
        self.path.unlink(missing_ok=True)


def _read(path: Path) -> list | None:
    """The current log, or None if it can't be read (never guess 'empty')."""
    if not path.exists():
        return []
    for _ in range(5):
        try:
            data = json.loads(path.read_text("utf-8"))
            return data if isinstance(data, list) else None
        except (json.JSONDecodeError, OSError):
            time.sleep(0.05)
    return None


def append(path: Path, entry: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with _FileLock(path.with_suffix(".lock")):
        log = _read(path)
        if log is None:
            with open(path.with_name("audit_trail.recovery.jsonl"), "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, default=str) + "\n")
            return
        log.append(entry)
        tmp = path.with_suffix(f".tmp{os.getpid()}")
        tmp.write_text(json.dumps(log, indent=2, default=str), "utf-8")
        for _ in range(20):  # Windows: another process may briefly hold the file open
            try:
                os.replace(tmp, path)
                return
            except PermissionError:
                time.sleep(0.05)
        tmp.unlink(missing_ok=True)
        with open(path.with_name("audit_trail.recovery.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")
