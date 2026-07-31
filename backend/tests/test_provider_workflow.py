from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import provider_workflow


class ProviderWorkflowTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.reports = {
            key: root / f"{key}.json"
            for key in ("provider_probe", "smoke", "canary", "full")
        }
        self.patch_reports = patch.object(provider_workflow, "REPORTS", self.reports)
        self.patch_fallback = patch.object(
            provider_workflow, "FALLBACK_FORMAL_REPORT", root / "fallback.json"
        )
        self.patch_reports.start()
        self.patch_fallback.start()
        provider_workflow._state.update(
            running=False, stage="", started_at=None, finished_at=None,
            exit_code=None, message="",
        )

    def tearDown(self):
        self.patch_reports.stop()
        self.patch_fallback.stop()
        self.temp.cleanup()

    def write(self, stage, payload):
        self.reports[stage].write_text(json.dumps(payload), encoding="utf-8")

    def write_ready_prerequisites(self):
        self.write("provider_probe", {
            "status": "ready",
            "runs": [{"formal_schema": {"status": "success", "schema_valid": True}}],
        })
        self.write("smoke", {
            "status": "ready", "requested_smoke_count": 3,
            "completed_smoke_count": 3, "runs": [{}, {}, {}],
        })

    def test_blocked_formal_only_allows_provider_probe(self):
        self.write("provider_probe", {
            "status": "blocked_by_provider_availability",
            "runs": [{"formal_schema": {"status": "failed"}}],
        })
        status = provider_workflow.workflow_status()
        self.assertTrue(status["actions"]["provider_probe"])
        self.assertFalse(status["actions"]["smoke"])
        self.assertFalse(status["actions"]["canary"])
        self.assertFalse(status["actions"]["full"])
        self.assertFalse(status["actions"]["holdout"])

    def test_formal_success_unlocks_smoke_only(self):
        self.write("provider_probe", {
            "status": "ready",
            "runs": [{"formal_schema": {"status": "success", "schema_valid": True}}],
        })
        status = provider_workflow.workflow_status()
        self.assertTrue(status["actions"]["smoke"])
        self.assertFalse(status["actions"]["canary"])

    def test_three_smokes_unlock_canary(self):
        self.write("provider_probe", {
            "status": "ready",
            "runs": [{"formal_schema": {"status": "success", "schema_valid": True}}],
        })
        self.write("smoke", {
            "status": "ready", "requested_smoke_count": 3,
            "completed_smoke_count": 3, "runs": [{}, {}, {}],
        })
        self.assertTrue(provider_workflow.workflow_status()["actions"]["canary"])

    def test_canary_success_unlocks_full(self):
        self.write_ready_prerequisites()
        self.write("canary", {
            "report_kind": "calibration_canary", "status": "completed",
            "metrics": {"total": 3, "task_success_rate": 1, "schema_valid_rate": 1},
            "fallback_count": 0,
        })
        self.assertTrue(provider_workflow.workflow_status()["actions"]["full"])

    def test_full_gate_never_unlocks_holdout_directly(self):
        self.write_ready_prerequisites()
        self.write("canary", {
            "report_kind": "calibration_canary", "status": "completed",
            "metrics": {"total": 3, "task_success_rate": 1, "schema_valid_rate": 1},
            "fallback_count": 0,
        })
        self.write("full", {
            "report_kind": "calibration", "status": "completed",
            "metrics": {"total": 24, "task_success_rate": .96, "schema_valid_rate": 1},
            "fallback_count": 0,
        })
        status = provider_workflow.workflow_status()
        self.assertEqual(status["status"], "calibration_ready_for_freeze")
        self.assertFalse(status["actions"]["holdout"])
        self.assertTrue(status["holdout"]["sealed"])

    def test_later_report_cannot_bypass_missing_prerequisites(self):
        self.write("full", {
            "report_kind": "calibration", "status": "completed",
            "metrics": {"total": 24, "task_success_rate": 1, "schema_valid_rate": 1},
            "fallback_count": 0,
        })
        status = provider_workflow.workflow_status()
        self.assertFalse(status["gates"]["full_calibration_ready"])
        self.assertEqual(status["status"], "blocked_by_provider_availability")

    def test_command_tree_contains_no_holdout_stage(self):
        self.assertEqual(set(provider_workflow.REPORTS), {"provider_probe", "smoke", "canary", "full"})
        with self.assertRaises(provider_workflow.WorkflowConflict):
            provider_workflow.start_stage("holdout")


if __name__ == "__main__":
    unittest.main()
