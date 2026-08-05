from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.database import SessionLocal, init_db  # noqa: E402
from app.formal_pattern_evidence_verification import (  # noqa: E402
    REVIEWER,
    execute_batch,
    inspect_batch,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify only frozen evidence from verified formal patterns",
    )
    parser.add_argument("--reviewer", default=REVIEWER)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if args.execute:
        init_db()
    db = SessionLocal()
    try:
        result = (
            execute_batch(db, reviewer=args.reviewer)
            if args.execute
            else inspect_batch(db, reviewer=args.reviewer)
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0 if result.get("can_execute", False) or args.execute else 2
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
