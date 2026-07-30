"""Export Ground Truth and evaluation JSON without image data."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.database import SessionLocal, close_db, init_db  # noqa: E402
from app.acceptance_pack import export_pack  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset_version")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    init_db()
    db = SessionLocal()
    try:
        payload = export_pack(db, args.dataset_version)
        args.output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        print(f"已导出 {len(payload['ground_truth'])} 条标注；不包含图片。")
        return 0
    finally:
        db.close()
        close_db()


if __name__ == "__main__":
    raise SystemExit(main())
