"""离线检索评测 CLI。

用法（在 backend/ 下）：
    python -m evaluation.run_eval
    python -m evaluation.run_eval --eval-set evaluation/eval_set_v1.json --k 3,5 \
        --md-out evaluation/report.md --json-out evaluation/report.json

它连接与应用相同的 ``DATABASE_URL``，因此评测跑在真实的已确认模式/案例数据上。
先用少量种子样本跑通链路，再把评测集扩到 50~100 条真实需求。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 兼容直接以脚本方式运行：把 backend/ 加入路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import SessionLocal, init_db  # noqa: E402
from evaluation.harness import evaluate, load_eval_set  # noqa: E402


def _fmt(value) -> str:
    return f"{value:.3f}" if isinstance(value, (int, float)) else "—"


def format_report(result: dict) -> str:
    k_values = result["k_values"]
    metric_keys = (
        [f"recall@{k}" for k in k_values]
        + [f"ndcg@{k}" for k in k_values]
        + ["mrr"]
    )
    lines = [
        "# 检索评测报告",
        "",
        f"- 评测样本数：{result['item_count']}",
        f"- K：{', '.join(str(k) for k in k_values)}",
        "",
        "| 通道 | 已评测 | " + " | ".join(metric_keys) + " |",
        "|---|---|" + "|".join(["---"] * len(metric_keys)) + "|",
    ]
    labels = {"patterns": "排版模式", "cases": "相关案例"}
    for channel, agg in result["aggregate"].items():
        cells = [_fmt(agg.get(key)) for key in metric_keys]
        lines.append(
            f"| {labels.get(channel, channel)} | {agg['evaluated']} | "
            + " | ".join(cells)
            + " |"
        )
    lines.append("")
    lines.append("## 逐条明细")
    for row in result["per_item"]:
        parts = []
        for channel in ("patterns", "cases"):
            data = row[channel]
            if data:
                r3 = data.get(f"recall@{k_values[0]}")
                parts.append(f"{labels[channel]} R@{k_values[0]}={_fmt(r3)} MRR={_fmt(data['mrr'])}")
        detail = "；".join(parts) if parts else "无金标准，跳过"
        lines.append(f"- `{row['id']}` {row['title']}：{detail}")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="离线检索评测")
    default_set = Path(__file__).parent / "eval_set_v1.json"
    parser.add_argument("--eval-set", default=str(default_set))
    parser.add_argument("--k", default="3,5", help="逗号分隔的 K，例如 3,5")
    parser.add_argument("--md-out", default="")
    parser.add_argument("--json-out", default="")
    args = parser.parse_args(argv)

    k_values = tuple(int(part) for part in args.k.split(",") if part.strip())
    items = load_eval_set(args.eval_set)
    if not items:
        print("评测集为空：请先在 eval_set_v1.json 填入真实需求与金标准参考 id。")
        return 1

    init_db()
    with SessionLocal() as session:
        result = evaluate(session, items, k_values)

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
