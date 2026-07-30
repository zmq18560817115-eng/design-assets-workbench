"""Preview or safely add LayoutPattern discovery v2 columns to SQLite."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import inspect, text

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.database import close_db, engine  # noqa: E402


FIELDS = {
    "pattern_code": ("TEXT", ""),
    "layout_signature": ("TEXT", ""),
    "module_structure_json": ("TEXT", "[]"),
    "average_positions_json": ("TEXT", "[]"),
    "required_modules_json": ("TEXT", "[]"),
    "optional_modules_json": ("TEXT", "[]"),
    "suitable_scenes_json": ("TEXT", "[]"),
    "unsuitable_scenes_json": ("TEXT", "[]"),
    "evidence_case_ids_json": ("TEXT", "[]"),
    "evidence_blueprint_ids_json": ("TEXT", "[]"),
    "evidence_count": ("INTEGER", "0"),
    "confidence_level": ("TEXT", "candidate"),
    "discovery_method": ("TEXT", ""),
    "generated_at": ("DATETIME", None),
    "reviewer": ("TEXT", ""),
}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Preview LayoutPattern v2 schema changes; add --execute to apply them."
    )
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    inspector = inspect(engine)
    if "layout_patterns" not in inspector.get_table_names():
        print("layout_patterns 表尚不存在；请先正常启动应用以增量建表。")
        close_db()
        return 0

    existing = {column["name"] for column in inspector.get_columns("layout_patterns")}
    missing = [name for name in FIELDS if name not in existing]
    print(f"待新增字段 {len(missing)} 个：" + ("、".join(missing) if missing else "无"))
    if not args.execute:
        print("当前为预览模式，数据库未修改；添加 --execute 执行。")
        close_db()
        return 0

    with engine.begin() as connection:
        for name in missing:
            field_type, default = FIELDS[name]
            default_clause = "" if default is None else f" DEFAULT '{default}'"
            connection.execute(
                text(
                    f"ALTER TABLE layout_patterns ADD COLUMN {name} "
                    f"{field_type}{default_clause}"
                )
            )
    print(f"升级完成：新增 {len(missing)} 个字段；旧模式和历史数据未改写。")
    close_db()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
