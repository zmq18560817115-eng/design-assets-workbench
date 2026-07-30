"""Preview or execute the additive layout-search acceptance migration."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.database import close_db, init_db  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        print(
            "预览：创建 layout_search_ground_truth、layout_search_datasets；补充模式业务适用字段和"
            "参考图哈希、分析器版本、审核字段。添加 --execute 执行。"
        )
        return 0
    try:
        init_db()
        print("升级完成：仅增量建表/建列，既有检索运行与人工反馈未改动。")
        return 0
    finally:
        close_db()


if __name__ == "__main__":
    raise SystemExit(main())
