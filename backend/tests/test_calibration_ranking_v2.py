import json
import unittest
from types import SimpleNamespace

from app import calibration_ranking_v2 as ranking


class CalibrationRankingV2Tests(unittest.TestCase):
    def test_multi_product_scope_detects_explicit_count(self):
        requirement = SimpleNamespace(
            title="4品恒温杯选购", raw_requirement="多品测评", content_purpose="选购攻略",
            page_role="对比页", required_modules_json=json.dumps(["四款参与产品"]),
        )
        scope = ranking.requirement_scope(requirement)
        self.assertEqual(scope, {"multi_product": True, "explicit_product_count": 4, "high_information": True})

    def test_capacity_promotes_grid_and_penalizes_single_product(self):
        high = SimpleNamespace(name="四象限矩阵网格对比", content_type="产品横评", scene="选购", summary="",)
        low = SimpleNamespace(name="中轴型单品种草", content_type="海报", scene="活动海报", summary="",)
        blueprint = SimpleNamespace(modules_json="[]", information_density="medium")
        high_score, high_reasons = ranking._case_capacity(high, blueprint)
        low_score, low_reasons = ranking._case_capacity(low, blueprint)
        self.assertGreater(high_score, low_score)
        self.assertTrue(any("结构含" in reason for reason in high_reasons))
        self.assertTrue(any("低容量" in reason for reason in low_reasons))

    def test_version_is_immutable_name(self):
        self.assertEqual(ranking.SCORING_VERSION, "layout-search-ranking-v2")
