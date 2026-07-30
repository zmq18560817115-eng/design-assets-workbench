"""检索排序评测指标。

约定：
- ``ranked`` 是按分数降序排列的 id 列表（模式 id 或案例 id）。
- ``gold`` 是相关项：可以是 id 列表（等价于全部相关度 1），也可以是
  ``{id: grade}`` 字典（分级相关度，用于 nDCG）。
- 当没有金标准时返回 ``None``，表示该条在聚合时应被跳过，而不是记 0 分。
"""
from __future__ import annotations

import math


def _gold_set(gold) -> set:
    if isinstance(gold, dict):
        return {key for key, grade in gold.items() if grade}
    return set(gold or [])


def _grade_map(gold) -> dict:
    if isinstance(gold, dict):
        return {key: grade for key, grade in gold.items() if grade}
    return {item: 1.0 for item in (gold or [])}


def recall_at_k(ranked: list, gold, k: int):
    """top-K 命中的相关项 / 全部相关项。"""
    gold_set = _gold_set(gold)
    if not gold_set:
        return None
    hit = len(set(ranked[:k]) & gold_set)
    return hit / len(gold_set)


def mrr(ranked: list, gold):
    """第一个命中相关项的倒数排名；全无命中记 0。"""
    gold_set = _gold_set(gold)
    if not gold_set:
        return None
    for index, item in enumerate(ranked, 1):
        if item in gold_set:
            return 1.0 / index
    return 0.0


def ndcg_at_k(ranked: list, gold, k: int):
    """带分级相关度的归一化折损累计增益。"""
    grades = _grade_map(gold)
    if not grades:
        return None
    dcg = 0.0
    for index, item in enumerate(ranked[:k], 1):
        grade = grades.get(item, 0)
        if grade:
            dcg += grade / math.log2(index + 1)
    ideal = sorted(grades.values(), reverse=True)[:k]
    idcg = sum(grade / math.log2(index + 1) for index, grade in enumerate(ideal, 1))
    return dcg / idcg if idcg else None
