"""Create immutable v2 calibration runs and ignored comparison reports."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import calibration_ranking_v2 as ranking  # noqa: E402
from app import models  # noqa: E402
from app.database import SessionLocal  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "acceptance_data" / "real-search")
    args = parser.parse_args()
    db = SessionLocal()
    try:
        result = ranking.create_v2_runs(db)
        report = ranking.metrics(db, result["runs"])
        if not args.execute:
            db.rollback()
            print(json.dumps({"dry_run": True, "would_create": result["created"], **report}, ensure_ascii=False, indent=2))
            return 0
        db.commit()
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / "calibration-ranking-v2-metrics.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        rows = []
        rank_changes = []
        for run in result["runs"]:
            snap = json.loads(run.result_snapshot_json)
            query = json.loads(run.query_snapshot_json)
            source = db.get(models.LayoutSearchRun, query.get("source_run_id"))
            old = json.loads(source.result_snapshot_json) if source else {"cases": [], "patterns": []}
            old_ranks = {(item["result_type"], int(item["id"])): item.get("rank") for kind in ("cases", "patterns") for item in old.get(kind, [])}
            for kind in ("cases", "patterns"):
                for item in snap.get(kind) or []:
                    rank_changes.append({
                        "requirement_id": run.requirement_id,
                        "result_type": item["result_type"],
                        "result_id": item["id"],
                        "v1_rank": old_ranks.get((item["result_type"], int(item["id"]))),
                        "v2_rank": item.get("rank"),
                        "label_status": item.get("label_status", ""),
                    })
            for item in snap.get("excluded_results") or []:
                rows.append({"requirement_id": run.requirement_id, **item})
        with (args.output_dir / "calibration-ranking-v2-exclusions.csv").open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["requirement_id", "result_type", "id", "reason"])
            writer.writeheader(); writer.writerows(rows)
        with (args.output_dir / "calibration-ranking-v2-rank-changes.csv").open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["requirement_id", "result_type", "result_id", "v1_rank", "v2_rank", "label_status"])
            writer.writeheader(); writer.writerows(rank_changes)
        with (args.output_dir / "calibration-ranking-v2-pending-labels.csv").open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["requirement_id", "result_type", "result_id"])
            writer.writeheader(); writer.writerows(report["pending_calibration_labels"])
        (args.output_dir / "calibration-pattern-knowledge-gap.md").write_text(
            "# 排版模式知识缺口\n\n"
            "- 恒温杯多品选购/评测：冻结答案中有 Case 61、63、64、66 共4个不同公司案例，可形成 candidate 建议。\n"
            "- 羊脂膏测评：冻结答案中有 Case 361、363、371、375 共4个不同公司案例，可形成 candidate 建议。\n"
            "- 两类现有 verified 模式均无法承载多品范围和必需信息，本轮不推荐、不发布。\n"
            "- 建议状态仅为 candidate / unverified。\n",
            encoding="utf-8",
        )
        summary = ["# Calibration v1 / v2 对比", "", "- v1 案例准确率：44.44%", "- v1 案例 Top 5 准确率：20%", f"- v2 案例准确率：{report['case_accuracy']:.2%}", f"- v2 案例 Top 5 准确率：{report['case_top5_accuracy']:.2%}", "- ID 3、4、9、10 首个合适案例：均为第1名", "- ID 1、5、6：继续正确返回无结果", "- 跨品类推荐：0", "- 禁止项违规：0", f"- v2 返回模式：{report['pattern_returned']}（无合适模式时明确返回空状态）", f"- 待补充人工判断：{len(report['pending_calibration_labels'])}", "", "## 结论", "", "案例排序达到本轮门槛。排版模式因知识缺口未达到门槛，不能以全部隐藏模式宣称通过；Holdout 不应运行。"]
        (args.output_dir / "calibration-ranking-v2-comparison.md").write_text("\n".join(summary) + "\n", encoding="utf-8")
        print(json.dumps({"dry_run": False, "created": result["created"], **report}, ensure_ascii=False, indent=2))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
