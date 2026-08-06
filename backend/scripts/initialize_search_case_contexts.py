"""Initialize only the current production-searchable case scope; dry-run by default."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.case_business_context import initialize_contexts, preview_initialization  # noqa: E402
from app.database import SessionLocal, init_db  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    init_db()
    db = SessionLocal()
    try:
        result = initialize_contexts(db) if args.execute else preview_initialization(db)
        print(json.dumps(result, ensure_ascii=False, default=str, indent=2))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
