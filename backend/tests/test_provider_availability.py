from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

import httpx
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import analysis_evaluation, batch, config, models
from app.database import Base
from app.provider_availability import (
    CallPolicy, CircuitBreaker, ProviderCallError, classify_exception,
    guarded_chat_request, is_real_model_success, run_preflight,
    safe_config_summary,
)
from app.visual_calibration import resume_calibration_assets, run_model_once


class FakeClient:
    def __init__(self, events, calls, **_kwargs):
        self.events = events
        self.calls = calls

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def stream(self, method, url, **_kwargs):
        self.calls.append((method, url))
        event = self.events.pop(0)
        if isinstance(event, Exception):
            raise event
        return nullcontext(event)


def response(status=200, body=None, headers=None):
    return httpx.Response(
        status,
        json=body or {"choices": [{"message": {"content": "OK"}}]},
        headers=headers,
        request=httpx.Request("POST", "https://provider.invalid/v1/chat/completions"),
    )


class ProviderAvailabilityTest(unittest.TestCase):
    def call(self, events, *, retries=2, sleeper=lambda _seconds: None):
        calls = []
        factory = lambda **kwargs: FakeClient(events, calls, **kwargs)
        try:
            result = guarded_chat_request(
                {"model": "endpoint", "messages": []},
                policy=CallPolicy(max_retries=retries, jitter_max=0),
                breaker=CircuitBreaker(),
                client_factory=factory,
                sleeper=sleeper,
            )
            return result, calls
        except ProviderCallError as error:
            error.test_calls = calls
            raise

    def test_01_401_does_not_retry(self):
        with self.assertRaises(ProviderCallError) as caught:
            self.call([response(401)], retries=2)
        self.assertEqual(caught.exception.error_type, "authentication_error")
        self.assertEqual(len(caught.exception.test_calls), 1)

    def test_02_404_does_not_retry(self):
        with self.assertRaises(ProviderCallError) as caught:
            self.call([response(404, {"error": {"code": "ModelNotFound"}})], retries=2)
        self.assertEqual(caught.exception.error_type, "model_not_found")
        self.assertEqual(len(caught.exception.test_calls), 1)

    def test_03_429_retries_once_and_honors_retry_after(self):
        sleeps = []
        result, calls = self.call(
            [response(429, headers={"Retry-After": "2"}), response(200)],
            retries=1, sleeper=sleeps.append,
        )
        self.assertEqual(result["http_status"], 200)
        self.assertEqual(len(calls), 2)
        self.assertEqual(sleeps, [2.0])

    def test_04_5xx_retry_is_finite(self):
        result, calls = self.call([response(503), response(200)], retries=1)
        self.assertEqual(result["attempt_count"], 2)
        self.assertEqual(len(calls), 2)

    def test_05_connect_timeout_is_classified(self):
        error = classify_exception(httpx.ConnectTimeout("connect"))
        self.assertEqual(error.error_type, "connect_timeout")

    def test_06_read_timeout_is_classified(self):
        error = classify_exception(httpx.ReadTimeout("read"))
        self.assertEqual(error.error_type, "read_timeout")

    def test_07_three_consecutive_failures_open_circuit(self):
        breaker = CircuitBreaker(failure_threshold=3)
        calls = []
        factory = lambda **kwargs: FakeClient(
            [httpx.ReadTimeout("read")] * 3, calls, **kwargs
        )
        with self.assertRaises(ProviderCallError):
            guarded_chat_request(
                {"model": "endpoint"}, policy=CallPolicy(max_retries=2),
                breaker=breaker, client_factory=factory, sleeper=lambda _s: None,
            )
        self.assertTrue(breaker.is_open)
        self.assertEqual(len(calls), 3)

    def test_08_failed_text_preflight_never_calls_image(self):
        calls = []
        def request(*_args, **_kwargs):
            calls.append(1)
            raise ProviderCallError("authentication_error", "denied", status_code=401)
        with (
            patch("app.provider_availability.config.vision_missing_config", return_value=[]),
            patch("app.provider_availability.network_probe", return_value={"error_type": ""}),
        ):
            result = run_preflight(Path("unused.png"), request=request)
        self.assertEqual(result["status"], "blocked_by_provider_availability")
        self.assertEqual(len(calls), 1)
        self.assertEqual(result["minimal_image"]["status"], "not_run")

    def test_09_blocked_batch_is_not_quality_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = create_engine(f"sqlite:///{Path(directory) / 'batch.db'}")
            Base.metadata.create_all(engine)
            Session = sessionmaker(bind=engine)
            image_path = Path(directory) / "sample.png"
            Image.new("RGB", (20, 20), "white").save(image_path)
            with (
                patch.object(batch, "SessionLocal", Session),
                patch.object(config, "vlm_enabled", return_value=True),
                patch.object(batch, "run_preflight", return_value={
                    "status": "blocked_by_provider_availability",
                    "block_reason": "read_timeout",
                }),
            ):
                batch_id = batch.create_batch(
                    [{"path": str(image_path), "filename": "sample.png"}],
                    background=False, enable_vlm=True,
                )
                state = batch.get_batch(batch_id)
            engine.dispose()
            self.assertEqual(state["status"], "blocked")
            self.assertEqual(state["failed"], 0)
            self.assertEqual(state["done"], 0)
            self.assertEqual(state["errors"][0]["task_status"], "blocked_by_provider_availability")

    def test_10_fallback_is_not_real_model_success(self):
        self.assertFalse(is_real_model_success("启发式规则", "heuristic_fallback"))
        self.assertFalse(is_real_model_success("vision-model", "failed_fallback"))
        self.assertTrue(is_real_model_success("vision-model", "model"))

    def test_11_successful_resume_rows_are_not_pending(self):
        rows = [
            {"asset_id": "a", "run_status": "completed"},
            {"asset_id": "b", "run_status": "failed"},
            {"asset_id": "c", "run_status": "completed", "fallback": True},
        ]
        pending, completed = resume_calibration_assets(
            [{"asset_id": "a"}, {"asset_id": "b"}, {"asset_id": "c"}],
            {"runs": rows},
        )
        self.assertEqual(pending, [{"asset_id": "b"}, {"asset_id": "c"}])
        self.assertEqual([row["asset_id"] for row in completed], ["a"])

    def test_12_holdout_guard_remains_enforced_by_existing_contract(self):
        dataset = models.AnalysisEvaluationDataset(
            dataset_version="sealed", name="sealed", status="gt_ready"
        )
        runtime = models.AnalysisRuntimeVersion(status="draft")
        with self.assertRaises(analysis_evaluation.EvaluationConflict):
            analysis_evaluation.run_evaluation(
                None, dataset, runtime, dataset_split="holdout",
                actor="reviewer", confirm_holdout=True,
            )

    def test_13_safe_diagnostics_never_expose_api_key(self):
        with patch.object(config, "VISION_API_KEY", "super-secret-value"):
            encoded = json.dumps(safe_config_summary(), ensure_ascii=False)
        self.assertNotIn("super-secret-value", encoded)
        self.assertIn("configured", encoded)

    def test_14_streaming_chat_is_reassembled_as_normal_response(self):
        stream = (
            'data: {"id":"chat-1","choices":[{"delta":{"content":"{\\"blueprint_"}}]}\n\n'
            'data: {"choices":[{"delta":{"content":"modules\\":[]}"},"finish_reason":"stop"}]}\n\n'
            "data: [DONE]\n\n"
        )
        calls = []
        events = [
            httpx.Response(
                200,
                content=stream.encode(),
                headers={"content-type": "text/event-stream"},
                request=httpx.Request(
                    "POST", "https://provider.invalid/v1/chat/completions"
                ),
            )
        ]
        factory = lambda **kwargs: FakeClient(events, calls, **kwargs)
        result = guarded_chat_request(
            {"model": "endpoint", "stream": True},
            policy=CallPolicy(max_retries=0),
            breaker=CircuitBreaker(),
            client_factory=factory,
        )
        self.assertEqual(len(calls), 1)
        self.assertEqual(
            result["body"]["choices"][0]["message"]["content"],
            '{"blueprint_modules":[]}',
        )
        self.assertEqual(
            result["body"]["choices"][0]["finish_reason"], "stop"
        )

    def test_15_formal_policy_does_not_duplicate_read_timeout(self):
        calls = []
        factory = lambda **kwargs: FakeClient(
            [httpx.ReadTimeout("read"), response(200)], calls, **kwargs
        )
        with self.assertRaises(ProviderCallError):
            guarded_chat_request(
                {"model": "endpoint", "stream": True},
                policy=CallPolicy(
                    max_retries=1,
                    retry_read_timeout=False,
                ),
                breaker=CircuitBreaker(),
                client_factory=factory,
                sleeper=lambda _seconds: None,
            )
        self.assertEqual(len(calls), 1)

    def test_16_calibration_uses_bounded_streaming_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            image_path = Path(directory) / "sample.png"
            Image.new("RGB", (1600, 1600), "white").save(image_path)
            with patch("app.visual_calibration.vlm.analyze_image_with_trace") as call:
                call.return_value = ({"blueprint_modules": []}, "{}")
                run_model_once(image_path)
        kwargs = call.call_args.kwargs
        self.assertTrue(kwargs["stream"])
        self.assertFalse(kwargs["retry_read_timeout"])
        self.assertEqual(kwargs["max_tokens"], config.VISION_CALIBRATION_MAX_TOKENS)
        self.assertEqual(kwargs["image_max_edge"], config.VISION_CALIBRATION_IMAGE_EDGE)


if __name__ == "__main__":
    unittest.main()
