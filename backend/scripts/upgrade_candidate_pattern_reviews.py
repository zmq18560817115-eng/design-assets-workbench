"""Add candidate review tables and migrate observable legacy snapshots safely."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import candidate_patterns, models  # noqa: E402
from app.database import SessionLocal, init_db  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        print({"dry_run": True, "candidate_count": len(candidate_patterns.load_candidates()), "writes": 0})
        return 0
    init_db()
    with SessionLocal() as db:
        before = db.query(models.LayoutPatternCandidateReviewEvent).count()
        candidate_patterns.ensure_states(db)
        after = db.query(models.LayoutPatternCandidateReviewEvent).count()
        print({"dry_run": False, "legacy_snapshot_events_added": after - before})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
