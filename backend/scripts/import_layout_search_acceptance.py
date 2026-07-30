"""Validate an acceptance pack; import only with --execute."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app import models  # noqa: E402
from app.database import SessionLocal, close_db, init_db  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    if payload.get("format") != "layout-search-acceptance-v1":
        raise SystemExit("不支持的验收包格式")
    version = str(payload.get("dataset_version", "")).strip()
    rows = payload.get("ground_truth", [])
    if not version or not rows:
        raise SystemExit("缺少 dataset_version 或 ground_truth")
    if any(row.get("dataset_version") != version for row in rows):
        raise SystemExit("标注版本不一致")
    if any(not row.get("frozen_at") for row in rows):
        raise SystemExit("验收包必须在检索运行前冻结")
    init_db()
    db = SessionLocal()
    try:
        if db.query(models.LayoutSearchGroundTruth).filter(
            models.LayoutSearchGroundTruth.dataset_version == version
        ).first():
            raise SystemExit("目标版本已存在，禁止覆盖")
        for row in rows:
            target = models.LayoutPattern if row["result_type"] == "pattern" else models.Case
            if not db.get(models.BusinessRequirement, row["requirement_id"]):
                raise SystemExit(f"需求 ID 不存在：{row['requirement_id']}")
            if not db.get(target, row["result_id"]):
                raise SystemExit(f"结果 ID 不存在：{row['result_id']}")
        print(f"校验通过：{version}，{len(rows)} 条，不包含图片。")
        if not args.execute:
            print("当前为 dry-run；添加 --execute 才会写入。")
            return 0
        for source in rows:
            values = {key: source.get(key) for key in (
                "requirement_id", "result_type", "result_id",
                "expected_relevance", "reviewer", "reason",
                "dataset_version", "dataset_split", "frozen_at",
            )}
            db.add(models.LayoutSearchGroundTruth(**values))
        db.commit()
        print("导入完成；未覆盖任何既有版本。")
        return 0
    finally:
        db.close()
        close_db()


if __name__ == "__main__":
    raise SystemExit(main())
