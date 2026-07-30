"""L2 结构符合度：作品蓝图 vs 公司已确认排版模式 → 偏离度。

判断作品的排版结构"像不像公司已经确认过的模式"。复用模式发现里的
``layout_patterns.structure_similarity``(模块类型 35% / 位置尺寸 35% /
栅格阅读动线 15% / 画布密度 15%),不重造、不训练、不落库。

- ``conforms`` ：与某个已确认模式的相似度 ≥ 阈值(默认 0.72,与模式发现一致)。
- ``deviates`` ：与所有已确认模式都低于阈值(结构较新/较偏)。
- ``na``       ：库里还没有已确认模式可对照。
"""
from __future__ import annotations

import json
from types import SimpleNamespace

from . import layout_patterns

CONFORM_THRESHOLD = 0.72


def _comparable(
    modules_json: str,
    *,
    grid_columns,
    grid_rows,
    reading_flow,
    layout_signature,
    orientation,
    canvas_ratio,
    information_density,
) -> SimpleNamespace:
    """把作品/模式适配成 structure_similarity 需要的鸭子类型对象。"""
    return SimpleNamespace(
        modules_json=modules_json or "[]",
        grid_columns=grid_columns or 1,
        grid_rows=grid_rows or 1,
        reading_flow=reading_flow or "",
        layout_signature=layout_signature or "",
        orientation=orientation or "",
        canvas_ratio=canvas_ratio or "",
        information_density=information_density or "",
    )


def evaluate_conformance(
    work: dict, patterns, *, top_n: int = 3, threshold: float = CONFORM_THRESHOLD
) -> dict:
    """work 为作品蓝图 dict；patterns 为已确认 LayoutPattern 列表。"""
    if not patterns:
        return {
            "verdict": "na",
            "conforms": False,
            "threshold": threshold,
            "best": None,
            "matches": [],
            "summary": "尚无已确认排版模式可对照",
        }

    work_obj = _comparable(
        json.dumps(work.get("modules_json", []), ensure_ascii=False),
        grid_columns=work.get("grid_columns"),
        grid_rows=work.get("grid_rows"),
        reading_flow=work.get("reading_flow"),
        layout_signature=work.get("layout_signature"),
        orientation=work.get("orientation"),
        canvas_ratio=work.get("canvas_ratio"),
        information_density=work.get("information_density"),
    )

    scored: list[dict] = []
    for pattern in patterns:
        pattern_obj = _comparable(
            pattern.average_positions_json or pattern.modules_json or "[]",
            grid_columns=pattern.grid_columns,
            grid_rows=pattern.grid_rows,
            reading_flow=pattern.reading_flow,
            layout_signature=pattern.layout_signature,
            orientation=pattern.orientation,
            canvas_ratio=pattern.canvas_ratio,
            information_density=pattern.information_density,
        )
        components = layout_patterns.structure_similarity(work_obj, pattern_obj)
        scored.append(
            {
                "pattern_id": pattern.id,
                "pattern_name": pattern.name,
                "pattern_code": pattern.pattern_code,
                "similarity": components["total"],
                "components": components,
            }
        )

    scored.sort(key=lambda item: (-item["similarity"], item["pattern_id"]))
    best = scored[0]
    conforms = best["similarity"] >= threshold
    percent = round(best["similarity"] * 100)
    return {
        "verdict": "conforms" if conforms else "deviates",
        "conforms": conforms,
        "threshold": threshold,
        "best": best,
        "matches": scored[:top_n],
        "summary": (
            f"结构贴合已确认模式「{best['pattern_name']}」（{percent}%）"
            if conforms
            else f"与已确认模式偏离较大，最接近「{best['pattern_name']}」（{percent}%）"
        ),
    }
