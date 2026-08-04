"""Discover human-reviewable layout candidates from curated color-box annotations."""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import math
import mimetypes
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
sys.path.insert(0, str(ROOT))

from app import config, models, vlm  # noqa: E402
from app.database import SessionLocal, init_db  # noqa: E402


CATEGORIES = ("恒温杯", "吸奶器", "羊脂膏")
REASON = "公司人工筛选的优秀落地成品"
ARTIFACT_DIR = ROOT / "acceptance_data" / "layout-pattern-discovery"
QUALITY_PATH = ROOT / "acceptance_data" / "pairing-audit" / "annotation-quality-queues.json"
AUDIT_PATH = ARTIFACT_DIR / "curated-structure-audit.json"
CANDIDATE_PATH = ARTIFACT_DIR / "layout-pattern-candidates.json"
MODEL_RUN_PATH = ARTIFACT_DIR / "representative-model-runs.json"
PROMPT_VERSION = "curated-layout-representative-v1"


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def center(region: dict[str, Any]) -> tuple[float, float]:
    return region["x"] + region["width"] / 2, region["y"] + region["height"] / 2


def position_name(point: tuple[float, float]) -> str:
    x, y = point
    horizontal = "左" if x < .4 else "右" if x > .6 else "中"
    vertical = "上" if y < .4 else "下" if y > .6 else "中"
    return vertical + horizontal


def union_area(regions: list[dict[str, Any]]) -> float:
    grid = [[False] * 30 for _ in range(30)]
    for region in regions:
        x1 = max(0, min(29, int(region["x"] * 30)))
        y1 = max(0, min(29, int(region["y"] * 30)))
        x2 = max(x1 + 1, min(30, math.ceil((region["x"] + region["width"]) * 30)))
        y2 = max(y1 + 1, min(30, math.ceil((region["y"] + region["height"]) * 30)))
        for y in range(y1, y2):
            for x in range(x1, x2):
                grid[y][x] = True
    return sum(cell for row in grid for cell in row) / 900


def iou(left: dict[str, Any], right: dict[str, Any]) -> float:
    lx2, ly2 = left["x"] + left["width"], left["y"] + left["height"]
    rx2, ry2 = right["x"] + right["width"], right["y"] + right["height"]
    intersection = max(0.0, min(lx2, rx2) - max(left["x"], right["x"])) * max(0.0, min(ly2, ry2) - max(left["y"], right["y"]))
    union = left["width"] * left["height"] + right["width"] * right["height"] - intersection
    return intersection / union if union else 0.0


