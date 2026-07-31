"""Import a folder-based image library into category-focused repositories.

Dry-run is the default. Add --execute to copy images, call the configured
vision model, and persist results. Re-running is safe because perceptual hashes
are checked inside each repository category.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.database import close_db, init_db  # noqa: E402
from app.ingestion import dry_run_summary, execute_items, prepare_manifest  # noqa: E402

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}


def classify_folder(name: str) -> tuple[str, str]:
    prefix, _, detail = name.partition("-")
    if prefix == "排版":
        return "layout", detail or name
    if prefix == "风格":
        return "style", detail or name
    if prefix in {"实拍", "实拍图"}:
        return "photo", detail or name
    if prefix == "色彩":
        return "color", detail or name
    if prefix == "大促" and "对比" in detail:
        return "layout", detail or name
    if prefix == "大促":
        return "style", detail or name
    return "style", name


def discover(root: Path) -> list[dict]:
    items = []
    for folder in sorted(path for path in root.iterdir() if path.is_dir()):
        category, subcategory = classify_folder(folder.name)
        for path in sorted(folder.rglob("*")):
            if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES:
                items.append(
                    {
                        "path": path,
                        "category": category,
                        "subcategory": subcategory,
                        "folder": folder.name,
                    }
                )
    return items


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "root",
        nargs="?",
        type=Path,
        default=PROJECT_DIR / "小红书内容图片素材库",
    )
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--sample-per-folder", type=int, default=0)
    parser.add_argument(
        "--local-only",
        action="store_true",
        help="Use local heuristic analysis without paid model calls.",
    )
    parser.add_argument("--project-name", default="")
    parser.add_argument(
        "--category", choices=["layout", "style", "color", "photo"]
    )
    args = parser.parse_args()

    if not args.root.exists():
        raise SystemExit(f"素材目录不存在：{args.root}")

    items = discover(args.root)
    if args.category:
        items = [item for item in items if item["category"] == args.category]
    if args.sample_per_folder > 0:
        sampled = []
        folder_counts = Counter()
        for item in items:
            if folder_counts[item["folder"]] >= args.sample_per_folder:
                continue
            sampled.append(item)
            folder_counts[item["folder"]] += 1
        items = sampled
    if args.limit > 0:
        items = items[: args.limit]

    prepared, report = prepare_manifest(
        args.root,
        args.manifest,
        default_source_type="external_reference",
        inferred_items=items,
    )
    if args.project_name:
        for item in prepared:
            item["project_name"] = args.project_name
    summary = dry_run_summary(prepared, report)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if not args.execute:
        return 0 if summary["valid"] else 2
    if not summary["valid"]:
        print("manifest validation failed; execute aborted")
        return 2
    init_db()
    try:
        result = execute_items(prepared, enable_vlm=not args.local_only)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result.get("failed") else 0
    finally:
        close_db()


if __name__ == "__main__":
    raise SystemExit(main())
