"""L1 合规判定：作品蓝图 × 业务需求 → 客观合规报告。

只判断**可客观核对**的合规性：必需模块是否齐全、是否踩了禁止模块、画布比例 /
方向 / 信息密度是否吻合。不做主观审美评价（配色好坏、专业点评属于 L3，需要 VLM）。
不训练、不落库、不依赖任何外部模型——判据来自公司自己的业务需求定义。

判定分三档：
- ``pass``  ：硬性合规通过，且软性维度也吻合。
- ``warn``  ：硬性合规通过，但画布 / 方向 / 密度与需求不一致。
- ``fail``  ：缺必需模块或命中禁止模块（硬性不合规）。

注意：模块级判定的准确度取决于 AI 拆解识别模块类型的能力；仅启发式拆解时较粗，
配置真实视觉模型后更可靠。画布 / 方向 / 密度判定不受此影响。
"""
from __future__ import annotations

import json


def _json_list(value) -> list:
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(value or "[]")
        return parsed if isinstance(parsed, list) else []
    except (TypeError, ValueError, json.JSONDecodeError):
        return []


def _module_types(modules: list[dict]) -> list[str]:
    ordered: list[str] = []
    for module in modules:
        module_type = module.get("type")
        if module_type and module_type not in ordered:
            ordered.append(module_type)
    return ordered


def _compare(dimension: str, label: str, expected, actual) -> dict:
    expected = (expected or "").strip()
    if not expected:
        return {"dimension": dimension, "label": label, "status": "na", "detail": "需求未指定"}
    matched = (actual or "").strip() == expected
    return {
        "dimension": dimension,
        "label": label,
        "status": "pass" if matched else "warn",
        "detail": "一致" if matched else f"需求 {expected}，作品 {actual or '未知'}",
    }


def evaluate_compliance(work: dict, requirement) -> dict:
    """work: {canvas_ratio, orientation, information_density, modules_json:[{type,...}]}
    requirement: 带 required_modules_json / forbidden_modules_json / canvas_ratio /
    orientation / information_density 的业务需求对象（字段可为 JSON 文本或列表）。"""
    present = _module_types(work.get("modules_json", []))
    present_set = set(present)
    required = _json_list(getattr(requirement, "required_modules_json", []))
    forbidden = _json_list(getattr(requirement, "forbidden_modules_json", []))

    missing_required = [item for item in required if item not in present_set]
    forbidden_present = [item for item in forbidden if item in present_set]

    checks: list[dict] = []
    if required:
        checks.append({
            "dimension": "required_modules",
            "label": "必需模块",
            "status": "fail" if missing_required else "pass",
            "detail": ("缺少：" + "、".join(missing_required)) if missing_required else "齐全",
        })
    if forbidden:
        checks.append({
            "dimension": "forbidden_modules",
            "label": "禁止模块",
            "status": "fail" if forbidden_present else "pass",
            "detail": ("命中禁止：" + "、".join(forbidden_present)) if forbidden_present else "无违规",
        })
    checks.append(_compare("canvas_ratio", "画布比例",
                           getattr(requirement, "canvas_ratio", ""), work.get("canvas_ratio")))
    checks.append(_compare("orientation", "画布方向",
                           getattr(requirement, "orientation", ""), work.get("orientation")))
    checks.append(_compare("information_density", "信息密度",
                           getattr(requirement, "information_density", ""), work.get("information_density")))

    hard_fail = bool(missing_required or forbidden_present)
    soft_warn = any(check["status"] == "warn" for check in checks)
    verdict = "fail" if hard_fail else ("warn" if soft_warn else "pass")

    return {
        "verdict": verdict,
        "compliant": not hard_fail,
        "missing_required": missing_required,
        "forbidden_present": forbidden_present,
        "checks": checks,
        "work": {
            "canvas_ratio": work.get("canvas_ratio", ""),
            "orientation": work.get("orientation", ""),
            "information_density": work.get("information_density", ""),
            "module_types": sorted(present_set),
        },
        "summary": _summary(verdict, missing_required, forbidden_present, checks),
    }


def _summary(verdict, missing_required, forbidden_present, checks) -> str:
    if verdict == "fail":
        parts = []
        if missing_required:
            parts.append("缺必需模块 " + "、".join(missing_required))
        if forbidden_present:
            parts.append("踩禁止模块 " + "、".join(forbidden_present))
        return "不合规：" + "；".join(parts)
    if verdict == "warn":
        mismatches = [c["label"] for c in checks if c["status"] == "warn"]
        return "基本合规，但 " + "、".join(mismatches) + " 与需求不一致"
    return "合规：必需/禁止模块与画布结构均符合需求"
