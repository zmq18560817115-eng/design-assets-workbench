"""Preview or create the additive P3 layout-search tables."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import inspect

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app import models  # noqa: E402
from app.database import close_db, engine  # noqa: E402

TABLES = (
    models.RequirementReferenceAnalysis.__table__,
    models.LayoutSearchRun.__table__,
    models.LayoutSearchFeedback.__table__,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Preview P3 search tables; add --execute to create missing tables."
    )
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    existing = set(inspect(engine).get_table_names())
    missing = [table for table in TABLES if table.name not in existing]
    print("待新增表：" + ("、".join(table.name for table in missing) if missing else "无"))
    if not args.execute:
        print("当前为预览模式，数据库未修改；添加 --execute 执行。")
        close_db()
        return 0
    for table in missing:
        table.create(bind=engine, checkfirst=True)
    print(f"升级完成：新增 {len(missing)} 张表；旧表和历史数据未改写。")
    close_db()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
