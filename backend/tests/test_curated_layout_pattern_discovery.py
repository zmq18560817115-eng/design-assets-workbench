import unittest

from scripts.discover_curated_layout_patterns import (
    candidate,
    cluster_category,
    model_call_is_new,
    valid_model_result,
)


def item(item_id: int, category: str, feature: list[float]):
    return {
        "annotation_id": item_id,
        "category": category,
        "feature": feature,
        "product_position": "center",
        "main_text_position": "top-center",
        "product_text_relation": "text_above_product",
        "information_density": "medium",
        "whitespace_ratio": 0.4,
        "product_area": 0.2,
        "risks": [],
        "counts": {"layout_block": 1, "product_image": 1, "main_text": 1},
    }


class CuratedLayoutPatternDiscoveryTests(unittest.TestCase):
    def test_categories_are_clustered_independently(self):
        cup = cluster_category([item(i, "cup", [0.1, 0.2]) for i in range(3)])
        pump = cluster_category([item(i, "pump", [0.8, 0.9]) for i in range(3, 6)])
        self.assertEqual(3, len(cup[0]))
        self.assertEqual(3, len(pump[0]))

    def test_fewer_than_three_is_not_a_candidate(self):
        groups = cluster_category([item(1, "cup", [0.1]), item(2, "cup", [0.1])])
        self.assertFalse([group for group in groups if len(group) >= 3])

    def test_candidate_defaults_are_unverified(self):
        value = candidate("cup", 1, [item(i, "cup", [0.1]) for i in range(1, 4)])
        self.assertEqual("candidate", value["status"])
        self.assertEqual("ai_suggested", value["suggestion_status"])
        self.assertEqual("unverified", value["review_status"])

    def test_existing_or_interrupted_model_call_is_never_repeated(self):
        self.assertTrue(model_call_is_new({"runs": {}}, 1))
        for status in ("success", "failed", "timeout", "running"):
            self.assertFalse(model_call_is_new({"runs": {"1": {"status": status}}}, 1))

    def test_model_schema_requires_observed_structure(self):
        good = {
            "observed": {
                "product_subject": "center",
                "main_text": "top",
                "layout_structure": "vertical",
            },
            "inferred": {"information_density": "medium"},
        }
        self.assertTrue(valid_model_result(good))
        self.assertFalse(
            valid_model_result(
                {"observed": {}, "inferred": {"information_density": "medium"}}
            )
        )


if __name__ == "__main__":
    unittest.main()
