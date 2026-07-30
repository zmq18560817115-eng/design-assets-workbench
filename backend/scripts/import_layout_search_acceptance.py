"""Validate an acceptance pack; import only with --execute."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.acceptance_pack import import_pack  # noqa: E402
from app.database import SessionLocal, close_db, init_db  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    init_db()
    db = SessionLocal()
    try:
        result = import_pack(db, payload, execute=args.execute)
        print(
            f"校验通过：{result['dataset_version']}，"
            f"{result['annotation_count']} 条，不包含图片。"
        )
        print("当前为 dry-run；添加 --execute 才会写入。"
              if result["dry_run"] else "导入完成；未覆盖任何既有版本。")
        return 0
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    finally:
        db.close()
        close_db()


if __name__ == "__main__":
    raise SystemExit(main())
