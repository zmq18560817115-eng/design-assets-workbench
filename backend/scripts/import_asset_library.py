"""Import a folder-based image library into category-focused repositories.

Dry-run is the default. Add --execute to copy images, call the configured
vision model, and persist results. Re-running is safe because perceptual hashes
are checked inside each repository category.
"""
from __future__ import annotations

import argparse
import shutil
import sys
import uuid
from collections import Counter
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from app import crud, imagehash, models  # noqa: E402
from app.agents import run_pipeline  # noqa: E402
from app.database import SessionLocal, close_db, init_db  # noqa: E402

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


def import_one(
    item: dict,
    *,
    enable_vlm: bool = True,
    project_id: int | None = None,
) -> str:
    db = SessionLocal()
    copied_path: Path | None = None
    try:
        source: Path = item["path"]
        phash = imagehash.dhash(str(source))
        duplicate = crud.find_duplicate_case_id(
            db, phash, asset_category=item["category"]
        )
        if duplicate:
            if project_id is not None:
                existing = (
                    db.query(models.Case)
                    .filter(models.Case.id == duplicate)
                    .first()
                )
                if existing and existing.project_id != project_id:
                    existing.project_id = project_id
                    db.commit()
                    return "assigned"
            return "skipped"

        stored_name = f"{uuid.uuid4().hex}{source.suffix.lower()}"
        copied_path = BACKEND_DIR / "uploads" / stored_name
        shutil.copy2(source, copied_path)

        result = run_pipeline(
            str(copied_path),
            asset_category=item["category"],
            enable_vlm=enable_vlm,
        )
        image = models.Image(
            url=f"/uploads/{stored_name}",
            filename=source.name,
            source="local_library",
            source_type="internal_reference",
            source_url=str(source),
            rights_note="本地素材库导入",
            visibility="team",
            uploader="local-import",
            phash=phash,
        )
        db.add(image)
        db.flush()
        case = crud.create_case_from_analysis(
            db,
            image,
            result,
            asset_category=item["category"],
            asset_subcategory=item["subcategory"],
        )
        if project_id is not None:
            case.project_id = project_id
            db.commit()
        return "imported"
    except Exception:
        db.rollback()
        if copied_path:
            copied_path.unlink(missing_ok=True)
        raise
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "root",
        nargs="?",
        type=Path,
        default=PROJECT_DIR / "小红书内容图片素材库",
    )
    parser.add_argument("--execute", action="store_true")
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

    by_category = Counter(item["category"] for item in items)
    by_folder = Counter(item["folder"] for item in items)
    print(f"扫描图片：{len(items)}")
    print("一级仓库：" + ", ".join(f"{k}={v}" for k, v in sorted(by_category.items())))
    for folder, count in sorted(by_folder.items()):
        category, subcategory = classify_folder(folder)
        print(f"- {folder}: {count} -> {category}/{subcategory}")

    if not args.execute:
        print("当前为预览模式；确认后添加 --execute 才会调用模型并入库。")
        return 0

    init_db()
    project_id = None
    if args.project_name:
        db = SessionLocal()
        try:
            project = (
                db.query(models.Project)
                .filter(models.Project.name == args.project_name)
                .first()
            )
            if not project:
                project = models.Project(
                    name=args.project_name,
                    description="从本地素材库分层抽样建立的公司黄金项目候选集",
                    status="active",
                    is_gold=True,
                )
                db.add(project)
                db.commit()
                db.refresh(project)
            project_id = project.id
            print(f"归属项目：{project.name} (#{project.id})")
        finally:
            db.close()
    stats = Counter()
    try:
        for index, item in enumerate(items, 1):
            try:
                state = import_one(
                    item,
                    enable_vlm=not args.local_only,
                    project_id=project_id,
                )
                stats[state] += 1
                print(
                    f"[{index}/{len(items)}] {state}: "
                    f"{item['category']}/{item['subcategory']}/{item['path'].name}"
                )
            except Exception as exc:  # noqa: BLE001
                stats["failed"] += 1
                print(f"[{index}/{len(items)}] failed: {item['path'].name}: {exc}")
    finally:
        close_db()
    print("完成：" + ", ".join(f"{k}={v}" for k, v in sorted(stats.items())))
    return 1 if stats["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
