"""Append-only CSV archive.

Captured lines and predictions are immutable: rows are only ever appended.
CSV (not Parquet) is used for the archive so every capture is a readable,
reviewable git diff; processed/analytic copies go to Parquet/DuckDB.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable, Mapping, Sequence

try:
    import fcntl
except ImportError:   # not POSIX; the lock run only ever runs on Linux
    fcntl = None


class SchemaMismatch(RuntimeError):
    pass


def append_rows(path: Path, fieldnames: Sequence[str], rows: Iterable[Mapping]) -> int:
    rows = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists() and path.stat().st_size > 0
    if exists:
        with open(path, newline="") as f:
            header = next(csv.reader(f))
        if list(header) != list(fieldnames):
            raise SchemaMismatch(f"{path}: header {header} != {list(fieldnames)}")
    if not rows:
        return 0
    with open(path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(fieldnames), extrasaction="raise")
        if not exists:
            w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in fieldnames})
    return len(rows)


def append_unique(path: Path, fieldnames: Sequence[str], rows: Iterable[Mapping], key: str
                  ) -> tuple[list[Mapping], list[Mapping]]:
    """append_rows that never writes a second row for the same `key` value (e.g. one prediction per game_id).

    The existing keys are re-read while holding an exclusive lock on the file itself, so two writers on one
    machine cannot both pass the check. Rows whose key is already in the file, or repeats inside `rows`, are
    rejected. Returns (appended, rejected); nothing is raised for a duplicate."""
    rows = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a+", newline="") as f:
        if fcntl is not None:
            fcntl.flock(f, fcntl.LOCK_EX)
        f.seek(0)
        content = list(csv.reader(f))
        if content and list(content[0]) != list(fieldnames):
            raise SchemaMismatch(f"{path}: header {content[0]} != {list(fieldnames)}")
        seen = set()
        if content:
            ki = content[0].index(key)
            seen = {r[ki] for r in content[1:] if len(r) > ki}
        appended, rejected = [], []
        for r in rows:
            k = str(r.get(key))
            if k in seen:
                rejected.append(r)
            else:
                seen.add(k)
                appended.append(r)
        if appended:
            f.seek(0, 2)
            w = csv.DictWriter(f, fieldnames=list(fieldnames), extrasaction="raise")
            if not content:
                w.writeheader()
            for r in appended:
                w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in fieldnames})
            f.flush()
    return appended, rejected


def read_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))
