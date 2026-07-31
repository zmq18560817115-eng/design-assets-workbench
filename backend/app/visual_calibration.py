"""Real-image calibration contracts; never reads sealed holdout answers."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image
import httpx

from . import config, vlm
from .layout_blueprint import MODULE_TYPE_ORDER


SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
ERROR_CODES = {
    "PRODUCT_MISSED",
    "PRODUCT_BOX_INACCURATE",
    "PRIMARY_TEXT_MISSED",
    "LAYOUT_MODULE_MISSED",
    "LAYOUT_MODULE_TYPE_ERROR",
    "MODULE_OUT_OF_BOUNDS",
    "MODULE_OVERLAP_INVALID",
    "OUTPUT_SCHEMA_INVALID",
    "MODEL_TIMEOUT",
    "MODEL_PROVIDER_ERROR",
    "UNKNOWN_ANALYSIS_ERROR",
}

DEFAULT_THRESHOLDS = {
    "region_iou": 0.5,
    "product_iou": 0.45,
    "maximum_sibling_overlap_ratio": 0.35,
    "duplicate_module_iou": 0.9,
}

CALIBRATION_GATES = {
    "task_success_rate_min": 0.95,
    "schema_valid_rate_min": 0.98,
    "product_detection_rate_min": 0.95,
    "primary_text_detection_rate_min": 0.90,
    "layout_module_recall_min": 0.90,
    "invalid_overlap_rate_max": 0.05,
    "timeout_rate_max": 0.05,
    "severe_regression_count_max": 0,
}


@dataclass(frozen=True)
class CalibrationPaths:
    project_root: Path
    annotated_root: Path
    output_root: Path
    database_path: Path


def locate_annotated_root(project_root: Path) -> tuple[Path, str]:
    preferred = project_root / "Untitled1"
    if preferred.is_dir():
        return preferred, "Untitled1"
    compatible = project_root / "消毒柜"
    if compatible.is_dir():
        return compatible, "消毒柜 (Untitled1 export alias)"
    raise FileNotFoundError("未找到 Untitled1 或已确认的消毒柜导出目录")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def perceptual_hash(path: Path, size: int = 16) -> str:
    with Image.open(path) as source:
        image = source.convert("L").resize((size, size))
        pixels = list(image.getdata())
    average = sum(pixels) / len(pixels)
    bits = "".join("1" if value >= average else "0" for value in pixels)
    return f"{int(bits, 2):0{size * size // 4}x}"


def _hamming(left: str, right: str) -> int:
    return (int(left, 16) ^ int(right, 16)).bit_count()


def _legacy_rows(database_path: Path) -> dict[str, dict[str, Any]]:
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    try:
        exists = connection.execute(
            "select 1 from sqlite_master where type='table' "
            "and name='disinfection_annotations'"
        ).fetchone()
        if not exists:
            return {}
        # regions_json is deliberately selected only for calibration rows.
        metadata = connection.execute(
            "select id, annotated_image_path, original_image_path, source_sha256, "
            "product_category, project_key, status, dataset_split, reviewer, "
            "reviewed_at, annotation_version, created_at, canvas_width, canvas_height "
            "from disinfection_annotations"
        ).fetchall()
        rows: dict[str, dict[str, Any]] = {}
        for item in metadata:
            data = dict(item)
            name = Path(data["annotated_image_path"]).name
            if data["dataset_split"] == "calibration" and data["status"] == "verified":
                region_row = connection.execute(
                    "select regions_json from disinfection_annotations where id=?",
                    (data["id"],),
                ).fetchone()
                data["regions"] = json.loads(region_row[0] or "[]")
            rows[name.casefold()] = data
        return rows
    finally:
        connection.close()


def _pixel_region(region: dict[str, Any], width: int, height: int) -> dict[str, Any]:
    normalized = {
        key: round(float(region[key]), 6)
        for key in ("x", "y", "width", "height")
    }
    pixels = {
        "x": round(normalized["x"] * width),
        "y": round(normalized["y"] * height),
        "width": round(normalized["width"] * width),
        "height": round(normalized["height"] * height),
    }
    return {
        "id": str(region.get("id") or ""),
        "type": str(region.get("semantic_type") or region.get("type") or "other"),
        "normalized": normalized,
        "pixels": pixels,
    }


def _ground_truth(row: dict[str, Any], asset_id: str) -> dict[str, Any]:
    if row.get("dataset_split") != "calibration":
        raise PermissionError("禁止读取 Holdout Ground Truth")
    if row.get("status") != "verified":
        raise ValueError("只有 verified 标注可以生成 Ground Truth")
    width, height = int(row["canvas_width"]), int(row["canvas_height"])
    converted = [
        _pixel_region(region, width, height) for region in row.get("regions", [])
    ]
    products = [item for item in converted if item["type"] == "product_image"]
    texts = [item for item in converted if item["type"] == "main_text"]
    modules = [item for item in converted if item["type"] == "layout_block"]
    return {
        "asset_id": asset_id,
        "canvas": {"width": width, "height": height},
        "product_regions": products,
        "primary_text_regions": texts,
        "layout_modules": modules,
        "containment_relations": [],
        "allowed_overlap_relations": [],
        "review_status": "verified",
        "reviewer": row.get("reviewer") or "",
        "review_reason": "设计负责人已在消毒柜标注工作台确认彩框拆解",
        "annotation_version": f"human-color-box-v{row.get('annotation_version') or 1}",
    }


def build_manifest(paths: CalibrationPaths) -> dict[str, Any]:
    legacy = _legacy_rows(paths.database_path)
    images = sorted(
        (
            path
            for path in paths.annotated_root.rglob("*")
            if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
        ),
        key=lambda item: item.relative_to(paths.annotated_root).as_posix().casefold(),
    )
    imported_at = dt.datetime.now(dt.UTC).isoformat()
    assets: list[dict[str, Any]] = []
    hashes: set[str] = set()
    for path in images:
        sha = file_sha256(path)
        if sha in hashes:
            continue
        hashes.add(sha)
        with Image.open(path) as image:
            width, height = image.size
        row = legacy.get(path.name.casefold(), {})
        split = row.get("dataset_split") or "unassigned"
        status = row.get("status") or "draft"
        asset_id = f"untitled1-{sha[:16]}"
        item = {
            "asset_id": asset_id,
            "filename": path.name,
            "relative_path": path.relative_to(paths.project_root).as_posix(),
            "sha256": sha,
            "perceptual_hash": perceptual_hash(path),
            "width": width,
            "height": height,
            "product_category": row.get("product_category") or "消毒柜",
            "project_category": row.get("project_key") or "Untitled1",
            "annotation_status": status,
            "dataset_split": split,
            "original_relative_path": "",
            "imported_at": imported_at,
        }
        original = str(row.get("original_image_path") or "")
        if original:
            original_path = Path(original)
            try:
                item["original_relative_path"] = original_path.relative_to(
                    paths.project_root
                ).as_posix()
            except ValueError:
                item["original_relative_path"] = original_path.as_posix()
        if split == "calibration" and status == "verified":
            item["ground_truth"] = _ground_truth(row, asset_id)
        assets.append(item)

    # Near duplicates are required to stay within one split.
    for index, left in enumerate(assets):
        for right in assets[index + 1:]:
            if _hamming(left["perceptual_hash"], right["perceptual_hash"]) <= 4:
                real_splits = {
                    value for value in (left["dataset_split"], right["dataset_split"])
                    if value in {"calibration", "holdout"}
                }
                if len(real_splits) > 1:
                    raise ValueError(
                        f"近重复图片跨 split: {left['filename']} / {right['filename']}"
                    )
    counts = {
        key: sum(item["dataset_split"] == key for item in assets)
        for key in ("calibration", "holdout", "unassigned")
    }
    verified = sum(item["annotation_status"] == "verified" for item in assets)
    return {
        "manifest_version": "untitled1-visual-calibration-v1",
        "source_directory": paths.annotated_root.relative_to(
            paths.project_root
        ).as_posix(),
        "source_alias": locate_annotated_root(paths.project_root)[1],
        "generated_at": imported_at,
        "product_category": "消毒柜",
        "total_scanned": len(assets),
        "verified_count": verified,
        "split_counts": counts,
        "holdout_sealed": True,
        "holdout_ground_truth_included": False,
        "assets": assets,
    }


def write_manifest(paths: CalibrationPaths) -> Path:
    paths.output_root.mkdir(parents=True, exist_ok=True)
    target = paths.output_root / "untitled1-manifest.json"
    target.write_text(
        json.dumps(build_manifest(paths), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return target


def _rect(region: dict[str, Any]) -> dict[str, float]:
    if "normalized" in region:
        region = region["normalized"]
    return {key: float(region[key]) for key in ("x", "y", "width", "height")}


def region_iou(left: dict[str, Any], right: dict[str, Any]) -> float:
    a, b = _rect(left), _rect(right)
    ax2, ay2 = a["x"] + a["width"], a["y"] + a["height"]
    bx2, by2 = b["x"] + b["width"], b["y"] + b["height"]
    intersection = max(0, min(ax2, bx2) - max(a["x"], b["x"])) * max(
        0, min(ay2, by2) - max(a["y"], b["y"])
    )
    union = a["width"] * a["height"] + b["width"] * b["height"] - intersection
    return intersection / union if union else 0.0


def containment_ratio(inner: dict[str, Any], outer: dict[str, Any]) -> float:
    a, b = _rect(inner), _rect(outer)
    intersection = max(
        0, min(a["x"] + a["width"], b["x"] + b["width"]) - max(a["x"], b["x"])
    ) * max(
        0, min(a["y"] + a["height"], b["y"] + b["height"]) - max(a["y"], b["y"])
    )
    area = a["width"] * a["height"]
    return intersection / area if area else 0.0


def _valid_region(region: dict[str, Any]) -> bool:
    try:
        value = _rect(region)
    except (KeyError, TypeError, ValueError):
        return False
    return (
        value["x"] >= 0 and value["y"] >= 0
        and value["width"] > 0 and value["height"] > 0
        and value["x"] + value["width"] <= 1.000001
        and value["y"] + value["height"] <= 1.000001
    )


def _best_matches(
    truth: list[dict[str, Any]],
    predicted: list[dict[str, Any]],
    threshold: float,
) -> tuple[int, list[float]]:
    used: set[int] = set()
    scores: list[float] = []
    for expected in truth:
        choices = [
            (region_iou(expected, candidate), index)
            for index, candidate in enumerate(predicted)
            if index not in used
        ]
        score, index = max(choices, default=(0.0, -1))
        if score >= threshold:
            used.add(index)
            scores.append(score)
    return len(scores), scores


def validate_prediction(
    parsed: dict[str, Any],
    ground_truth: dict[str, Any],
    *,
    thresholds: dict[str, float] | None = None,
) -> dict[str, Any]:
    rules = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    errors: list[str] = []
    details: list[dict[str, Any]] = []
    modules = parsed.get("blueprint_modules")
    if not isinstance(modules, list):
        return {
            "schema_valid": False,
            "error_codes": ["OUTPUT_SCHEMA_INVALID"],
            "validation_errors": ["blueprint_modules 必须是数组"],
            "metrics": {},
        }
    normalized_modules = []
    for index, module in enumerate(modules):
        if not isinstance(module, dict) or module.get("type") not in MODULE_TYPE_ORDER:
            errors.append("LAYOUT_MODULE_TYPE_ERROR")
            details.append({"index": index, "reason": "非法模块类型"})
            continue
        if not _valid_region(module):
            errors.append("MODULE_OUT_OF_BOUNDS")
            details.append({"index": index, "reason": "模块坐标越界或宽高非法"})
            continue
        normalized_modules.append(module)
    products = [row for row in normalized_modules if row.get("type") == "product_image"]
    texts = [
        row for row in normalized_modules
        if row.get("type") in {"main_title", "subtitle", "body_text", "selling_point"}
    ]
    if ground_truth["product_regions"] and not products:
        errors.append("PRODUCT_MISSED")
    product_hits, product_ious = _best_matches(
        ground_truth["product_regions"], products, rules["product_iou"]
    )
    if products and product_hits < len(ground_truth["product_regions"]):
        errors.append("PRODUCT_BOX_INACCURATE")
    text_hits, _ = _best_matches(
        ground_truth["primary_text_regions"], texts, rules["region_iou"]
    )
    if ground_truth["primary_text_regions"] and not text_hits:
        errors.append("PRIMARY_TEXT_MISSED")
    layout_hits, _ = _best_matches(
        ground_truth["layout_modules"], normalized_modules, rules["region_iou"]
    )
    if layout_hits < len(ground_truth["layout_modules"]):
        errors.append("LAYOUT_MODULE_MISSED")

    invalid_overlaps = 0
    duplicates = 0
    allowed = {
        tuple(sorted(pair)) for pair in ground_truth.get("allowed_overlap_relations", [])
    }
    for index, left in enumerate(normalized_modules):
        for right in normalized_modules[index + 1:]:
            pair = tuple(sorted((str(left.get("id", "")), str(right.get("id", "")))))
            if pair in allowed:
                continue
            iou = region_iou(left, right)
            if iou >= rules["duplicate_module_iou"] and left.get("type") == right.get("type"):
                duplicates += 1
                invalid_overlaps += 1
            elif (
                containment_ratio(left, right) < 0.9
                and containment_ratio(right, left) < 0.9
                and iou > rules["maximum_sibling_overlap_ratio"]
            ):
                invalid_overlaps += 1
    if invalid_overlaps:
        errors.append("MODULE_OVERLAP_INVALID")
    return {
        "schema_valid": "OUTPUT_SCHEMA_INVALID" not in errors,
        "error_codes": sorted(set(errors)),
        "validation_errors": details,
        "metrics": {
            "product_truth_count": len(ground_truth["product_regions"]),
            "product_hit_count": product_hits,
            "product_mean_iou": round(
                sum(product_ious) / len(product_ious), 4
            ) if product_ious else 0,
            "primary_text_truth_count": len(ground_truth["primary_text_regions"]),
            "primary_text_hit_count": text_hits,
            "layout_truth_count": len(ground_truth["layout_modules"]),
            "layout_hit_count": layout_hits,
            "predicted_module_count": len(normalized_modules),
            "invalid_overlap_count": invalid_overlaps,
            "duplicate_module_count": duplicates,
        },
    }


def run_model_once(
    image_path: Path,
    *,
    additional_instructions: str = "",
    timeout_seconds: float = 300,
) -> tuple[dict[str, Any], str]:
    mime = {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }.get(image_path.suffix.lower(), "image/png")
    return vlm.analyze_image_with_trace(
        image_path.read_bytes(),
        mime,
        {"palette": [], "tone": "", "grid_columns": "", "modules": "", "margins": ""},
        asset_category="layout",
        additional_instructions=additional_instructions,
        timeout_seconds=timeout_seconds,
    )


def classify_exception(error: Exception) -> str:
    if isinstance(error, (httpx.TimeoutException, TimeoutError)):
        return "MODEL_TIMEOUT"
    if isinstance(error, (httpx.HTTPError, ConnectionError)):
        return "MODEL_PROVIDER_ERROR"
    if isinstance(error, (json.JSONDecodeError, KeyError, TypeError, ValueError)):
        return "OUTPUT_SCHEMA_INVALID"
    return "UNKNOWN_ANALYSIS_ERROR"
