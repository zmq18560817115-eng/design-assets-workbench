"""拆解保真度分析（P1 的评测脚手架）。

监督信号来自天然的版本链：每个案例的「AI 初版蓝图」(review_status=ai_generated)
与「人工确认终版」(verified) 的差异，就是 AI 拆解错在哪的免费标注。

本模块只读、不落库、不训练任何模型：把 v1→verified 看成一段模块级编辑序列，
按生成路径 / 画布方向分层，算出改动率、类型准确率、增删率等，回答
"AI 拆解最该先修哪一类"。

术语：
- gen_path：初版蓝图的生成路径，从 model_name 前缀推断
  （template / region / model，见 crud.build_initial_layout_blueprint）。
- 编辑操作：retype（类型改）+ added（人工新增）+ dropped（人工删除）。
- edit_rate：编辑操作数 / 终版模块数，越低越好。
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from app import models
from app.layout_blueprint import MODULE_TYPES

IOU_MATCH_THRESHOLD = 0.3


def gen_path(model_name: str | None) -> str:
    name = model_name or ""
    if name.startswith("template-fallback"):
        return "template"
    if name.startswith("region-detection-fallback"):
        return "region"
    return "model"


def _modules(blueprint: models.LayoutBlueprint) -> list[dict]:
    try:
        parsed = json.loads(blueprint.modules_json or "[]")
        return parsed if isinstance(parsed, list) else []
    except (TypeError, ValueError, json.JSONDecodeError):
        return []


def _iou(a: dict, b: dict) -> float:
    ax, ay = float(a.get("x", 0)), float(a.get("y", 0))
    bx, by = float(b.get("x", 0)), float(b.get("y", 0))
    aw, ah = float(a.get("width", 0)), float(a.get("height", 0))
    bw, bh = float(b.get("width", 0)), float(b.get("height", 0))
    ix = max(0.0, min(ax + aw, bx + bw) - max(ax, bx))
    iy = max(0.0, min(ay + ah, by + bh) - max(ay, by))
    inter = ix * iy
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


def _match(x_modules: list[dict], y_modules: list[dict]) -> dict:
    """贪心按 IoU 把 v1 模块配到终版模块（高 IoU 优先，一对一）。"""
    candidates = []
    for yi, y in enumerate(y_modules):
        for xi, x in enumerate(x_modules):
            iou = _iou(x, y)
            if iou >= IOU_MATCH_THRESHOLD:
                candidates.append((iou, yi, xi))
    candidates.sort(reverse=True)
    matched_y: dict[int, tuple[int, float]] = {}
    used_x: set[int] = set()
    for iou, yi, xi in candidates:
        if yi in matched_y or xi in used_x:
            continue
        matched_y[yi] = (xi, iou)
        used_x.add(xi)
    return matched_y


def analyze_pair(x_modules: list[dict], y_modules: list[dict]) -> dict:
    """度量一对 (AI 初版 → 人工终版) 的模块级编辑。"""
    matched_y = _match(x_modules, y_modules)
    same_type = retyped = 0
    iou_sum = 0.0
    for yi, (xi, iou) in matched_y.items():
        iou_sum += iou
        if x_modules[xi].get("type") == y_modules[yi].get("type"):
            same_type += 1
        else:
            retyped += 1
    matched = len(matched_y)
    added = len(y_modules) - matched
    dropped = len(x_modules) - matched
    noncanonical_x = sum(
        1 for module in x_modules if module.get("type") not in MODULE_TYPES
    )
    edit_ops = retyped + added + dropped
    return {
        "x_count": len(x_modules),
        "y_count": len(y_modules),
        "matched": matched,
        "same_type": same_type,
        "retyped": retyped,
        "added": added,
        "dropped": dropped,
        "noncanonical_x": noncanonical_x,
        "mean_matched_iou": (iou_sum / matched) if matched else None,
        "edit_ops": edit_ops,
        "edit_rate": edit_ops / max(1, len(y_modules)),
    }


def extract_pairs(session) -> list[dict]:
    """抽取每个案例的 (最早 ai_generated 版) → (最新 verified 版) 对。"""
    rows = (
        session.query(models.LayoutBlueprint)
        .order_by(models.LayoutBlueprint.case_id, models.LayoutBlueprint.version)
        .all()
    )
    by_case: dict[int, list] = defaultdict(list)
    for blueprint in rows:
        by_case[blueprint.case_id].append(blueprint)

    pairs = []
    for case_id, blueprints in by_case.items():
        verified = [b for b in blueprints if b.review_status == "verified"]
        if not verified:
            continue
        target = verified[-1]
        ai_generated = [b for b in blueprints if b.review_status == "ai_generated"]
        source = ai_generated[0] if ai_generated else blueprints[0]
        if source.id == target.id:
            continue
        pairs.append(
            {
                "case_id": case_id,
                "gen_path": gen_path(source.model_name),
                "orientation": source.orientation or target.orientation or "",
                "x_modules": _modules(source),
                "y_modules": _modules(target),
            }
        )
    return pairs


def _aggregate(rows: list[dict]) -> dict:
    if not rows:
        return {"pairs": 0}
    sum_y = sum(r["y_count"] for r in rows)
    sum_x = sum(r["x_count"] for r in rows)
    sum_matched = sum(r["matched"] for r in rows)
    ious = [r["mean_matched_iou"] for r in rows if r["mean_matched_iou"] is not None]

    def ratio(numerator: int, denominator: int):
        return round(numerator / denominator, 4) if denominator else None

    return {
        "pairs": len(rows),
        "mean_edit_rate": round(sum(r["edit_rate"] for r in rows) / len(rows), 4),
        "type_accuracy": ratio(sum(r["same_type"] for r in rows), sum_matched),
        "retype_rate": ratio(sum(r["retyped"] for r in rows), sum_matched),
        "add_rate": ratio(sum(r["added"] for r in rows), sum_y),
        "drop_rate": ratio(sum(r["dropped"] for r in rows), sum_x),
        "noncanonical_x_rate": ratio(sum(r["noncanonical_x"] for r in rows), sum_x),
        "mean_matched_iou": round(sum(ious) / len(ious), 4) if ious else None,
    }


def analyze(session) -> dict:
    """全量分析：整体 + 按生成路径 + 按画布方向分层。"""
    pairs = extract_pairs(session)
    per_pair = [{**{k: pair[k] for k in ("case_id", "gen_path", "orientation")},
                 **analyze_pair(pair["x_modules"], pair["y_modules"])}
                for pair in pairs]

    by_gen_path: dict[str, list] = defaultdict(list)
    by_orientation: dict[str, list] = defaultdict(list)
    for row in per_pair:
        by_gen_path[row["gen_path"]].append(row)
        by_orientation[row["orientation"]].append(row)

    return {
        "pair_count": len(per_pair),
        "overall": _aggregate(per_pair),
        "by_gen_path": {key: _aggregate(rows) for key, rows in by_gen_path.items()},
        "by_orientation": {
            key: _aggregate(rows) for key, rows in by_orientation.items()
        },
        "per_pair": per_pair,
    }


def format_report(result: dict) -> str:
    cols = [
        "pairs", "mean_edit_rate", "type_accuracy", "retype_rate",
        "add_rate", "drop_rate", "noncanonical_x_rate", "mean_matched_iou",
    ]

    def fmt(value):
        return f"{value:.3f}" if isinstance(value, float) else ("—" if value is None else str(value))

    def table(title: str, buckets: dict) -> list[str]:
        lines = [f"### {title}", "", "| 分组 | " + " | ".join(cols) + " |",
                 "|---|" + "|".join(["---"] * len(cols)) + "|"]
        for key, agg in sorted(buckets.items()):
            lines.append("| " + key + " | " + " | ".join(fmt(agg.get(c)) for c in cols) + " |")
        lines.append("")
        return lines

    lines = [
        "# 拆解保真度报告",
        "",
        f"- (ai_generated → verified) 对：{result['pair_count']}",
        "- 指标越低越好：mean_edit_rate / retype_rate / add_rate / drop_rate / noncanonical_x_rate；越高越好：type_accuracy / mean_matched_iou。",
        "",
    ]
    lines += table("整体", {"overall": result["overall"]})
    lines += table("按生成路径 (gen_path)", result["by_gen_path"])
    lines += table("按画布方向 (orientation)", result["by_orientation"])
    return "\n".join(lines)


def main(argv=None) -> int:
    import argparse
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from app.database import SessionLocal, init_db

    parser = argparse.ArgumentParser(description="拆解保真度分析")
    parser.add_argument("--md-out", default="")
    parser.add_argument("--json-out", default="")
    args = parser.parse_args(argv)

    init_db()
    with SessionLocal() as session:
        result = analyze(session)

    if result["pair_count"] == 0:
        print("尚无 (ai_generated → verified) 蓝图对：请先在案例详情校正并确认蓝图。")
        return 1

    report = format_report(result)
    print(report)
    if args.md_out:
        Path(args.md_out).write_text(report, encoding="utf-8")
    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
