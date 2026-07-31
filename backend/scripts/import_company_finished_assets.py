"""Import a diverse sample of company-finished design assets by business line.

The script is a dry run by default. Use --execute to copy and analyze images.
Each top-level folder becomes one business-line project. Sampling uses
perceptual-hash diversity so near-identical exports do not dominate the profile.
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app import config, imagehash, vlm  # noqa: E402
from app.database import close_db, init_db  # noqa: E402
from app.sampling import color_sample  # noqa: E402
from app.ingestion import dry_run_summary, execute_items, prepare_manifest  # noqa: E402

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


def _hash_int(path: Path) -> int | None:
    try:
        value = imagehash.dhash(str(path))
        return int(value, 16)
    except Exception:
        return None


def _distance(left: int, right: int) -> int:
    return (left ^ right).bit_count()


def diverse_sample(paths: list[Path], limit: int) -> list[Path]:
    """Deterministically choose visually diverse images with a farthest-first pass."""
    if limit <= 0 or len(paths) <= limit:
        return paths
    candidates = [(path, _hash_int(path)) for path in paths]
    valid = [(path, value) for path, value in candidates if value is not None]
    if not valid:
        step = (len(paths) - 1) / max(1, limit - 1)
        return [paths[round(index * step)] for index in range(limit)]

    # Start near the middle of the sorted folder to avoid filename-prefix bias.
    chosen = [valid[len(valid) // 2]]
    remaining = [item for item in valid if item != chosen[0]]
    while remaining and len(chosen) < limit:
        best = max(
            remaining,
            key=lambda item: min(
                _distance(item[1], selected[1]) for selected in chosen
            ),
        )
        chosen.append(best)
        remaining.remove(best)
    return [path for path, _ in chosen]


def discover(
    root: Path,
    sample_per_line: int,
    category: str = "layout",
    sampling: str = "diverse",
) -> list[dict]:
    items: list[dict] = []
    for folder in sorted(path for path in root.iterdir() if path.is_dir()):
        paths = sorted(
            path
            for path in folder.rglob("*")
            if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
        )
        selected = (
            color_sample(paths, sample_per_line)
            if sampling == "color"
            else [(path, None) for path in diverse_sample(paths, sample_per_line)]
        )
        for path, score in selected:
            items.append(
                {
                    "path": path,
                    "business_line": folder.name,
                    "category": category,
                    "subcategory": f"公司成品·{category}",
                    "folder_total": len(paths),
                    "sampling_score": score,
                }
            )
    return items


def confirm_categories(
    items: list[dict],
    *,
    expected_category: str,
    minimum_confidence: int,
    timeout_seconds: float,
) -> list[dict]:
    """Use the configured vision model as a safety gate before category import."""
    confirmed: list[dict] = []
    for index, item in enumerate(items, 1):
        path: Path = item["path"]
        mime = mimetypes.guess_type(path.name)[0] or "image/png"
        try:
            suggestion = vlm.suggest_asset_category(
                path.read_bytes(),
                mime,
                timeout_seconds=timeout_seconds,
            )
            item["model_suggestion"] = suggestion
            accepted = (
                suggestion["category"] == expected_category
                and suggestion["confidence"] >= minimum_confidence
            )
            state = "accepted" if accepted else "rejected"
            print(
                f"[model {index}/{len(items)}] {state}: "
                f"{item['business_line']}/{path.name} -> "
                f"{suggestion['category']} {suggestion['confidence']}%",
                flush=True,
            )
            if accepted:
                confirmed.append(item)
        except Exception as exc:  # noqa: BLE001
            item["model_error"] = str(exc)
            print(
                f"[model {index}/{len(items)}] failed: "
                f"{item['business_line']}/{path.name}: {exc}",
                flush=True,
            )
    return confirmed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--sample-per-line", type=int, default=10)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--local-only", action="store_true")
    parser.add_argument("--business-line", default="")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument(
        "--category",
        choices=("layout", "style", "color", "photo"),
        default="layout",
    )
    parser.add_argument(
        "--sampling",
        choices=("diverse", "color"),
        default="diverse",
        help="Use color to rank palette-learning candidates; preview before import.",
    )
    parser.add_argument(
        "--confirm-with-model",
        action="store_true",
        help=(
            "Ask the configured vision model to confirm the primary learning "
            "category before preview or import."
        ),
    )
    parser.add_argument(
        "--minimum-confidence",
        type=int,
        default=80,
        help="Minimum model confidence required by --confirm-with-model.",
    )
    parser.add_argument(
        "--model-timeout",
        type=float,
        default=60,
        help="Per-image model confirmation timeout in seconds.",
    )
    args = parser.parse_args()

    if not args.root.exists():
        raise SystemExit(f"素材目录不存在：{args.root}")
    items = discover(
        args.root,
        args.sample_per_line,
        category=args.category,
        sampling=args.sampling,
    )
    if args.business_line:
        items = [
            item
            for item in items
            if item["business_line"] == args.business_line
        ]
    if args.execute and args.confirm_with_model and not args.local_only:
        before = len(items)
        items = confirm_categories(
            items,
            expected_category=args.category,
            minimum_confidence=max(0, min(args.minimum_confidence, 100)),
            timeout_seconds=max(5, args.model_timeout),
        )
        print(f"模型确认通过：{len(items)}/{before}")
    for item in items:
        item["project_name"] = f"公司成品·{item['business_line']}"
        item["product_category"] = ""
    prepared, report = prepare_manifest(
        args.root,
        args.manifest,
        default_source_type="company_published",
        inferred_items=items,
    )
    summary = dry_run_summary(prepared, report)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if not args.execute:
        return 0 if summary["valid"] else 2
    if not summary["valid"]:
        print("manifest validation failed; execute aborted")
        return 2
    init_db()
    try:
        result = execute_items(
            prepared,
            concurrency=max(1, min(args.workers, 5)),
            enable_vlm=not args.local_only,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result.get("failed") else 0
    finally:
        close_db()


if __name__ == "__main__":
    raise SystemExit(main())
