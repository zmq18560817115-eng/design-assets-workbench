"""Run layered provider diagnostics without executing a Calibration batch or Holdout."""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import io
import hashlib
import json
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).parents[1]))

from app import config, vlm  # noqa: E402
from app.layout_blueprint import MODULE_TYPE_ORDER  # noqa: E402
from app.provider_availability import (  # noqa: E402
    CallPolicy, CircuitBreaker, ProviderCallError,
    guarded_chat_request, run_preflight,
)
from app.visual_calibration import (  # noqa: E402
    CALIBRATION_OUTPUT_PROMPT, validate_prediction,
)


def calibration_sample(manifest_path: Path) -> tuple[Path, dict]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    root = manifest_path.resolve().parents[2]
    for item in manifest["assets"]:
        if item.get("dataset_split") != "calibration":
            continue
        relative = item.get("original_relative_path")
        if relative and (root / relative).is_file():
            return root / relative, item
    raise SystemExit("No Calibration original is available for the image preflight")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--smoke-count", type=int, choices=range(1, 4), default=1)
    parser.add_argument("--connect-timeout", type=float, default=10)
    parser.add_argument(
        "--read-timeout", type=float,
        default=config.VISION_CALIBRATION_READ_TIMEOUT,
    )
    parser.add_argument("--max-retries", type=int, choices=(0, 1), default=1)
    parser.add_argument("--formal-schema", action="store_true")
    parser.add_argument("--instructions-file", type=Path)
    args = parser.parse_args()
    sample, sample_item = calibration_sample(args.manifest)
    policy = CallPolicy(
        connect_timeout=args.connect_timeout,
        read_timeout=args.read_timeout,
        max_retries=args.max_retries,
    )
    runs = []
    for index in range(args.smoke_count):
        result = run_preflight(sample, policy=policy, breaker=CircuitBreaker())
        if result["status"] == "ready" and args.formal_schema:
            with Image.open(sample) as source:
                image = source.convert("RGB")
                edge = config.VISION_CALIBRATION_IMAGE_EDGE
                image.thumbnail((edge, edge), Image.Resampling.LANCZOS)
                output = io.BytesIO()
                image.save(output, "JPEG", quality=80, optimize=True)
            prompt = CALIBRATION_OUTPUT_PROMPT.format(
                module_types=", ".join(MODULE_TYPE_ORDER)
            )
            if args.instructions_file:
                prompt += "\n\n" + args.instructions_file.read_text(encoding="utf-8")
            payload = {
                "model": config.VISION_MODEL,
                "messages": [{"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url":
                        "data:image/jpeg;base64," + base64.b64encode(output.getvalue()).decode()
                    }},
                ]}],
                "temperature": 0,
                "max_tokens": config.VISION_CALIBRATION_MAX_TOKENS,
                "stream": True,
            }
            try:
                formal_policy = CallPolicy(
                    connect_timeout=policy.connect_timeout,
                    read_timeout=policy.read_timeout,
                    write_timeout=policy.write_timeout,
                    pool_timeout=policy.pool_timeout,
                    max_retries=policy.max_retries,
                    backoff_base=policy.backoff_base,
                    jitter_max=policy.jitter_max,
                    retry_read_timeout=False,
                )
                formal = guarded_chat_request(
                    payload, policy=formal_policy, breaker=CircuitBreaker()
                )
                content = formal["body"]["choices"][0]["message"]["content"]
                finish_reason = formal["body"]["choices"][0].get("finish_reason")
                raw_path = args.output.with_suffix(".raw.txt")
                raw_path.parent.mkdir(parents=True, exist_ok=True)
                raw_path.write_text(content, encoding="utf-8")
                trace = {
                    **{key: value for key, value in formal.items() if key != "body"},
                    "finish_reason": finish_reason,
                    "content_length": len(content),
                    "content_sha256": hashlib.sha256(content.encode()).hexdigest(),
                    "raw_output_path": str(raw_path),
                }
                try:
                    parsed = vlm._extract_json(content)
                except json.JSONDecodeError as exc:
                    result["formal_schema"] = {
                        "status": "failed",
                        "error_type": "invalid_json",
                        "exception_type": type(exc).__name__,
                        **trace,
                        "result_persisted_as_verified": False,
                    }
                    result["status"] = "blocked_by_provider_availability"
                    result["block_reason"] = "invalid_json"
                    parsed = None
                if parsed is not None:
                    validation = validate_prediction(parsed, sample_item["ground_truth"])
                    schema_valid = validation["schema_valid"]
                    result["formal_schema"] = {
                        "status": "success" if schema_valid else "failed",
                        **trace,
                        "schema_valid": schema_valid,
                        "error_codes": validation["error_codes"],
                        "module_count": len(parsed.get("blueprint_modules", [])),
                        "result_persisted_as_verified": False,
                    }
                    if not schema_valid:
                        result["formal_schema"]["error_type"] = "schema_validation_failed"
                        result["status"] = "blocked_by_provider_availability"
                        result["block_reason"] = "schema_validation_failed"
            except ProviderCallError as exc:
                result["formal_schema"] = {
                    "status": "failed", **exc.to_dict(),
                    "attempts": getattr(exc, "attempts", []),
                    "result_persisted_as_verified": False,
                }
                result["status"] = "blocked_by_provider_availability"
                result["block_reason"] = exc.error_type
            except (KeyError, TypeError, ValueError) as exc:
                result["formal_schema"] = {
                    "status": "failed", "error_type": "invalid_json",
                    "exception_type": type(exc).__name__,
                    "result_persisted_as_verified": False,
                }
                result["status"] = "blocked_by_provider_availability"
                result["block_reason"] = "invalid_json"
        result["sequence"] = index + 1
        runs.append(result)
        if result["status"] != "ready":
            break
    ready = len(runs) == args.smoke_count and all(
        row["status"] == "ready" for row in runs
    )
    report = {
        "report_kind": "provider_availability_preflight",
        "generated_at": dt.datetime.now(dt.UTC).isoformat(),
        "status": "ready" if ready else "blocked_by_provider_availability",
        "requested_smoke_count": args.smoke_count,
        "completed_smoke_count": sum(row["status"] == "ready" for row in runs),
        "calibration_batch_executed": False,
        "holdout_executed": False,
        "sample_split": "calibration",
        "runs": runs,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
