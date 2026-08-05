from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.database import SessionLocal, init_db  # noqa: E402
from app.human_confirmed_evidence import execute_repair, inspect_repair  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Import one human-confirmed company evidence image by exact SHA")
    parser.add_argument("--annotation-id", type=int, required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--project-id", type=int, required=True)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--product-category", required=True)
    parser.add_argument("--source-type", default="company_published")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    init_db()
    db = SessionLocal()
    try:
        values = vars(args).copy(); execute = values.pop("execute")
        result = execute_repair(db, **values) if execute else inspect_repair(db, **values)
        result["mode"] = "execute" if execute else "dry-run"
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
