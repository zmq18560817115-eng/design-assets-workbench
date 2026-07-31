"""Persisted, gated orchestration for provider recovery and Calibration stages."""
from __future__ import annotations

import json
import subprocess
import sys
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .provider_availability import safe_config_summary

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent
EVALUATION_DIR = PROJECT_DIR / "evaluation"
PROVIDER_DIR = EVALUATION_DIR / "provider-availability"
VISUAL_DIR = EVALUATION_DIR / "visual-analysis"
REPORTS = {
    "provider_probe": PROVIDER_DIR / "formal-schema-latest.json",
    "smoke": PROVIDER_DIR / "smoke-3.json",
    "canary": PROVIDER_DIR / "calibration-canary.json",
    "full": PROVIDER_DIR / "calibration-full.json",
}
FALLBACK_FORMAL_REPORT = PROVIDER_DIR / "formal-schema-probe.json"

_lock = threading.Lock()
_state: dict[str, Any] = {
    "running": False, "stage": "", "started_at": None,
    "finished_at": None, "exit_code": None, "message": "",
}


class WorkflowConflict(ValueError):
    """The requested workflow stage is unknown, busy, or still gated."""


def _load(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _formal_report() -> dict[str, Any]:
    return _load(REPORTS["provider_probe"]) or _load(FALLBACK_FORMAL_REPORT)


def _formal_ready(report: dict[str, Any]) -> bool:
    runs = report.get("runs", [])
    return bool(
        report.get("status") == "ready"
        and runs
        and runs[-1].get("formal_schema", {}).get("status") == "success"
        and runs[-1].get("formal_schema", {}).get("schema_valid") is True
    )


def _smoke_ready(report: dict[str, Any]) -> bool:
    return bool(
        report.get("status") == "ready"
        and report.get("requested_smoke_count") == 3
        and report.get("completed_smoke_count") == 3
        and len(report.get("runs", [])) == 3
    )


def _canary_ready(report: dict[str, Any]) -> bool:
    metrics = report.get("metrics", {})
    return bool(
        report.get("report_kind") == "calibration_canary"
        and report.get("status") == "completed"
        and metrics.get("total") == 3
        and metrics.get("task_success_rate") == 1
        and metrics.get("schema_valid_rate") == 1
        and report.get("fallback_count", 0) == 0
    )


def _full_ready(report: dict[str, Any]) -> bool:
    metrics = report.get("metrics", {})
    return bool(
        report.get("report_kind") == "calibration"
        and report.get("status") == "completed"
        and metrics.get("total") == 24
        and metrics.get("task_success_rate", 0) >= .95
        and metrics.get("schema_valid_rate") == 1
        and report.get("fallback_count", 0) == 0
    )


def workflow_status() -> dict[str, Any]:
    formal = _formal_report()
    smoke = _load(REPORTS["smoke"])
    canary = _load(REPORTS["canary"])
    full = _load(REPORTS["full"])
    formal_ready = _formal_ready(formal)
    smoke_ready = formal_ready and _smoke_ready(smoke)
    canary_ready = smoke_ready and _canary_ready(canary)
    full_ready = canary_ready and _full_ready(full)
    gates = {
        "formal_schema_ready": formal_ready,
        "smoke_three_ready": smoke_ready,
        "canary_three_ready": canary_ready,
        "full_calibration_ready": full_ready,
        "holdout_frozen": False,
    }
    with _lock:
        execution = dict(_state)
    return {
        "status": (
            "calibration_ready_for_freeze" if full_ready
            else "calibration_in_progress" if formal_ready
            else "blocked_by_provider_availability"
        ),
        "configuration": safe_config_summary(),
        "gates": gates,
        "execution": execution,
        "actions": {
            "provider_probe": not execution["running"],
            "smoke": gates["formal_schema_ready"] and not execution["running"],
            "canary": gates["smoke_three_ready"] and not execution["running"],
            "full": gates["canary_three_ready"] and not execution["running"],
            "holdout": False,
        },
        "reports": {"provider_probe": formal, "smoke": smoke, "canary": canary, "full": full},
        "holdout": {
            "sealed": True,
            "executed": False,
            "message": "完整 Calibration 与版本冻结完成前禁止执行 Holdout",
        },
    }


def _command(stage: str) -> list[str]:
    manifest = VISUAL_DIR / "untitled1-manifest.json"
    prompt = VISUAL_DIR / "prompt-visual-calibration-v2.txt"
    validator = VISUAL_DIR / "validator-visual-calibration-v2.json"
    if stage == "provider_probe":
        return [
            sys.executable, "scripts/run_provider_preflight.py",
            "--manifest", str(manifest), "--output", str(REPORTS[stage]),
            "--smoke-count", "1", "--connect-timeout", "10",
            "--read-timeout", "120", "--max-retries", "1",
            "--formal-schema", "--instructions-file", str(prompt),
        ]
    if stage == "smoke":
        return [
            sys.executable, "scripts/run_provider_preflight.py",
            "--manifest", str(manifest), "--output", str(REPORTS[stage]),
            "--smoke-count", "3", "--connect-timeout", "10",
            "--read-timeout", "120", "--max-retries", "1",
        ]
    previous = REPORTS["smoke"] if stage == "canary" else REPORTS["canary"]
    return [
        sys.executable, "scripts/run_visual_calibration.py",
        "--manifest", str(manifest), "--output", str(REPORTS[stage]),
        "--prompt-version", "visual-calibration-prompt-v2",
        "--validator-version", "visual-calibration-validator-v2",
        "--instructions-file", str(prompt), "--validator-config", str(validator),
        "--stage", stage, "--readiness-report", str(previous),
        "--workers", "1", "--timeout", "120",
    ]


def _run(stage: str) -> None:
    try:
        completed = subprocess.run(
            _command(stage), cwd=BACKEND_DIR, capture_output=True,
            text=True, encoding="utf-8", errors="replace", check=False,
        )
        message = "完成" if completed.returncode == 0 else (
            completed.stderr.strip() or completed.stdout.strip()[-1000:]
        )
        exit_code = completed.returncode
    except Exception as exc:  # noqa: BLE001
        message, exit_code = f"{type(exc).__name__}: {exc}", -1
    with _lock:
        _state.update(
            running=False, finished_at=datetime.now(UTC).isoformat(),
            exit_code=exit_code, message=message,
        )


def start_stage(stage: str) -> dict[str, Any]:
    if stage not in REPORTS:
        raise WorkflowConflict("未知的恢复阶段")
    status = workflow_status()
    if status["execution"]["running"]:
        raise WorkflowConflict("已有模型诊断任务正在运行")
    if not status["actions"][stage]:
        requirements = {
            "smoke": "单张正式 Schema 预检尚未成功",
            "canary": "连续 3 次服务冒烟尚未全部成功",
            "full": "3 张 Calibration Canary 尚未全部成功",
        }
        raise WorkflowConflict(requirements.get(stage, "当前阶段不可执行"))
    with _lock:
        _state.update(
            running=True, stage=stage, started_at=datetime.now(UTC).isoformat(),
            finished_at=None, exit_code=None, message="运行中",
        )
    threading.Thread(target=_run, args=(stage,), daemon=True).start()
    return workflow_status()
