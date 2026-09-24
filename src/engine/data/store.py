"""Append-only CSV archive.

Captured lines and predictions are immutable: rows are only ever appended.
CSV (not Parquet) is used for the archive so every capture is a readable,
reviewable git diff; processed/analytic copies go to Parquet/DuckDB.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable, Mapping, Sequence


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


def read_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))
