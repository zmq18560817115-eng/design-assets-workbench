from __future__ import annotations

import json
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app import crud, models
from app.database import SessionLocal
from app.layout_blueprint import validate_modules
from app.layout_patterns import (
    DISCOVERY_METHOD,
    _confidence,
    discover_candidates,
    latest_verified_blueprints,
    structure_similarity,
)
from app.main import app


def company_case(db, **values) -> models.Case:
    image = models.Image(
        url=f"/uploads/fixture-{len(db.new)}.png",
        filename="fixture.png",
        source_type="company_finished_asset",
    )
    db.add(image)
    db.flush()
    case = models.Case(image_id=image.id, trust_status="verified", **values)
    db.add(case)
    db.flush()
    return case


class LayoutPatternDiscoveryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.client.__enter__()
        cls.db = SessionLocal()
        cls.case_ids: list[int] = []
        cls.group_blueprints: list[list[models.LayoutBlueprint]] = []
        fixture_path = Path(__file__).parent / "fixtures" / "layout_pattern_discovery_v2.json"
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        structures = [
            (
                item["canvas_ratio"],
                "square" if item["canvas_ratio"] == "1:1"
                else ("landscape" if item["canvas_ratio"] == "16:9" else "portrait"),
                item["density"],
                item["modules"],
            )
            for item in fixture["structures"]
        ]
        assert fixture["case_count"] == 15
        for group_index, (ratio, orientation, density, types) in enumerate(structures):
            group: list[models.LayoutBlueprint] = []
            for item_index in range(3):
                case = company_case(
                    cls.db,
                    name=f"发现测试-{group_index}-{item_index}",
                    product_category="fixture",
                    status="public",
                )
                cls.case_ids.append(case.id)
                modules = cls.make_modules(types, offset=item_index * 0.005)
                if item_index == 2:
                    modules.append({
                        "id": "decoration-1", "type": "decoration",
                        "label": "装饰", "x": .82, "y": .84,
                        "width": .08, "height": .08, "priority": 9,
                        "importance": 3, "alignment": "center",
                        "description": "", "content_summary": "",
                        "confidence": .9,
                    })
                # First case has two verified versions; only v2 may be selected.
                if group_index == 0 and item_index == 0:
                    cls.db.add(models.LayoutBlueprint(
                        case_id=case.id, canvas_ratio=ratio,
                        orientation=orientation, information_density=density,
                        reading_flow="top-to-bottom", grid_columns=6, grid_rows=12,
                        module_count=1,
                        modules_json=json.dumps(cls.make_modules(["logo"])),
                        layout_signature="obsolete", version=1,
                        review_status="verified", text_image_ratio=.5,
                    ))
                blueprint = models.LayoutBlueprint(
                    case_id=case.id, canvas_ratio=ratio,
                    orientation=orientation, information_density=density,
                    reading_flow="left-to-right" if orientation == "landscape" else "top-to-bottom",
                    grid_columns=12 if orientation == "landscape" else 6,
                    grid_rows=6 if orientation == "landscape" else 12,
                    module_count=len(modules), modules_json=json.dumps(modules),
                    layout_signature=f"fixture-group-{group_index}",
                    version=2 if group_index == 0 and item_index == 0 else 1,
                    review_status="verified", text_image_ratio=.5,
                )
                cls.db.add(blueprint)
                group.append(blueprint)
            cls.group_blueprints.append(group)

        # Same structure but unverified: never eligible.
        unverified_case = company_case(
            cls.db, name="未确认蓝图", status="public"
        )
        cls.db.add(models.LayoutBlueprint(
            case_id=unverified_case.id, canvas_ratio="3:4",
            orientation="portrait", information_density="low",
            reading_flow="top-to-bottom", grid_columns=6, grid_rows=12,
            module_count=2,
            modules_json=json.dumps(cls.make_modules(["main_title", "product_image"])),
            version=1, review_status="ai_generated", text_image_ratio=.5,
        ))
        # Invalid verified blueprint: validator excludes it.
        invalid_case = company_case(
            cls.db, name="非法蓝图", status="public"
        )
        cls.db.add(models.LayoutBlueprint(
            case_id=invalid_case.id, canvas_ratio="3:4",
            orientation="portrait", information_density="low",
            reading_flow="top-to-bottom", grid_columns=6, grid_rows=12,
            module_count=1, modules_json=json.dumps([{
                "id": "bad", "type": "main_title", "x": .9, "y": .1,
                "width": .4, "height": .1,
            }]), version=1, review_status="verified", text_image_ratio=.5,
        ))
        # Only two valid cases in this bucket: below minimum evidence.
        for index in range(2):
            case = company_case(
                cls.db, name=f"不足证据-{index}", status="public"
            )
            modules = cls.make_modules(["logo"])
            cls.db.add(models.LayoutBlueprint(
                case_id=case.id, canvas_ratio="9:16",
                orientation="portrait", information_density="low",
                reading_flow="top-to-bottom", grid_columns=4, grid_rows=8,
                module_count=len(modules), modules_json=json.dumps(modules),
                version=1, review_status="verified", text_image_ratio=.5,
            ))
        cls.db.commit()

    @staticmethod
    def make_modules(types: list[str], offset: float = 0) -> list[dict]:
        modules = []
        for index, module_type in enumerate(types):
            modules.append({
                "id": f"{module_type}-source-{index}",
                "type": module_type, "label": module_type,
                "x": round(.05 + (index % 3) * .27 + offset, 4),
                "y": round(.06 + index * .19 + offset, 4),
                "width": .22, "height": .12,
                "priority": index + 1, "importance": 1,
                "alignment": "center", "description": "",
                "content_summary": "", "confidence": .95,
            })
        return modules

    @classmethod
    def tearDownClass(cls):
        cls.db.close()
        cls.client.__exit__(None, None, None)

    def candidates(self):
        return discover_candidates(self.db)

    def test_01_only_verified_blueprints_participate(self):
        eligible = latest_verified_blueprints(self.db)
        self.assertTrue(all(item.review_status == "verified" for item in eligible))
        self.assertFalse(any(item.case.name == "未确认蓝图" for item in eligible))
        self.assertFalse(any(item.case.name == "非法蓝图" for item in eligible))

    def test_02_latest_verified_version_per_case(self):
        eligible = latest_verified_blueprints(self.db)
        target = next(item for item in eligible if item.case_id == self.case_ids[0])
        self.assertEqual(target.version, 2)
        self.assertNotEqual(target.layout_signature, "obsolete")

    def test_03_less_than_three_distinct_cases_is_excluded(self):
        self.assertFalse(any(item["canvas_ratio"] == "9:16" for item in self.candidates()))

    def test_04_similar_blueprints_share_candidate(self):
        candidate = next(item for item in self.candidates() if item["canvas_ratio"] == "1:1")
        self.assertEqual(candidate["evidence_count"], 3)

    def test_05_different_orientation_not_merged(self):
        self.assertEqual(
            structure_similarity(self.group_blueprints[0][0], self.group_blueprints[3][0])["canvas_density"],
            0.0,
        )

    def test_06_different_structure_not_forced_together(self):
        score = structure_similarity(self.group_blueprints[0][0], self.group_blueprints[4][0])
        self.assertLess(score["module_types"], 1.0)
        self.assertEqual(len(self.candidates()), 5)

    def test_07_required_modules_use_eighty_percent_rule(self):
        candidate = next(item for item in self.candidates() if item["information_density"] == "low")
        self.assertIn("main_title-1", candidate["required_modules_json"])
        self.assertIn("product_image-1", candidate["required_modules_json"])

    def test_08_optional_modules_use_thirty_percent_rule(self):
        candidate = next(item for item in self.candidates() if item["information_density"] == "low")
        self.assertIn("decoration-1", candidate["optional_modules_json"])

    def test_09_average_coordinates_are_valid(self):
        for candidate in self.candidates():
            validate_modules(
                candidate["average_positions_json"],
                len(candidate["average_positions_json"]),
            )

    def test_10_evidence_count_is_distinct_cases(self):
        self.assertTrue(all(item["evidence_count"] == 3 for item in self.candidates()))
        self.assertEqual(len(self.candidates()[0]["evidence_case_ids_json"]), 3)

    def test_11_confidence_level_boundaries(self):
        self.assertEqual(_confidence(3), "candidate")
        self.assertEqual(_confidence(5), "medium")
        self.assertEqual(_confidence(8), "high")

    def test_12_pattern_code_is_stable(self):
        first = [item["pattern_code"] for item in self.candidates()]
        second = [item["pattern_code"] for item in self.candidates()]
        self.assertEqual(first, second)
        self.assertEqual(len(first), len(set(first)))

    def test_13_dry_run_does_not_write(self):
        before = self.db.query(models.LayoutPattern).count()
        response = self.client.post("/api/layout-patterns/rebuild", json={
            "dry_run": True, "similarity_threshold": .72,
            "minimum_evidence": 3,
        })
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["candidate_count"], 5)
        self.assertEqual(self.db.query(models.LayoutPattern).count(), before)

    def test_14_rebuild_is_idempotent(self):
        first = self.client.post("/api/layout-patterns/rebuild", json={
            "dry_run": False, "similarity_threshold": .72,
            "minimum_evidence": 3,
        })
        self.assertEqual(first.status_code, 200, first.text)
        after_first = self.db.query(models.LayoutPattern).count()
        second = self.client.post("/api/layout-patterns/rebuild", json={
            "dry_run": False, "similarity_threshold": .72,
            "minimum_evidence": 3,
        })
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(self.db.query(models.LayoutPattern).count(), after_first)
        self.assertEqual(second.json()["written"], 0)
        self.assertEqual(second.json()["updated"], 5)

    def test_15_verified_pattern_is_not_overwritten(self):
        pattern = self.db.query(models.LayoutPattern).filter(
            models.LayoutPattern.discovery_method == DISCOVERY_METHOD
        ).first()
        result = self.client.post(
            f"/api/layout-patterns/{pattern.id}/verify",
            json={"editor": "设计负责人"},
        )
        self.assertEqual(result.status_code, 200, result.text)
        pattern.name = "人工确认名称"; self.db.commit()
        self.client.post("/api/layout-patterns/rebuild", json={"dry_run": False})
        self.db.refresh(pattern)
        self.assertEqual(pattern.name, "人工确认名称")
        self.assertEqual(pattern.review_status, "verified")

    def test_16_disabled_pattern_is_not_restored(self):
        pattern = self.db.query(models.LayoutPattern).filter(
            models.LayoutPattern.discovery_method == DISCOVERY_METHOD,
            models.LayoutPattern.review_status == "draft",
        ).first()
        result = self.client.post(
            f"/api/layout-patterns/{pattern.id}/disable",
            json={"editor": "设计负责人"},
        )
        self.assertEqual(result.status_code, 200, result.text)
        self.client.post("/api/layout-patterns/rebuild", json={"dry_run": False})
        self.db.refresh(pattern)
        self.assertEqual(pattern.review_status, "disabled")

    def test_17_manual_pattern_is_not_overwritten(self):
        pattern = self.db.query(models.LayoutPattern).filter(
            models.LayoutPattern.discovery_method == DISCOVERY_METHOD,
            models.LayoutPattern.review_status == "draft",
        ).first()
        pattern.discovery_method = ""
        pattern.name = "人工修改模式"
        self.db.commit()
        self.client.post("/api/layout-patterns/rebuild", json={"dry_run": False})
        self.db.refresh(pattern)
        self.assertEqual(pattern.name, "人工修改模式")

    def test_18_evidence_endpoint_is_traceable(self):
        pattern = self.db.query(models.LayoutPattern).filter(
            models.LayoutPattern.discovery_method == DISCOVERY_METHOD
        ).first()
        response = self.client.get(f"/api/layout-patterns/{pattern.id}/evidence")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["evidence_count"], 3)
        self.assertEqual(len(body["cases"]), 3)
        self.assertEqual(len(body["blueprints"]), 3)
        self.assertEqual(len(body["similarities"]), 3)

    def test_19_legacy_pattern_remains_readable(self):
        legacy = models.LayoutPattern(
            name="旧人工模式", pattern_code="", review_status="human_edited",
            modules_json="[]", source_blueprint_ids="[]",
            source_case_ids="[]",
        )
        self.db.add(legacy); self.db.commit()
        response = self.client.get(f"/api/layout-patterns/{legacy.id}")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["name"], "旧人工模式")

    def test_20_automatic_discovery_ignores_legacy_weights(self):
        # The service has no PreferenceEvent/company profile/service-run inputs.
        candidate = self.candidates()[0]
        self.assertEqual(candidate["discovery_method"], DISCOVERY_METHOD)
        self.assertNotIn("preference", json.dumps(candidate).lower())
        self.assertNotIn("color", json.dumps(candidate).lower())

    def test_21_external_and_rejected_evidence_never_form_company_pattern(self):
        blocked_case_ids = []
        modules = self.make_modules(["main_title", "product_image"])
        for source_type, trust_status in (
            ("external_reference", "verified"),
            ("external_reference", "verified"),
            ("external_reference", "verified"),
            ("company_finished_asset", "rejected"),
        ):
            image = models.Image(
                url=f"/uploads/blocked-{len(blocked_case_ids)}.png",
                filename="blocked.png",
                source_type=source_type,
            )
            self.db.add(image)
            self.db.flush()
            case = models.Case(
                image_id=image.id,
                name=f"blocked-{len(blocked_case_ids)}",
                trust_status=trust_status,
                status="public",
            )
            self.db.add(case)
            self.db.flush()
            blocked_case_ids.append(case.id)
            self.db.add(models.LayoutBlueprint(
                case_id=case.id,
                canvas_ratio="4:5",
                orientation="portrait",
                information_density="low",
                reading_flow="top-to-bottom",
                grid_columns=6,
                grid_rows=12,
                module_count=len(modules),
                modules_json=json.dumps(modules),
                version=1,
                review_status="verified",
                text_image_ratio=.5,
            ))
        self.db.commit()
        eligible_ids = {
            blueprint.case_id for blueprint in latest_verified_blueprints(self.db)
        }
        self.assertFalse(eligible_ids.intersection(blocked_case_ids))
        evidence_ids = {
            case_id
            for candidate in self.candidates()
            for case_id in candidate["evidence_case_ids_json"]
        }
        self.assertFalse(evidence_ids.intersection(blocked_case_ids))
