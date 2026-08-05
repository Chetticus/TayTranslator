# -*- coding: utf-8 -*-
"""
Tạo file ZIP bàn giao mã nguồn (không gồm venv, cache, file zip đích).

Chạy từ thư mục code:
    python export_project_zip.py

File ra: thư mục gốc dự án, tên Tay-Viet-export-YYYYMMDD.zip
"""
from __future__ import annotations

import os
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SKIP_DIRS = frozenset(
    {
        "venv",
        "__pycache__",
        ".git",
        ".pytest_cache",
        ".mypy_cache",
        ".cursor",
        ".idea",
        ".vs",
        "node_modules",
        "dist",
        "build",
        ".eggs",
        ".tox",
        ".ruff_cache",
    }
)
SKIP_FILES = frozenset({".DS_Store", "Thumbs.db"})


def _prune_dirs(dirnames: list[str]) -> None:
    keep: list[str] = []
    for d in dirnames:
        if d in SKIP_DIRS:
            continue
        if d.endswith(".egg-info"):
            continue
        keep.append(d)
    dirnames[:] = keep


def _should_skip_file(path: Path, out_zip: Path) -> bool:
    name = path.name
    if name.endswith(".pyc"):
        return True
    if name in SKIP_FILES:
        return True
    # Không đóng gói file môi trường / bí mật cục bộ
    if name == ".env" or name.startswith(".env."):
        return True
    if name == "config.env":
        return True
    if name.startswith("Tay-Viet-export") and name.endswith(".zip"):
        return True
    try:
        if path.resolve() == out_zip.resolve():
            return True
    except OSError:
        pass
    return False


def build_zip() -> Path:
    stamp = datetime.now().strftime("%Y%m%d")
    out = ROOT / f"Tay-Viet-export-{stamp}.zip"
    if out.exists():
        out.unlink()

    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for dirpath, dirnames, filenames in os.walk(ROOT, topdown=True):
            _prune_dirs(dirnames)
            for fn in filenames:
                fp = Path(dirpath) / fn
                if _should_skip_file(fp, out):
                    continue
                arc = fp.relative_to(ROOT).as_posix()
                zf.write(fp, arc)
    return out


if __name__ == "__main__":
    print(build_zip())