def analyze(row: models.DisinfectionAnnotation) -> dict[str, Any]:
    regions = json.loads(row.regions_json or "[]")
    by_type = {kind: [r for r in regions if r.get("type") == kind] for kind in ("layout_block", "product_image", "main_text")}
    product = max(by_type["product_image"], key=lambda r: r["width"] * r["height"])
    text = max(by_type["main_text"], key=lambda r: r["width"] * r["height"])
    product_center, text_center = center(product), center(text)
    product_area = product["width"] * product["height"]
    text_area = text["width"] * text["height"]
    occupied = union_area(regions)
    whitespace = max(0.0, 1 - occupied)
    density = "high" if len(regions) >= 10 or occupied >= .72 else "low" if len(regions) <= 5 and occupied < .48 else "medium"
    if abs(product_center[0] - text_center[0]) > .18:
        relation = "文字在产品左侧" if text_center[0] < product_center[0] else "文字在产品右侧"
        columns = 2
    else:
        relation = "文字在产品上方" if text_center[1] < product_center[1] else "文字在产品下方"
        columns = 1
    reading = [r["id"] for r in sorted(regions, key=lambda r: (r["y"], r["x"]))]
    overlap_warnings = [
        f"{left['id']}:{right['id']}"
        for index, left in enumerate(regions)
        for right in regions[index + 1:]
        if left.get("type") == right.get("type") and iou(left, right) > .88
    ]
    prominence = "strong" if product_area >= .22 else "weak" if product_area < .1 else "medium"
    content_area = sum(r["width"] * r["height"] for r in by_type["product_image"] + by_type["main_text"])
    needs_check = bool(overlap_warnings)
    feature = [
        min(len(by_type["layout_block"]), 6) / 6,
        min(len(by_type["product_image"]), 5) / 5,
        min(len(by_type["main_text"]), 5) / 5,
        product_center[0], product_center[1], text_center[0], text_center[1],
        product_area, text_area, occupied, float(columns - 1),
    ]
    return {
        "annotation_id": row.id,
        "category": row.product_category,
        "status": "needs_human_check" if needs_check else "ai_reviewed",
        "suggestion_status": "suggested",
        "counts": {kind: len(items) for kind, items in by_type.items()},
        "product_position": position_name(product_center),
        "product_area": round(product_area, 4),
        "main_text_position": position_name(text_center),
        "main_text_area": round(text_area, 4),
        "layout_region_count": len(by_type["layout_block"]),
        "alignment": "two_column" if columns == 2 else "center_stack",
        "product_text_relation": relation,
        "reading_order_suggestion": reading,
        "information_density": density,
        "whitespace_ratio": round(whitespace, 4),
        "product_prominence": prominence,
        "risks": [
            *("产品与文字区域总面积偏密" for _ in [0] if content_area > .85),
            *("异常重叠需人工确认" for _ in [0] if overlap_warnings),
            *("产品主体不够突出" for _ in [0] if prominence == "weak"),
        ],
        "feature": feature,
        "original_image_url": f"/api/layout-annotations/{row.id}/original-image",
        "annotation_image_url": f"/api/layout-annotations/{row.id}/image",
    }


def distance(left: dict[str, Any], right: dict[str, Any]) -> float:
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(left["feature"], right["feature"])))


def cluster_category(items: list[dict[str, Any]], threshold: float = .62) -> list[list[dict[str, Any]]]:
    clusters: list[list[dict[str, Any]]] = []
    for item in sorted(items, key=lambda row: row["annotation_id"]):
        scores = [sum(distance(item, member) for member in group) / len(group) for group in clusters]
        if scores and min(scores) <= threshold:
            clusters[scores.index(min(scores))].append(item)
        else:
            clusters.append([item])
    return sorted(clusters, key=lambda group: (-len(group), group[0]["annotation_id"]))


