"""LayoutBlueprint v2 validation and stable signature generation."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

# 规范模块类型的唯一来源（有序，供 VLM 提示词枚举与校验共用）。
MODULE_TYPE_ORDER = (
    "layout_block", "main_title", "subtitle", "body_text", "product_image", "person_image",
    "scene_image", "selling_point", "feature_list", "parameter_table", "price",
    "logo", "cta", "footnote", "decoration", "background", "other",
)
MODULE_TYPES = set(MODULE_TYPE_ORDER)
OVERLAY_TYPES = {"decoration", "background"}


def validate_canvas_ratio(value: str) -> str:
    value = (value or "").strip()
    match = re.fullmatch(r"(\d+(?:\.\d+)?):(\d+(?:\.\d+)?)", value)
    if not match or float(match.group(1)) <= 0 or float(match.group(2)) <= 0:
        raise ValueError("canvas_ratio 必须是正数比例，例如 3:4")
    return value


def _intersection_ratio(left: dict[str, Any], right: dict[str, Any]) -> float:
    x1 = max(left["x"], right["x"])
    y1 = max(left["y"], right["y"])
    x2 = min(left["x"] + left["width"], right["x"] + right["width"])
    y2 = min(left["y"] + left["height"], right["y"] + right["height"])
    intersection = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    smaller = min(left["width"] * left["height"], right["width"] * right["height"])
    return intersection / smaller if smaller else 0.0


def _contains(container: dict[str, Any], child: dict[str, Any]) -> bool:
    tolerance = 1e-6
    return (
        child["x"] >= container["x"] - tolerance
        and child["y"] >= container["y"] - tolerance
        and child["x"] + child["width"] <= container["x"] + container["width"] + tolerance
        and child["y"] + child["height"] <= container["y"] + container["height"] + tolerance
    )


def validate_modules(modules: list[dict[str, Any]], module_count: int | None) -> None:
    if module_count is not None and module_count != len(modules):
        raise ValueError("module_count 必须与 modules_json 实际模块数一致")
    ids: set[str] = set()
    for index, module in enumerate(modules, 1):
        missing = [
            key for key in ("id", "type", "x", "y", "width", "height")
            if module.get(key) in (None, "")
        ]
        if missing:
            raise ValueError(f"模块 {index} 缺少必要字段: {', '.join(missing)}")
        if module["id"] in ids:
            raise ValueError(f"模块 id 重复: {module['id']}")
        ids.add(module["id"])
        if module["type"] not in MODULE_TYPES:
            raise ValueError(f"模块 {module['id']} 类型不受支持: {module['type']}")
        for key in ("x", "y", "width", "height"):
            value = float(module[key])
            if not 0 <= value <= 1:
                raise ValueError(f"模块 {module['id']} 的 {key} 必须在 0～1 之间")
        if module["width"] <= 0 or module["height"] <= 0:
            raise ValueError(f"模块 {module['id']} 的 width 和 height 必须大于 0")
        if module["x"] + module["width"] > 1.000001:
            raise ValueError(f"模块 {module['id']} 横向超出画布")
        if module["y"] + module["height"] > 1.000001:
            raise ValueError(f"模块 {module['id']} 纵向超出画布")
    for index, left in enumerate(modules):
        if left["type"] in OVERLAY_TYPES:
            continue
        for right in modules[index + 1:]:
            if right["type"] in OVERLAY_TYPES:
                continue
            if left["type"] != right["type"] and (
                _contains(left, right) or _contains(right, left)
            ):
                # Human architecture annotations describe layers: layout
                # blocks contain products, and copy may sit on a product photo.
                # Cross-type containment is hierarchy, not a collision. Same-
                # type duplicates and partial crossings remain strictly gated.
                continue
            if _intersection_ratio(left, right) >= 0.92:
                raise ValueError(f"模块 {left['id']} 与 {right['id']} 存在严重重叠")


def layout_signature(payload: dict[str, Any]) -> str:
    modules = sorted(
        (
            {
                "type": item["type"],
                "x": round(float(item["x"]), 3),
                "y": round(float(item["y"]), 3),
                "width": round(float(item["width"]), 3),
                "height": round(float(item["height"]), 3),
            }
            for item in payload.get("modules_json", [])
        ),
        key=lambda item: (item["y"], item["x"], item["type"]),
    )
    stable = {
        "canvas_ratio": payload.get("canvas_ratio", ""),
        "orientation": payload.get("orientation", ""),
        "grid": [payload.get("grid_columns", 1), payload.get("grid_rows", 1)],
        "modules": modules,
    }
    digest = hashlib.sha256(
        json.dumps(stable, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:20]
    return f"lbp2-{digest}"
