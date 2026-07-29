"""Backfill normalized layout blueprints without changing existing case data.

Dry-run by default. Add --execute to create version 1 only for cases that do
not already have a layout blueprint.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app import crud, models  # noqa: E402
from app.database import SessionLocal, close_db, init_db  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--case-id", type=int, default=0)
    args = parser.parse_args()

    init_db()
    db = SessionLocal()
    try:
        query = (
            db.query(models.Case)
            .outerjoin(
                models.LayoutBlueprint,
                models.LayoutBlueprint.case_id == models.Case.id,
            )
            .filter(models.LayoutBlueprint.id.is_(None))
            .order_by(models.Case.id)
        )
        if args.case_id:
            query = query.filter(models.Case.id == args.case_id)
        if args.limit > 0:
            query = query.limit(args.limit)
        cases = query.all()
        print(f"待回填案例：{len(cases)}")
        for case in cases:
            print(f"- #{case.id} {case.name}")
        if not args.execute:
            print("当前为预览模式；添加 --execute 后才会创建排版骨架。")
            return 0

        created = 0
        failed = 0
        for case in cases:
            try:
                payload = crud.build_layout_blueprint_for_case(case)
                crud.create_layout_blueprint(db, case.id, payload)
                created += 1
                print(f"[created] #{case.id}", flush=True)
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                failed += 1
                print(f"[failed] #{case.id}: {exc}", flush=True)
        print(f"完成：created={created}, failed={failed}")
        return 1 if failed else 0
    finally:
        db.close()
        close_db()


if __name__ == "__main__":
    raise SystemExit(main())
