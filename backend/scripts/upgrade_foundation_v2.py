"""Safely add/backfill LayoutBlueprint v2 and BusinessRequirement foundation fields."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app import models  # noqa: E402
from app.database import SessionLocal, close_db, init_db  # noqa: E402
from app.layout_blueprint import layout_signature  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        print(
            "预览：将增量建列并为缺失的 layout_signature/margins_json "
            "回填；添加 --execute 执行。"
        )
        return 0
    init_db()
    db = SessionLocal()
    changed = 0
    try:
        for item in db.query(models.LayoutBlueprint).all():
            modules = json.loads(item.modules_json or "[]")
            if not item.margins_json:
                item.margins_json = item.margins or "{}"
            if not item.layout_signature:
                item.layout_signature = layout_signature(
                    {
                        "canvas_ratio": item.canvas_ratio,
                        "orientation": item.orientation,
                        "grid_columns": item.grid_columns,
                        "grid_rows": item.grid_rows,
                        "modules_json": modules,
                    }
                )
                changed += 1
        db.commit()
        print(
            f"升级完成：回填 {changed} 条排版蓝图；"
            "旧 Analysis/AnalysisVersion 未改动。"
        )
        return 0
    finally:
        db.close()
        close_db()


if __name__ == "__main__":
    raise SystemExit(main())
