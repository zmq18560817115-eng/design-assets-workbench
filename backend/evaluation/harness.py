"""评测执行核心：把评测样本喂给检索、逐条算指标、聚合。

设计要点：
- 用**未入库**的 BusinessRequirement 对象直接调 ``crud.match_business_requirement``，
  不污染数据库；检索命中的 pattern / case 来自库里真实的已确认数据。
- 模式检索与案例检索是两条独立结果，分别度量、分别聚合。
- ``evaluate`` 接收一个已打开的 session，便于单测传入自建的种子库。
"""
from __future__ import annotations

import json
from pathlib import Path

from app import crud, models

from . import metrics

# 评测样本里 requirement 的标量字段 → 模型同名列
_SCALAR_FIELDS = (
    "title",
    "request_text",
    "industry",
    "product_category",
    "channel",
    "canvas_ratio",
    "orientation",
    "campaign_stage",
    "business_goal",
    "key_message",
    "information_density",
)
# 评测样本里的列表字段 → 模型存 JSON 文本的列
_LIST_FIELDS = {
    "required_modules": "required_modules_json",
    "forbidden_modules": "forbidden_modules_json",
    "reference_case_ids": "reference_case_ids",
}


def build_requirement(spec: dict) -> models.BusinessRequirement:
    """把评测样本里的需求描述构造成一个未入库的 BusinessRequirement。"""
    kwargs = {field: (spec.get(field) or "") for field in _SCALAR_FIELDS}
    for source_key, column in _LIST_FIELDS.items():
        kwargs[column] = json.dumps(spec.get(source_key) or [], ensure_ascii=False)
    return models.BusinessRequirement(**kwargs)


def _normalize_gold(value) -> dict:
    """接受 ``[id, ...]`` 或 ``{id: grade}``，统一成 ``{int_id: float_grade}``。"""
    if isinstance(value, dict):
        return {int(key): float(grade) for key, grade in value.items() if grade}
    return {int(item): 1.0 for item in (value or [])}


def _channel_metrics(ranked_ids: list, gold: dict, k_values) -> dict:
    row = {"gold_count": len(gold)}
    for k in k_values:
        row[f"recall@{k}"] = metrics.recall_at_k(ranked_ids, gold, k)
        row[f"ndcg@{k}"] = metrics.ndcg_at_k(ranked_ids, gold, k)
    row["mrr"] = metrics.mrr(ranked_ids, gold)
    return row


def evaluate(session, items: list, k_values=(3, 5)) -> dict:
    """对整份评测集跑检索并算指标，返回聚合与逐条明细。"""
    per_item = []
    for item in items:
        requirement = build_requirement(item.get("requirement", {}))
        result = crud.match_business_requirement(session, requirement)
        ranked_patterns = [m["pattern"]["id"] for m in result["pattern_matches"]]
        ranked_cases = [m["case_id"] for m in result["case_matches"]]

        relevant = item.get("relevant", {})
        gold_patterns = _normalize_gold(
            relevant.get("patterns", relevant.get("pattern_ids"))
        )
        gold_cases = _normalize_gold(
            relevant.get("cases", relevant.get("case_ids"))
        )
        per_item.append(
            {
                "id": item.get("id"),
                "title": item.get("title", ""),
                "patterns": (
                    _channel_metrics(ranked_patterns, gold_patterns, k_values)
                    if gold_patterns
                    else None
                ),
                "cases": (
                    _channel_metrics(ranked_cases, gold_cases, k_values)
                    if gold_cases
                    else None
                ),
                "ranked_patterns": ranked_patterns,
                "ranked_cases": ranked_cases,
            }
        )
    return {
        "item_count": len(items),
        "k_values": list(k_values),
        "aggregate": _aggregate(per_item, k_values),
        "per_item": per_item,
    }


def _aggregate(per_item: list, k_values) -> dict:
    metric_keys = (
        [f"recall@{k}" for k in k_values]
        + [f"ndcg@{k}" for k in k_values]
        + ["mrr"]
    )
    aggregate = {}
    for channel in ("patterns", "cases"):
        rows = [row[channel] for row in per_item if row[channel]]
        channel_agg = {"evaluated": len(rows)}
        for key in metric_keys:
            values = [row[key] for row in rows if row.get(key) is not None]
            channel_agg[key] = (
                round(sum(values) / len(values), 4) if values else None
            )
        aggregate[channel] = channel_agg
    return aggregate


def load_eval_set(path) -> list:
    """读取评测集：支持 ``{"version":.., "items":[...]}`` 或裸数组。"""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    items = data["items"] if isinstance(data, dict) else data
    # 允许样本带下划线开头的注释键（如 _note），不影响评测
    return [item for item in items if not str(item.get("id", "")).startswith("_")]
