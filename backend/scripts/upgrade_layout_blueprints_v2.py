r"""Append region-detected V2 layout blueprints without overwriting history.

Preview:
    backend\.venv\Scripts\python.exe backend\scripts\upgrade_layout_blueprints_v2.py

Execute:
    backend\.venv\Scripts\python.exe backend\scripts\upgrade_layout_blueprints_v2.py --execute
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app import crud, models  # noqa: E402
from app.database import SessionLocal, init_db  # noqa: E402


V2_PROMPTS = {
    "layout-blueprint-region-detection-v2",
    "layout-blueprint-template-fallback-v2",
}


def pending_case_ids(db) -> list[int]:
    result = []
    for case in db.query(models.Case).order_by(models.Case.id).all():
        latest = crud.get_latest_layout_blueprint(db, case.id)
        expected = crud.build_layout_blueprint_for_case(case)
        current_modules = (
            json.loads(latest.modules_json or "[]") if latest else []
        )
        if (
            not latest
            or latest.prompt_version not in V2_PROMPTS
            or latest.prompt_version != expected.prompt_version
            or latest.model_name != expected.model_name
            or current_modules != [
                module.model_dump() for module in expected.modules_json
            ]
        ):
            result.append(case.id)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--execute",
        action="store_true",
        help="append V2 blueprints; default is dry-run",
    )
    args = parser.parse_args()
    init_db()
    with SessionLocal() as db:
        case_ids = pending_case_ids(db)
        print(f"pending={len(case_ids)} execute={args.execute}")
        if not args.execute:
            return 0
        created = 0
        failed = []
        for case_id in case_ids:
            case = db.get(models.Case, case_id)
            try:
                payload = crud.build_layout_blueprint_for_case(case)
                crud.create_layout_blueprint(db, case.id, payload)
                created += 1
            except Exception as exc:  # continue other cases, report exact IDs
                db.rollback()
                failed.append((case_id, str(exc)))
        print(f"created={created} failed={len(failed)}")
        for case_id, reason in failed:
            print(f"case={case_id} error={reason}")
        return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