def average(values: list[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


def candidate(category: str, index: int, group: list[dict[str, Any]]) -> dict[str, Any]:
    representative = min(group, key=lambda item: sum(distance(item, other) for other in group))
    positions = collections.Counter(item["product_position"] for item in group)
    text_positions = collections.Counter(item["main_text_position"] for item in group)
    relations = collections.Counter(item["product_text_relation"] for item in group)
    densities = collections.Counter(item["information_density"] for item in group)
    evidence_ids = [item["annotation_id"] for item in group]
    layout_counts = [item["counts"]["layout_block"] for item in group]
    product_counts = [item["counts"]["product_image"] for item in group]
    text_counts = [item["counts"]["main_text"] for item in group]
    product_pos = positions.most_common(1)[0][0]
    text_pos = text_positions.most_common(1)[0][0]
    relation = relations.most_common(1)[0][0]
    density = densities.most_common(1)[0][0]
    return {
        "candidate_id": f"curated-{category}-{index:02d}",
        "pattern_name_suggestion": f"{category}·{product_pos}产品·{text_pos}文字结构",
        "category": category,
        "status": "candidate",
        "suggestion_status": "ai_suggested",
        "review_status": "unverified",
        "case_count": len(group),
        "representative_ids": [representative["annotation_id"]],
        "product_position": product_pos,
        "title_position": text_pos,
        "selling_point_position": text_pos,
        "reading_order": relation,
        "required_modules": ["layout_block", "product_image", "main_text"],
        "optional_modules": ["auxiliary_information"] if max(text_counts) > 1 else [],
        "average_information_density": density,
        "average_whitespace_ratio": average([item["whitespace_ratio"] for item in group]),
        "average_product_area": average([item["product_area"] for item in group]),
        "layout_region_range": [min(layout_counts), max(layout_counts)],
        "product_region_range": [min(product_counts), max(product_counts)],
        "text_region_range": [min(text_counts), max(text_counts)],
        "suitable_pages": ["产品卖点说明", "产品展示"] if density != "high" else ["功能说明", "信息汇总"],
        "unsuitable_pages": ["极简封面"] if density == "high" else ["复杂参数总表"],
        "reusable_parts": [relation, f"产品主体常见位置：{product_pos}", f"留白比例约{average([item['whitespace_ratio'] for item in group]):.0%}"],
        "risks": sorted({risk for item in group for risk in item["risks"]}) or ["需人工核对标题与辅助信息语义"],
        "evidence_annotation_ids": evidence_ids,
        "model_analysis": {},
    }


def write_reports(result: dict[str, Any]) -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    for category in CATEGORIES:
        candidates = [item for item in result["candidates"] if item["category"] == category]
        lines = [f"# {category}排版共性报告", "", f"- 自动审核：{result['category_counts'].get(category, 0)}张", f"- 候选模式：{len(candidates)}个", ""]
        for item in candidates:
            lines.extend([
                f"## {item['pattern_name_suggestion']}", "",
                f"- 案例数量：{item['case_count']}",
                f"- 代表案例：{', '.join(map(str, item['representative_ids']))}",
                f"- 共性：产品位于{item['product_position']}，文字位于{item['title_position']}，{item['reading_order']}",
                f"- 信息密度：{item['average_information_density']}；平均留白：{item['average_whitespace_ratio']:.1%}",
                f"- 适用：{'、'.join(item['suitable_pages'])}",
                f"- 不适用：{'、'.join(item['unsuitable_pages'])}",
                f"- 注意：{'、'.join(item['risks'])}",
                f"- 证据ID：{', '.join(map(str, item['evidence_annotation_ids']))}", "",
            ])
        (ARTIFACT_DIR / f"{category}-layout-commonality.md").write_text("\n".join(lines), encoding="utf-8")
    table = ["# 候选模式总表", "", "|候选ID|品类|案例数|代表案例|状态|", "|---|---|---:|---|---|"]
    for item in result["candidates"]:
        table.append(f"|{item['candidate_id']}|{item['category']}|{item['case_count']}|{','.join(map(str,item['representative_ids']))}|candidate / ai_suggested / unverified|")
    (ARTIFACT_DIR / "candidate-patterns-summary.md").write_text("\n".join(table), encoding="utf-8")
    (ARTIFACT_DIR / "representative-cases.md").write_text("# 代表案例清单\n\n" + "、".join(map(str, result["representative_ids"])), encoding="utf-8")
    (ARTIFACT_DIR / "human-check-issues.md").write_text(
        "# 需要人工判断的问题\n\n"
        "以下结构因同组不足3张，未强行生成候选模式：\n\n"
        + "、".join(map(str, result["unclustered_ids"])), encoding="utf-8"
    )


def build_local(*, write_database: bool) -> dict[str, Any]:
    quality = load_json(QUALITY_PATH, {})
    ready_ids = set(quality.get("first_manual_review_batch_ids", []))
    ready_ids = {record["id"] for record in quality.get("records", []) if record.get("quality_group") == "ready_for_manual_review"}
    if len(ready_ids) != 137:
        raise RuntimeError(f"ready scope must be 137, got {len(ready_ids)}")
    db = SessionLocal()
    try:
        rows = db.query(models.DisinfectionAnnotation).filter(models.DisinfectionAnnotation.id.in_(ready_ids)).all()
        if len(rows) != 137:
            raise RuntimeError("database ready scope mismatch")
        if any(row.source_type != "company_published" or row.dataset_split == "holdout" or row.product_category not in CATEGORIES for row in rows):
            raise RuntimeError("scope contains forbidden evidence")
        audited = [analyze(row) for row in rows]
        candidates = []
        discarded = []
        cluster_counts = {}
        for category in CATEGORIES:
            groups = cluster_category([item for item in audited if item["category"] == category])
            cluster_counts[category] = [len(group) for group in groups]
            valid = [group for group in groups if len(group) >= 3]
            discarded.extend(item["annotation_id"] for group in groups if len(group) < 3 for item in group)
            candidates.extend(candidate(category, index, group) for index, group in enumerate(valid, 1))
        representatives = []
        for category in CATEGORIES:
            category_candidates = [item for item in candidates if item["category"] == category][:8]
            representatives.extend(item["representative_ids"][0] for item in category_candidates)
        if write_database:
            audit_by_id = {item["annotation_id"]: item for item in audited}
            candidate_by_id = {annotation_id: item["candidate_id"] for item in candidates for annotation_id in item["evidence_annotation_ids"]}
            for row in rows:
                row.curator_selected_good = True
                row.curator_selection_reason = REASON
                row.structure_review_status = audit_by_id[row.id]["status"]
                row.structure_review_json = json.dumps(audit_by_id[row.id], ensure_ascii=False)
                row.structure_cluster_key = candidate_by_id.get(row.id, "needs_human_check")
            db.commit()
        result = {
            "generated_at": dt.datetime.now(dt.UTC).isoformat(),
            "scope_total": len(audited),
            "category_counts": dict(collections.Counter(item["category"] for item in audited)),
            "review_status_counts": dict(collections.Counter(item["status"] for item in audited)),
            "cluster_sizes": cluster_counts,
            "candidate_counts": dict(collections.Counter(item["category"] for item in candidates)),
            "representative_ids": representatives,
            "representative_count": len(representatives),
            "unclustered_ids": discarded,
            "excluded_needs_box_fix": len(quality.get("box_fix_ids", [])),
            "candidates": candidates,
            "audits": audited,
            "writes": {"annotation_verified": 0, "company_recommended": 0, "verified_layout_pattern": 0},
            "holdout_reads": 0,
            "model_calls": 0,
        }
        ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
        AUDIT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        CANDIDATE_PATH.write_text(json.dumps({"candidates": candidates, "representative_ids": representatives}, ensure_ascii=False, indent=2), encoding="utf-8")
        write_reports(result)
        return result
    finally:
        db.close()


def model_prompt(audit: dict[str, Any]) -> str:
    return f"""你是公司成品排版代表图审核助手。只输出严格JSON，不使用Markdown。
这是一张{audit['category']}公司成品图。本地框结构已经确定：{json.dumps({k:v for k,v in audit.items() if k not in {'feature','original_image_url','annotation_image_url'}}, ensure_ascii=False)}
请区分直接观察与判断，不能确定时写unknown。输出：
{{"observed":{{"product_subject":"","main_text":"","layout_structure":""}},"inferred":{{"page_role_suggestion":"","reading_order_suggestion":[],"layout_characteristics":"","product_presentation":"","text_hierarchy":"","information_density":"low|medium|high|unknown","suitable_scenes":[],"possible_problems":[],"pattern_name_suggestion":""}}}}
不得推断公司配色偏好，不得输出推荐状态。"""


def valid_model_result(value: Any) -> bool:
    return (
        isinstance(value, dict) and isinstance(value.get("observed"), dict)
        and isinstance(value.get("inferred"), dict)
        and all(str(value["observed"].get(key) or "").strip() for key in ("product_subject", "main_text", "layout_structure"))
        and value["inferred"].get("information_density") in {"low", "medium", "high", "unknown"}
    )


def model_call_is_new(state: dict[str, Any], annotation_id: int) -> bool:
    """Never repeat completed, failed, timed-out, or interrupted/running calls."""
    return str(annotation_id) not in state.get("runs", {})


def run_models(*, canary_only: bool, timeout: float) -> dict[str, Any]:
    local = load_json(AUDIT_PATH, {})
    candidates_doc = load_json(CANDIDATE_PATH, {})
    audits = {item["annotation_id"]: item for item in local.get("audits", [])}
    candidates = candidates_doc.get("candidates", [])
    reps = candidates_doc.get("representative_ids", [])
    canary = [next(item for item in reps if audits[item]["category"] == category) for category in CATEGORIES]
    targets = canary if canary_only else reps[:24]
    state = load_json(MODEL_RUN_PATH, {"prompt_version": PROMPT_VERSION, "runs": {}})
    db = SessionLocal()
    try:
        for annotation_id in targets:
            key = str(annotation_id)
            if not model_call_is_new(state, annotation_id):
                continue
            row = db.get(models.DisinfectionAnnotation, annotation_id)
            state["runs"][key] = {"annotation_id": annotation_id, "category": row.product_category, "status": "running", "started_at": dt.datetime.now(dt.UTC).isoformat()}
            ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
            MODEL_RUN_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
            try:
                path = Path(row.original_image_path)
                parsed, raw = vlm.analyze_image_with_trace(
                    path.read_bytes(), mimetypes.guess_type(path.name)[0] or "image/png", {},
                    prompt_override=model_prompt(audits[annotation_id]), timeout_seconds=timeout,
                    max_tokens=1200, retry_read_timeout=False,
                )
                if not valid_model_result(parsed):
                    raise ValueError("schema_validation_failed")
                state["runs"][key].update(status="success", parsed_output=parsed, fallback=False, finished_at=dt.datetime.now(dt.UTC).isoformat())
                (ARTIFACT_DIR / f"raw-{annotation_id}.txt").write_text(raw, encoding="utf-8")
            except Exception as exc:
                error = str(exc)
                status = "timeout" if "timeout" in error.lower() else "failed"
                state["runs"][key].update(status=status, error=error, fallback=False, finished_at=dt.datetime.now(dt.UTC).isoformat())
                MODEL_RUN_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
                break
            MODEL_RUN_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        canary_rows = [state["runs"].get(str(item), {}) for item in canary]
        canary_passed = len(canary_rows) == 3 and all(item.get("status") == "success" and not item.get("fallback") for item in canary_rows)
        state["canary_ids"] = canary
        state["canary_passed"] = canary_passed
        state["call_count"] = len(state["runs"])
        MODEL_RUN_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        if canary_only and not canary_passed:
            return state
        if not canary_only and not canary_passed:
            raise RuntimeError("canary gate is not passed")
        for item in candidates:
            rep_id = item["representative_ids"][0]
            item["model_analysis"] = state["runs"].get(str(rep_id), {}).get("parsed_output", {})
            suggestion = item["model_analysis"].get("inferred", {}).get("pattern_name_suggestion")
            if suggestion and suggestion != "unknown":
                item["pattern_name_suggestion"] = suggestion
        CANDIDATE_PATH.write_text(json.dumps({"candidates": candidates, "representative_ids": reps}, ensure_ascii=False, indent=2), encoding="utf-8")
        return state
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-database", action="store_true")
    parser.add_argument("--model-stage", choices=("none", "canary", "representatives"), default="none")
    parser.add_argument("--timeout", type=float, default=180)
    args = parser.parse_args()
    init_db()
    result = build_local(write_database=args.write_database)
    print(json.dumps({key: value for key, value in result.items() if key not in {"audits", "candidates"}}, ensure_ascii=False, indent=2))
    if args.model_stage == "canary":
        print(json.dumps(run_models(canary_only=True, timeout=args.timeout), ensure_ascii=False, indent=2))
    elif args.model_stage == "representatives":
        print(json.dumps(run_models(canary_only=False, timeout=args.timeout), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
