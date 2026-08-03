"""Run real Calibration only. This command has no Holdout execution path."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from app import config  # noqa: E402
from app.visual_calibration import (  # noqa: E402
    CANARY_GATES,
    CALIBRATION_GATES,
    calibration_gate_results,
    canary_gate_results,
    classify_exception,
    run_model_once,
    resume_calibration_assets,
    validate_prediction,
)


def percentile(values: list[int], fraction: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, math.ceil(len(ordered) * fraction) - 1)]


def full_calibration_ready(readiness: dict) -> bool:
    """Full Calibration is gated by Canary business quality, not transport only."""
    metrics = readiness.get("metrics", {})
    quality_gates = readiness.get("quality_gates", {})
    return (
        readiness.get("report_kind") == "calibration_canary"
        and readiness.get("dataset_split") == "calibration"
        and not readiness.get("holdout_executed", False)
        and metrics.get("total") == 3
        and metrics.get("task_success_rate") == 1
        and metrics.get("schema_valid_rate") == 1
        and readiness.get("quality_passed") is True
        and bool(quality_gates)
        and all(quality_gates.values())
        and all(canary_gate_results(metrics).values())
        and not readiness.get("fallback_count", 0)
    )


def report_versions_match(existing: dict, expected: dict) -> bool:
    return all(existing.get(key) == value for key, value in expected.items())


def aggregate(rows: list[dict]) -> dict:
    total = len(rows) or 1
    completed = [row for row in rows if row["run_status"] == "completed"]
    valid = [row for row in completed if row["schema_valid"]]
    def rate(numerator: int) -> float:
        return round(numerator / total, 4)
    truth_products = sum(row["metrics"].get("product_truth_count", 0) for row in completed)
    truth_text = sum(row["metrics"].get("primary_text_truth_count", 0) for row in completed)
    truth_layout = sum(row["metrics"].get("layout_truth_count", 0) for row in completed)
    matched_types = sum(
        row["metrics"].get("matched_type_count", 0) for row in completed
    )
    evaluable_modules = sum(
        row["metrics"].get("evaluable_module_count", 0) for row in completed
    )
    elapsed = [row["elapsed_ms"] for row in rows]
    text_types = (
        "main_title", "subtitle", "selling_point", "body_text", "feature_list"
    )
    subtype_predictions = {
        module_type: sum(
            row["metrics"].get("primary_text_prediction_type_counts", {}).get(
                module_type, 0
            )
            for row in completed
        )
        for module_type in text_types
    }
    subtype_matches = {
        module_type: sum(
            row["metrics"].get("primary_text_matched_type_counts", {}).get(
                module_type, 0
            )
            for row in completed
        )
        for module_type in text_types
    }
    return {
        "total": len(rows),
        "task_success_rate": rate(len(completed)),
        "schema_valid_rate": rate(len(valid)),
        "product_detection_rate": round(
            sum(row["metrics"].get("product_hit_count", 0) for row in completed)
            / max(1, truth_products), 4
        ),
        "product_missed_count": sum(
            "PRODUCT_MISSED" in row["error_codes"] for row in rows
        ),
        "primary_text_detection_rate": round(
            sum(row["metrics"].get("primary_text_hit_count", 0) for row in completed)
            / max(1, truth_text), 4
        ),
        "layout_module_recall": round(
            sum(row["metrics"].get("layout_hit_count", 0) for row in completed)
            / max(1, truth_layout), 4
        ),
        "module_type_accuracy": round(
            matched_types / evaluable_modules, 4
        ) if evaluable_modules else 0.0,
        "output_module_count": sum(
            row["metrics"].get("predicted_module_count", 0) for row in completed
        ),
        "primary_text_subtype_distribution": subtype_predictions,
        "primary_text_subtype_match_count": subtype_matches,
        "primary_text_subtype_match_accuracy": {
            module_type: (
                round(subtype_matches[module_type] / count, 4)
                if count else 0.0
            )
            for module_type, count in subtype_predictions.items()
        },
        "out_of_bounds_count": sum(
            "MODULE_OUT_OF_BOUNDS" in row["error_codes"] for row in rows
        ),
        "invalid_overlap_count": sum(
            row["metrics"].get("invalid_overlap_count", 0) for row in completed
        ),
        "invalid_overlap_rate": rate(sum(
            "MODULE_OVERLAP_INVALID" in row["error_codes"] for row in rows
        )),
        "timeout_rate": rate(sum(
            bool({"MODEL_TIMEOUT", "connect_timeout", "read_timeout"}.intersection(
                row["error_codes"]
            )) for row in rows
        )),
        "average_elapsed_ms": round(statistics.mean(elapsed)) if elapsed else 0,
        "p95_elapsed_ms": percentile(elapsed, 0.95),
    }


def evaluate_one(
    asset: dict,
    raw_root: Path,
    report_root: Path,
    instructions: str,
    timeout: float,
    validator_config: dict,
) -> dict:
    started = dt.datetime.now(dt.UTC)
    begin = time.perf_counter()
    raw_root.mkdir(parents=True, exist_ok=True)
    raw_path = raw_root / f"{asset['asset_id']}.txt"
    error_codes: list[str] = []
    parsed: dict = {}
    validation = {"schema_valid": False, "validation_errors": [], "metrics": {}}
    status = "failed"
    try:
        parsed, raw = run_model_once(
            Path(asset["absolute_original_path"]),
            additional_instructions=instructions,
            timeout_seconds=timeout,
        )
        raw_path.write_text(raw, encoding="utf-8")
        validation = validate_prediction(
            parsed, asset["ground_truth"], thresholds=validator_config
        )
        error_codes = validation["error_codes"]
        status = "completed"
    except Exception as error:
        error_codes = [classify_exception(error)]
        raw_path.write_text(
            json.dumps({"error": type(error).__name__, "detail": str(error)}, ensure_ascii=False),
            encoding="utf-8",
        )
        validation["validation_errors"] = [str(error)]
    finished = dt.datetime.now(dt.UTC)
    return {
        "asset_id": asset["asset_id"],
        "filename": asset["filename"],
        "model_provider": config.VISION_PROVIDER,
        "model_name": config.VISION_MODEL,
        "prompt_version": asset["prompt_version"],
        "validator_version": asset["validator_version"],
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "elapsed_ms": round((time.perf_counter() - begin) * 1000),
        "retry_count": 0,
        "run_status": status,
        "raw_output_path": raw_path.relative_to(report_root).as_posix(),
        "parsed_output": parsed,
        "validation_errors": validation["validation_errors"],
        "error_codes": error_codes,
        "schema_valid": validation["schema_valid"],
        "metrics": validation["metrics"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prompt-version", required=True)
    parser.add_argument("--validator-version", required=True)
    parser.add_argument("--instructions-file", type=Path)
    parser.add_argument("--validator-config", type=Path)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument(
        "--timeout", type=float,
        default=config.VISION_CALIBRATION_READ_TIMEOUT,
    )
    parser.add_argument("--stage", choices=("canary", "full"), required=True)
    parser.add_argument("--readiness-report", type=Path, required=True)
    args = parser.parse_args()
    if args.workers != 1:
        raise SystemExit("Provider safety policy requires --workers 1")
    if not config.vlm_enabled():
        raise SystemExit("生产视觉模型未配置，停止 Calibration")
    readiness = json.loads(args.readiness_report.read_text(encoding="utf-8"))
    if args.stage == "canary":
        ready = (
            readiness.get("report_kind") == "provider_availability_preflight"
            and readiness.get("status") == "ready"
            and readiness.get("completed_smoke_count") == 3
            and readiness.get("requested_smoke_count") == 3
            and all(
                row.get("minimal_text", {}).get("status") == "success"
                and row.get("minimal_image", {}).get("status") == "success"
                for row in readiness.get("runs", [])
            )
        )
        if not ready:
            raise SystemExit(
                "blocked_by_provider_availability: 需要连续3次成功的服务预检"
            )
    else:
        ready = full_calibration_ready(readiness)
        if not ready:
            raise SystemExit(
                "calibration_quality_blocked: Canary全部业务质量门禁通过后才能运行完整Calibration"
            )
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    instructions = (
        args.instructions_file.read_text(encoding="utf-8")
        if args.instructions_file else ""
    )
    validator_config = (
        json.loads(args.validator_config.read_text(encoding="utf-8"))
        if args.validator_config else {}
    )
    project_root = args.manifest.resolve().parents[2]
    assets = []
    for item in manifest["assets"]:
        if item["dataset_split"] != "calibration":
            continue
        if item["annotation_status"] != "verified" or "ground_truth" not in item:
            continue
        original = project_root / item["original_relative_path"]
        if not original.is_file():
            raise SystemExit(f"原图不存在: {item['original_relative_path']}")
        assets.append({
            **item,
            "absolute_original_path": str(original),
            "prompt_version": args.prompt_version,
            "validator_version": args.validator_version,
        })
    if args.stage == "canary":
        ordered = sorted(
            assets,
            key=lambda item: len(item["ground_truth"].get("layout_modules", []))
            + len(item["ground_truth"].get("product_regions", []))
            + len(item["ground_truth"].get("primary_text_regions", [])),
        )
        assets = [ordered[0], ordered[len(ordered) // 2], ordered[-1]]
    completed_assets: set[str] = set()
    rows = []
    if args.output.is_file():
        existing = json.loads(args.output.read_text(encoding="utf-8"))
        expected_versions = {
            "model_name": config.VISION_MODEL,
            "prompt_version": args.prompt_version,
            "validator_version": args.validator_version,
        }
        mismatched = [key for key, value in expected_versions.items()
                      if existing.get(key) != value]
        if mismatched:
            raise SystemExit(
                "拒绝混合不同运行版本，请使用新的输出文件: "
                + ", ".join(mismatched)
            )
        assets, rows = resume_calibration_assets(assets, existing)
        truth_by_id = {
            item["asset_id"]: item["ground_truth"]
            for item in manifest["assets"]
            if item.get("dataset_split") == "calibration"
            and item.get("annotation_status") == "verified"
            and "ground_truth" in item
        }
        for row in rows:
            truth = truth_by_id.get(row["asset_id"])
            if not truth:
                continue
            validation = validate_prediction(
                row.get("parsed_output") or {}, truth,
                thresholds=validator_config,
            )
            row.update(
                schema_valid=validation["schema_valid"],
                error_codes=validation["error_codes"],
                validation_errors=validation["validation_errors"],
                metrics=validation["metrics"],
            )
        completed_assets = {row["asset_id"] for row in rows}
    checkpoint = {
        "report_kind": "calibration_canary" if args.stage == "canary" else "calibration",
        "dataset_version": manifest["manifest_version"],
        "dataset_split": "calibration",
        "holdout_executed": False,
        "model_provider": config.VISION_PROVIDER,
        "model_name": config.VISION_MODEL,
        "prompt_version": args.prompt_version,
        "validator_version": args.validator_version,
        "runs": rows,
    }
    consecutive_provider_failures = 0
    provider_blocked = False
    provider_block_reason = ""
    raw_root = args.output.parent / f"{args.output.stem}-raw"
    report_root = args.output.parent.parent.parent
    for index, asset in enumerate(assets, 1):
        rows.append(evaluate_one(
            asset, raw_root, report_root, instructions, args.timeout,
            validator_config,
        ))
        provider_errors = {
            "dns_error", "tls_error", "connect_timeout", "read_timeout",
            "authentication_error", "permission_error", "endpoint_not_found",
            "model_not_found", "rate_limited", "quota_exceeded",
            "payload_too_large", "invalid_request", "provider_5xx",
            "unknown_provider_error",
        }
        if provider_errors.intersection(rows[-1]["error_codes"]):
            consecutive_provider_failures += 1
            provider_block_reason = next(
                iter(provider_errors.intersection(rows[-1]["error_codes"]))
            )
        else:
            consecutive_provider_failures = 0
        args.output.write_text(
            json.dumps(
                {**checkpoint, "metrics": aggregate(rows), "partial": True},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(
            f"[{index}/{len(assets)}] {rows[-1]['filename']} "
            f"{rows[-1]['run_status']} {rows[-1]['error_codes']}",
            flush=True,
        )
        non_retryable = {
            "dns_error", "tls_error", "authentication_error",
            "permission_error", "endpoint_not_found", "model_not_found",
            "quota_exceeded", "payload_too_large", "invalid_request",
        }
        if non_retryable.intersection(rows[-1]["error_codes"]):
            provider_blocked = True
            break
        if consecutive_provider_failures >= 3:
            provider_blocked = True
            break
    final_metrics = aggregate(rows)
    quality_gates = (
        canary_gate_results(final_metrics)
        if args.stage == "canary" else calibration_gate_results(final_metrics)
    )
    report = {
        "report_kind": "calibration_canary" if args.stage == "canary" else "calibration",
        "dataset_version": manifest["manifest_version"],
        "dataset_split": "calibration",
        "holdout_executed": False,
        "model_provider": config.VISION_PROVIDER,
        "model_name": config.VISION_MODEL,
        "prompt_version": args.prompt_version,
        "validator_version": args.validator_version,
        "thresholds": {
            **__import__(
                "app.visual_calibration", fromlist=["DEFAULT_THRESHOLDS"]
            ).DEFAULT_THRESHOLDS,
            **validator_config,
        },
        "gates": CANARY_GATES if args.stage == "canary" else CALIBRATION_GATES,
        "metrics": final_metrics,
        "quality_gates": quality_gates,
        "quality_passed": all(quality_gates.values()),
        "runs": sorted(rows, key=lambda row: row["filename"].casefold()),
        "generated_at": dt.datetime.now(dt.UTC).isoformat(),
        "fallback_count": 0,
        "verified_write_count": 0,
        "resume_skipped_success_count": len(completed_assets),
        "status": (
            "blocked_by_provider_availability"
            if provider_blocked else "completed"
        ),
        "provider_block_reason": provider_block_reason if provider_blocked else "",
    }
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    errors_path = args.output.with_name(
        "calibration-errors.json"
        if args.output.name == "calibration-baseline.json"
        else f"{args.output.stem}-errors.json"
    )
    errors_path.write_text(
        json.dumps(
            {
                "dataset_version": report["dataset_version"],
                "dataset_split": "calibration",
                "holdout_executed": False,
                "prompt_version": report["prompt_version"],
                "validator_version": report["validator_version"],
                "error_counts": {
                    code: sum(code in row["error_codes"] for row in rows)
                    for code in sorted({
                        code for row in rows for code in row["error_codes"]
                    })
                },
                "failures": [
                    {
                        "asset_id": row["asset_id"],
                        "filename": row["filename"],
                        "run_status": row["run_status"],
                        "elapsed_ms": row["elapsed_ms"],
                        "error_codes": row["error_codes"],
                        "validation_errors": row["validation_errors"],
                        "raw_output_path": row["raw_output_path"],
                    }
                    for row in sorted(rows, key=lambda item: item["filename"].casefold())
                    if row["error_codes"]
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(json.dumps(report["metrics"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
