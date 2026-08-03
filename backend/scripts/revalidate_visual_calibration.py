"""Offline revalidation of an existing Calibration report; never recalls a model."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from app.visual_calibration import (  # noqa: E402
    CANARY_GATES,
    canary_gate_results,
    validate_prediction,
)
from scripts.run_visual_calibration import aggregate  # noqa: E402


def revalidate(
    source: dict,
    manifest: dict,
    validator_config: dict,
    *,
    source_path: str,
    validator_version: str,
) -> dict:
    if source.get("dataset_split") != "calibration":
        raise ValueError("仅允许离线复评 Calibration")
    if source.get("holdout_executed"):
        raise ValueError("拒绝复评执行过 Holdout 的报告")
    truth_by_id = {
        item["asset_id"]: item["ground_truth"]
        for item in manifest.get("assets", [])
        if item.get("dataset_split") == "calibration"
        and item.get("annotation_status") == "verified"
        and "ground_truth" in item
    }
    rows = []
    for source_row in source.get("runs", []):
        truth = truth_by_id.get(source_row.get("asset_id"))
        if truth is None:
            raise ValueError(f"Calibration Ground Truth 不存在: {source_row.get('asset_id')}")
        validation = validate_prediction(
            source_row.get("parsed_output") or {}, truth,
            thresholds=validator_config,
        )
        rows.append({
            "asset_id": source_row["asset_id"],
            "filename": source_row["filename"],
            "run_status": source_row.get("run_status"),
            "schema_valid": validation["schema_valid"],
            "elapsed_ms": source_row.get("elapsed_ms", 0),
            "error_codes": validation["error_codes"],
            "validation_errors": validation["validation_errors"],
            "metrics": validation["metrics"],
            "predicted_primary_text_types": [
                module.get("type")
                for module in (source_row.get("parsed_output") or {}).get(
                    "blueprint_modules", []
                )
                if module.get("type") in {
                    "main_title", "subtitle", "selling_point", "body_text",
                    "feature_list",
                }
            ],
        })
    metrics = aggregate(rows)
    gates = canary_gate_results(metrics)
    return {
        "report_kind": "calibration_canary_offline_revalidation",
        "dataset_split": "calibration",
        "source_run_id": source.get("generated_at") or source_path,
        "source_report_path": source_path,
        "source_prompt_version": source.get("prompt_version"),
        "source_validator_version": source.get("validator_version"),
        "revalidation_validator_version": validator_version,
        "model_recalled": False,
        "holdout_read": False,
        "holdout_executed": False,
        "gates": CANARY_GATES,
        "metrics": metrics,
        "quality_gates": gates,
        "quality_passed": all(gates.values()),
        "runs": rows,
        "generated_at": dt.datetime.now(dt.UTC).isoformat(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-report", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--validator-config", type=Path, required=True)
    parser.add_argument("--validator-version", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.resolve() == args.source_report.resolve():
        raise SystemExit("离线复评必须使用独立输出文件")
    report = revalidate(
        json.loads(args.source_report.read_text(encoding="utf-8")),
        json.loads(args.manifest.read_text(encoding="utf-8")),
        json.loads(args.validator_config.read_text(encoding="utf-8")),
        source_path=args.source_report.as_posix(),
        validator_version=args.validator_version,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report["metrics"], ensure_ascii=False, indent=2))
    return 0 if report["quality_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
