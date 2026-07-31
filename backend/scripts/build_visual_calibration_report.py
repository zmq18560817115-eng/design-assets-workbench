"""Compare two Calibration runs. This script never accepts a Holdout report."""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path


def load_calibration(path: Path) -> dict:
    report = json.loads(path.read_text(encoding="utf-8-sig"))
    if report.get("dataset_split") != "calibration":
        raise SystemExit("Only Calibration reports are accepted")
    if report.get("holdout_executed") is not False:
        raise SystemExit("Holdout report is forbidden in Calibration comparison")
    return report


def gate_results(metrics: dict, gates: dict) -> dict:
    results = {}
    for name, limit in gates.items():
        metric_name = name.removesuffix("_min").removesuffix("_max")
        value = metrics.get(metric_name, 0)
        passed = value >= limit if name.endswith("_min") else value <= limit
        results[name] = {"metric": metric_name, "value": value, "limit": limit, "passed": passed}
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--regression", type=Path, required=True)
    parser.add_argument("--comparison", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    baseline = load_calibration(args.baseline)
    regression = load_calibration(args.regression)
    metrics = {}
    for key, after in regression["metrics"].items():
        before = baseline["metrics"].get(key)
        metrics[key] = {
            "baseline": before,
            "regression": after,
            "delta": round(after - before, 4)
            if isinstance(after, (int, float)) and isinstance(before, (int, float))
            else None,
        }
    gates = gate_results(regression["metrics"], regression["gates"])
    passed = all(item["passed"] for item in gates.values())
    comparison = {
        "dataset_version": baseline["dataset_version"],
        "dataset_split": "calibration",
        "holdout_executed": False,
        "baseline_versions": {
            "model_name": baseline["model_name"],
            "prompt_version": baseline["prompt_version"],
            "validator_version": baseline["validator_version"],
        },
        "candidate_versions": {
            "model_name": regression["model_name"],
            "prompt_version": regression["prompt_version"],
            "validator_version": regression["validator_version"],
        },
        "metric_comparison": metrics,
        "gate_results": gates,
        "calibration_passed": passed,
        "candidate_frozen": passed,
        "holdout_allowed": passed,
        "generated_at": dt.datetime.now(dt.UTC).isoformat(),
    }
    args.comparison.write_text(
        json.dumps(comparison, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lines = [
        "# 真实素材 Calibration 报告",
        "",
        f"- 数据集：`{comparison['dataset_version']}`",
        "- 范围：仅 Calibration；未读取、未运行 Holdout Ground Truth",
        f"- 结论：{'通过，可冻结候选版本' if passed else '未通过，不得冻结候选版本或运行 Holdout'}",
        "",
        "## 基线与回归",
        "",
        "| 指标 | 基线 | 回归 | 变化 |",
        "|---|---:|---:|---:|",
    ]
    for name, values in metrics.items():
        lines.append(
            f"| {name} | {values['baseline']} | {values['regression']} | {values['delta']} |"
        )
    lines += [
        "",
        "## 诊断",
        "",
        "- 基线 24/24 请求超时，正式复现 `MODEL_TIMEOUT`。",
        "- 候选版已压缩模型图片、收窄输出合同并限制输出长度，但当前生产模型端仍为 24/24 超时。",
        "- 因模型没有返回有效 JSON，本轮无法据实评估 PRODUCT_MISSED、模块边界与异常重叠；不得把 0 次此类错误解释为能力通过。",
        "- 下一步应先恢复或核验火山模型服务与部署点，再用同一 Calibration 数据和冻结前候选版本重新回归。",
        "",
        "## 门禁",
        "",
    ]
    for name, result in gates.items():
        lines.append(
            f"- {'通过' if result['passed'] else '失败'} `{name}`："
            f"{result['value']}（要求 {result['limit']}）"
        )
    lines += [
        "",
        "## 版本处置",
        "",
        f"- Prompt：`{regression['prompt_version']}`（候选，未冻结）",
        f"- Validator：`{regression['validator_version']}`（候选，未冻结）",
        f"- Model：`{regression['model_name']}`（未通过 Calibration）",
        "- Holdout：禁止执行；本任务未读取答案、未运行盲测。",
        "",
    ]
    args.report.write_text("\n".join(lines), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
