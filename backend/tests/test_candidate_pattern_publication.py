from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import candidate_patterns, models
from app.database import Base


class CandidatePatternPublicationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.engine = create_engine(f"sqlite:///{root / 'test.db'}")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.old_path = candidate_patterns.CANDIDATE_PATH
        candidate_patterns.CANDIDATE_PATH = root / "candidates.json"
        self.candidates = [self.candidate("cup-01", "恒温杯", [1, 2, 3]), self.candidate("cup-02", "恒温杯", [4, 5, 6]), self.candidate("pump-01", "吸奶器", [7, 8, 9])]
        candidate_patterns.CANDIDATE_PATH.write_text(json.dumps({"candidates": self.candidates}, ensure_ascii=False), encoding="utf-8")
        for annotation_id, category in [(i, "恒温杯" if i <= 6 else "吸奶器") for i in range(1, 10)]:
            filename = f"case-{annotation_id}.png"
            image = models.Image(url=f"/uploads/{filename}", filename=filename, source_type="company_published")
            self.db.add(image); self.db.flush()
            self.db.add(models.Case(image_id=image.id, name=filename, product_category=category, status="public"))
            self.db.add(models.DisinfectionAnnotation(
                id=annotation_id, source_sha256=f"sha-{annotation_id}", source_type="company_published",
                product_category=category, original_image_path=str(root / filename), status="pending_review",
                canvas_width=1000, canvas_height=1000, orientation="square", structure_cluster_key="ready",
                regions_json=json.dumps(self.regions()),
            ))
        self.db.commit(); candidate_patterns.ensure_states(self.db)

    def tearDown(self):
        candidate_patterns.CANDIDATE_PATH = self.old_path
        self.db.close(); self.engine.dispose(); self.temp.cleanup()

    @staticmethod
    def regions():
        return [
            {"id": "layout", "type": "layout_block", "x": .05, "y": .05, "width": .9, "height": .9, "confidence": 1},
            {"id": "text", "type": "main_text", "x": .1, "y": .1, "width": .8, "height": .15, "confidence": 1},
            {"id": "product", "type": "product_image", "x": .2, "y": .35, "width": .6, "height": .5, "confidence": 1},
        ]

    @staticmethod
    def candidate(candidate_id, category, ids):
        return {
            "candidate_id": candidate_id, "pattern_name_suggestion": f"{category}中心产品模式", "category": category,
            "case_count": len(ids), "representative_ids": [ids[0]], "evidence_annotation_ids": ids,
            "product_position": "中中", "title_position": "上中", "reading_order": "文字在产品上方",
            "required_modules": ["layout_block", "product_image", "main_text"], "optional_modules": [],
            "suitable_pages": ["功能说明"], "unsuitable_pages": ["极简封面"],
            "average_information_density": "high", "average_whitespace_ratio": .1,
        }

    def action(self, candidate_id, action, **values):
        return candidate_patterns.apply_action(self.db, candidate_id, {
            "action": action, "reviewer": values.pop("reviewer", "负责人"),
            "reviewer_role": values.pop("reviewer_role", "design_owner"), **values,
        })

    def test_keep_and_owner_confirmation_are_independent_and_append_history(self):
        self.action("cup-01", "keep", reviewer_role="reviewer")
        self.action("cup-01", "owner_confirm")
        row = self.db.get(models.LayoutPatternCandidateReview, "cup-01")
        self.assertEqual(row.decision, "keep")
        self.assertTrue(row.owner_confirmed)
        self.assertEqual([item.action for item in self.db.query(models.LayoutPatternCandidateReviewEvent).filter_by(candidate_id="cup-01").all()], ["keep", "owner_confirm"])

    def test_owner_without_keep_and_keep_without_owner_cannot_publish(self):
        with self.assertRaisesRegex(ValueError, "必须先选择保留"):
            self.action("cup-01", "owner_confirm")
        self.action("cup-01", "keep", reviewer_role="reviewer")
        with self.assertRaisesRegex(ValueError, "负责人尚未确认"):
            self.action("cup-01", "publish")

    def test_less_than_three_evidence_cannot_publish(self):
        self.candidates[0]["evidence_annotation_ids"] = [1, 2]
        candidate_patterns.CANDIDATE_PATH.write_text(json.dumps({"candidates": self.candidates}, ensure_ascii=False), encoding="utf-8")
        self.action("cup-01", "keep", reviewer_role="reviewer"); self.action("cup-01", "owner_confirm")
        with self.assertRaisesRegex(ValueError, "少于3个"):
            self.action("cup-01", "publish")

    def test_cross_category_merge_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "禁止跨品类合并"):
            self.action("pump-01", "merge", merge_target_id="cup-01", reviewer_role="reviewer")

    def test_needs_box_fix_cannot_publish(self):
        annotation = self.db.get(models.DisinfectionAnnotation, 1); annotation.structure_cluster_key = "needs_box_fix"; self.db.commit()
        self.action("cup-01", "keep", reviewer_role="reviewer"); self.action("cup-01", "owner_confirm")
        with self.assertRaisesRegex(ValueError, "needs_box_fix"):
            self.action("cup-01", "publish")

    def test_missing_name_scene_or_reading_order_cannot_publish(self):
        for field in ("pattern_name_suggestion", "suitable_pages", "reading_order"):
            original = self.candidates[0][field]; self.candidates[0][field] = "" if field != "suitable_pages" else []
            candidate_patterns.CANDIDATE_PATH.write_text(json.dumps({"candidates": self.candidates}, ensure_ascii=False), encoding="utf-8")
            state = self.db.get(models.LayoutPatternCandidateReview, "cup-01"); state.display_name = ""; state.decision = "keep"; state.owner_confirmed = True; self.db.commit()
            self.assertTrue(candidate_patterns.publication_missing(self.db, self.candidates[0], state))
            self.candidates[0][field] = original

    def test_publish_is_idempotent_and_traceable(self):
        self.action("cup-01", "keep", reviewer_role="reviewer"); self.action("cup-01", "owner_confirm")
        first = self.action("cup-01", "publish"); second = self.action("cup-01", "publish")
        self.assertEqual(first["formal_pattern_id"], second["formal_pattern_id"])
        self.assertEqual(self.db.query(models.LayoutPattern).count(), 1)
        pattern = self.db.get(models.LayoutPattern, first["formal_pattern_id"])
        self.assertEqual(pattern.review_status, "verified")
        self.assertEqual(pattern.source_candidate_id, "cup-01")
        self.assertEqual(json.loads(pattern.source_candidate_ids_json), ["cup-01"])
        self.assertEqual(len(json.loads(pattern.evidence_case_ids_json)), 3)
        actions = [item.action for item in self.db.query(models.LayoutPatternCandidateReviewEvent).filter_by(candidate_id="cup-01").all()]
        self.assertIn("formal_pattern_created", actions); self.assertIn("formal_verified", actions)

    def test_no_merge_keeps_evidence_count(self):
        state = self.db.get(models.LayoutPatternCandidateReview, "cup-01"); state.decision = "keep"; self.db.commit()
        result = candidate_patterns.aggregate_evidence(self.db, "cup-01")
        self.assertEqual(result["evidence_count"], 3)
        self.assertEqual(result["source_candidate_ids"], ["cup-01"])

    def test_single_and_multi_level_merge_aggregate_and_deduplicate(self):
        state1 = self.db.get(models.LayoutPatternCandidateReview, "cup-01"); state1.decision = "keep"
        state2 = self.db.get(models.LayoutPatternCandidateReview, "cup-02"); state2.decision = "merge"; state2.merge_target_id = "cup-01"
        state3 = self.db.get(models.LayoutPatternCandidateReview, "pump-01")
        # Recast the third fixture as the same category solely for recursive aggregation coverage.
        self.candidates[2]["category"] = "恒温杯"; self.candidates[2]["evidence_annotation_ids"] = [6, 7, 8]
        candidate_patterns.CANDIDATE_PATH.write_text(json.dumps({"candidates": self.candidates}, ensure_ascii=False), encoding="utf-8")
        for annotation_id in (7, 8):
            annotation = self.db.get(models.DisinfectionAnnotation, annotation_id); annotation.product_category = "恒温杯"
            annotation_case = self.db.query(models.Case).join(models.Image).filter(models.Image.filename == f"case-{annotation_id}.png").one(); annotation_case.product_category = "恒温杯"
        state3.decision = "merge"; state3.merge_target_id = "cup-02"; self.db.commit()
        result = candidate_patterns.aggregate_evidence(self.db, "cup-01")
        self.assertEqual(result["source_candidate_ids"], ["cup-01", "cup-02", "pump-01"])
        self.assertEqual(result["annotation_ids"], [1, 2, 3, 4, 5, 6, 7, 8])
        self.assertEqual(result["deduplicated_count"], 1)
        self.assertEqual(result["evidence_count"], 8)

    def test_distinct_annotations_for_the_same_case_are_deduplicated(self):
        one = self.db.get(models.LayoutPatternCandidateReview, "cup-01"); one.decision = "keep"
        two = self.db.get(models.LayoutPatternCandidateReview, "cup-02"); two.decision = "merge"; two.merge_target_id = "cup-01"
        annotation = self.db.get(models.DisinfectionAnnotation, 4)
        annotation.original_image_path = str(Path(annotation.original_image_path).with_name("case-1.png"))
        self.db.commit()
        result = candidate_patterns.aggregate_evidence(self.db, "cup-01")
        self.assertEqual(result["annotation_ids"], [1, 2, 3, 4, 5, 6])
        self.assertEqual(result["evidence_count"], 5)
        self.assertEqual(result["case_deduplicated_count"], 1)

    def test_cycle_and_rootless_chain_are_rejected(self):
        one = self.db.get(models.LayoutPatternCandidateReview, "cup-01"); two = self.db.get(models.LayoutPatternCandidateReview, "cup-02")
        root = self.db.get(models.LayoutPatternCandidateReview, "pump-01"); root.decision = "keep"
        one.decision = two.decision = "merge"; one.merge_target_id = "cup-02"; two.merge_target_id = "cup-01"; self.db.commit()
        with self.assertRaisesRegex(ValueError, "循环合并"):
            candidate_patterns.aggregate_evidence(self.db, "pump-01")
        one.decision = "pending"; one.merge_target_id = ""; two.merge_target_id = "cup-01"; self.db.commit()
        with self.assertRaisesRegex(ValueError, "无根合并链"):
            candidate_patterns.aggregate_evidence(self.db, "pump-01")
        one.decision = "merge"; one.merge_target_id = "missing-candidate"; two.decision = "pending"; self.db.commit()
        with self.assertRaisesRegex(ValueError, "合并目标不存在"):
            candidate_patterns.aggregate_evidence(self.db, "pump-01")

    def test_reject_and_independent_keep_are_not_aggregated(self):
        one = self.db.get(models.LayoutPatternCandidateReview, "cup-01"); one.decision = "keep"
        two = self.db.get(models.LayoutPatternCandidateReview, "cup-02"); two.decision = "reject"
        three = self.db.get(models.LayoutPatternCandidateReview, "pump-01"); three.decision = "keep"; self.db.commit()
        result = candidate_patterns.aggregate_evidence(self.db, "cup-01")
        self.assertEqual(result["source_candidate_ids"], ["cup-01"])

    def test_non_company_and_untraceable_evidence_are_rejected(self):
        state = self.db.get(models.LayoutPatternCandidateReview, "cup-01"); state.decision = "keep"
        annotation = self.db.get(models.DisinfectionAnnotation, 1); annotation.source_type = "external_reference"; self.db.commit()
        with self.assertRaisesRegex(ValueError, "非company_published"):
            candidate_patterns.aggregate_evidence(self.db, "cup-01")
        annotation.source_type = "company_published"; annotation.original_image_path = "missing-ambiguous.png"; self.db.commit()
        with self.assertRaisesRegex(ValueError, "无法追溯公司案例"):
            candidate_patterns.aggregate_evidence(self.db, "cup-01")

    def test_published_snapshot_does_not_change_with_candidate_state(self):
        self.action("cup-01", "keep", reviewer_role="reviewer"); self.action("cup-01", "owner_confirm")
        published = self.action("cup-01", "publish"); pattern = self.db.get(models.LayoutPattern, published["formal_pattern_id"])
        frozen_annotations = pattern.evidence_annotation_ids_json; frozen_sources = pattern.source_candidate_ids_json
        state = self.db.get(models.LayoutPatternCandidateReview, "cup-02"); state.decision = "merge"; state.merge_target_id = "cup-01"; self.db.commit()
        self.assertEqual(pattern.evidence_annotation_ids_json, frozen_annotations)
        self.assertEqual(pattern.source_candidate_ids_json, frozen_sources)

    def test_merge_and_reject_archive_without_deleting_candidates(self):
        self.action("cup-01", "merge", merge_target_id="cup-02", reviewer_role="reviewer")
        self.action("pump-01", "reject", reviewer_role="reviewer")
        self.assertEqual(len(candidate_patterns.load_candidates()), 3)
        self.assertEqual(self.db.get(models.LayoutPatternCandidateReview, "cup-01").decision, "merge")
        self.assertEqual(self.db.get(models.LayoutPatternCandidateReview, "pump-01").decision, "reject")

    def test_legacy_snapshot_does_not_invent_keep_before_owner_confirmation(self):
        self.db.query(models.LayoutPatternCandidateReviewEvent).delete(); self.db.query(models.LayoutPatternCandidateReview).delete(); self.db.commit()
        self.candidates[0]["human_review_status"] = "owner_confirmed"; self.candidates[0]["design_owner"] = "Mingqi"
        candidate_patterns.CANDIDATE_PATH.write_text(json.dumps({"candidates": self.candidates}, ensure_ascii=False), encoding="utf-8")
        candidate_patterns.ensure_states(self.db)
        row = self.db.get(models.LayoutPatternCandidateReview, "cup-01")
        self.assertEqual(row.decision, "pending"); self.assertTrue(row.owner_confirmed)
        self.assertEqual(self.db.query(models.LayoutPatternCandidateReviewEvent).filter_by(candidate_id="cup-01").one().action, "legacy_snapshot")

    def test_legacy_formal_pattern_survives_candidate_state_upgrade(self):
        legacy = models.LayoutPattern(name="历史正式模式", review_status="verified", editor="owner")
        self.db.add(legacy); self.db.commit(); legacy_id = legacy.id
        candidate_patterns.ensure_states(self.db)
        self.assertEqual(self.db.get(models.LayoutPattern, legacy_id).name, "历史正式模式")
        self.assertEqual(len(candidate_patterns.load_candidates()), 3)


if __name__ == "__main__":
    unittest.main()
