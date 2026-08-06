"""Prepare the fixed real-search acceptance queue. Dry-run is the default."""
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import real_search_acceptance  # noqa: E402
from app.database import SessionLocal, init_db  # noqa: E402


def integrity(path: Path) -> str:
    with sqlite3.connect(path) as connection:
        return str(connection.execute("PRAGMA integrity_check").fetchone()[0])


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    database = ROOT / "design_assets.db"
    init_db()
    with SessionLocal() as db:
        if not args.execute:
            print(json.dumps(real_search_acceptance.preview(db), ensure_ascii=False, indent=2, default=str))
            return 0
        before = integrity(database)
        if before != "ok":
            raise SystemExit(f"SQLite integrity check failed: {before}")
        backup_dir = ROOT / "backups"
        backup_dir.mkdir(exist_ok=True)
        backup = backup_dir / f"design-assets-before-real-search-{datetime.now():%Y%m%d-%H%M%S}.db"
        shutil.copy2(database, backup)
        result = real_search_acceptance.prepare(db)
        after = integrity(database)
        if after != "ok":
            raise SystemExit(f"SQLite integrity check failed after write: {after}")
        print(json.dumps({"backup": str(backup), "integrity_before": before, "integrity_after": after, **result}, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
