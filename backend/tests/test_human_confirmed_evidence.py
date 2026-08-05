from __future__ import annotations

import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image as PILImage, PngImagePlugin
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import config, human_confirmed_evidence as service, models
from app.database import Base


class HumanConfirmedEvidenceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.engine = create_engine(f"sqlite:///{root / 'test.db'}")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.old_root, self.old_project, self.old_plans = config.COMPANY_ASSET_ROOT, config.PROJECT_DIR, service.PLAN_PATHS
        config.PROJECT_DIR = root
        config.COMPANY_ASSET_ROOT = root / "公司成品素材"
        original = config.COMPANY_ASSET_ROOT / "羊脂膏" / "target.png"
        annotated = root / "产品信息架构图" / "羊脂膏" / "box.png"
        original.parent.mkdir(parents=True); annotated.parent.mkdir(parents=True)
        PILImage.new("RGB", (40, 40), "white").save(original)
        PILImage.new("RGB", (40, 40), "blue").save(annotated)
        self.original, self.annotated = original, annotated
        self.sha = hashlib.sha256(original.read_bytes()).hexdigest()
        plans = root / "plans"; plans.mkdir()
        service.PLAN_PATHS = (plans / "pairing-import-plan.csv", plans / "paired-assets-full-import-plan.csv")
        for plan in service.PLAN_PATHS:
            with plan.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.writer(handle); writer.writerow(["category", "original", "annotation", "status", "source", "reviewer"])
                writer.writerow(["羊脂膏", "公司成品素材/羊脂膏/target.png", "羊脂膏/box.png", "pair_confirmed", "human_confirmed", "张茗淇"])
        # The older manual plan calls the reviewed source "confirmed"; the full
        # authoritative plan carries the explicit human_confirmed value.
        with service.PLAN_PATHS[0].open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle); writer.writerow(["category", "original", "annotation", "status", "source", "reviewer"])
            writer.writerow(["羊脂膏", "公司成品素材/羊脂膏/target.png", "羊脂膏/box.png", "pair_confirmed", "confirmed", "张茗淇"])
        project = models.Project(id=6, name="公司成品·羊脂膏", business_line="羊脂膏")
        self.db.add(project)
        annotation = models.DisinfectionAnnotation(
            id=224, annotated_image_path=str(annotated), original_image_path=str(original),
            source_sha256=hashlib.sha256(annotated.read_bytes()).hexdigest(), source_type="company_published",
            product_category="羊脂膏", status="pending_review", annotation_verified=None,
            company_recommended=None, dataset_split="", regions_json="[]",
        )
        self.db.add(annotation); self.db.flush()
        self.db.add(models.DisinfectionAnnotationVersion(
            annotation_id=224, version=1, source="paired", editor="张茗淇",
            payload_json=json.dumps({
                "pairing_status": "pair_confirmed", "pairing_source": "human_confirmed",
                "pairing_review": {"reviewer": "张茗淇"},
                "original_relative_path": "公司成品素材/羊脂膏/target.png",
                "annotation_relative_path": "羊脂膏/box.png",
            }, ensure_ascii=False),
        ))
        # Same pixels, different exact SHA: ordinary pHash logic regards it as near-duplicate.
        near_path = root / "near.png"; metadata = PngImagePlugin.PngInfo(); metadata.add_text("variant", "near")
        PILImage.new("RGB", (40, 40), "white").save(near_path, pnginfo=metadata)
        near_image = models.Image(url=str(near_path), filename="near.png", source_type="company_published", phash=service.imagehash.dhash(str(near_path)))
        self.db.add(near_image); self.db.flush()
        self.db.add(models.Case(id=88, image_id=near_image.id, name="near", product_category="羊脂膏", asset_category="layout"))
        self.db.commit()

    def tearDown(self):
        config.COMPANY_ASSET_ROOT, config.PROJECT_DIR, service.PLAN_PATHS = self.old_root, self.old_project, self.old_plans
        self.db.close(); self.engine.dispose(); self.temp.cleanup()

    def values(self, **updates):
        values = dict(annotation_id=224, expected_sha256=self.sha, project_id=6, reviewer="张茗淇", product_category="羊脂膏", source_type="company_published")
        values.update(updates); return values

    def test_dry_run_records_near_duplicate_without_skipping(self):
        result = service.inspect_repair(self.db, **self.values())
        self.assertEqual((result["near_duplicate_case_id"], result["perceptual_hash_distance"]), (88, 0))
        self.assertEqual((result["would_create_image"], result["would_create_case"], result["model_calls"]), (1, 1, 0))

    def test_execute_is_idempotent_and_preserves_annotation_gates(self):
        first = service.execute_repair(self.db, **self.values()); second = service.execute_repair(self.db, **self.values())
        self.assertTrue(first["executed"]); self.assertTrue(second["idempotent"])
        self.assertEqual(self.db.query(models.Image).filter_by(original_sha256=self.sha).count(), 1)
        self.assertEqual(self.db.query(models.CompanyEvidenceRepairAudit).count(), 1)
        annotation = self.db.get(models.DisinfectionAnnotation, 224)
        self.assertEqual(annotation.case_id, first["case_id"]); self.assertEqual(annotation.status, "pending_review")
        self.assertIsNone(annotation.annotation_verified); self.assertIsNone(annotation.company_recommended)
        audit = self.db.query(models.CompanyEvidenceRepairAudit).one()
        self.assertEqual((audit.near_duplicate_case_id, audit.perceptual_hash_distance, audit.reviewer), (88, 0, "张茗淇"))

    def test_non_human_pairing_is_rejected(self):
        version = self.db.query(models.DisinfectionAnnotationVersion).one()
        payload = json.loads(version.payload_json); payload["pairing_source"] = "automatic_exact_match"; version.payload_json = json.dumps(payload); self.db.commit()
        with self.assertRaisesRegex(ValueError, "human_confirmed"):
            service.inspect_repair(self.db, **self.values())

    def test_outside_root_sha_category_and_source_are_rejected(self):
        annotation = self.db.get(models.DisinfectionAnnotation, 224)
        annotation.original_image_path = str(Path(self.temp.name) / "outside.png")
        Path(annotation.original_image_path).write_bytes(self.original.read_bytes()); self.db.commit()
        with self.assertRaisesRegex(ValueError, "公司成品目录"):
            service.inspect_repair(self.db, **self.values())
        annotation.original_image_path = str(self.original); self.db.commit()
        with self.assertRaisesRegex(ValueError, "SHA"):
            service.inspect_repair(self.db, **self.values(expected_sha256="0" * 64))
        with self.assertRaisesRegex(ValueError, "品类"):
            service.inspect_repair(self.db, **self.values(product_category="吸奶器"))
        with self.assertRaisesRegex(ValueError, "source_type"):
            service.inspect_repair(self.db, **self.values(source_type="external_reference"))

    def test_transaction_failure_rolls_everything_back(self):
        with self.assertRaisesRegex(RuntimeError, "rollback"):
            service.execute_repair(self.db, fail_after="image", **self.values())
        self.assertEqual(self.db.query(models.Image).filter_by(original_sha256=self.sha).count(), 0)
        self.assertEqual(self.db.query(models.Case).count(), 1)
        self.assertEqual(self.db.query(models.CompanyEvidenceRepairAudit).count(), 0)
        self.assertIsNone(self.db.get(models.DisinfectionAnnotation, 224).case_id)
