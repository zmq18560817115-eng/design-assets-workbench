from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from PIL import Image as PILImage
from pydantic import ValidationError
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from app import batch, config, crud, database, models
from app.agents import run_pipeline
from app.business_contract import (
    HISTORICAL_SOURCE_TYPES,
    PAGE_ROLES,
    parse_manifest,
)
from app.database import Base
from app.ingestion import dry_run_summary
from app.schemas import CaseBusinessUpdate, CaseReviewInput


class BusinessIngestionContractTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="business-contract-")
        self.root = Path(self.tmp.name)
        self.uploads = self.root / "uploads"
        self.uploads.mkdir()
        self.engine = create_engine(
            f"sqlite:///{self.root / 'test.db'}",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def tearDown(self):
        self.engine.dispose()
        self.tmp.cleanup()

    def _image(self, relative: str = "assets/a.png") -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        PILImage.new("RGB", (640, 960), "white").save(path)
        return path

    def _manifest(self, **overrides) -> Path:
        row = {
            "relative_path": "assets/a.png",
            "source_type": "company_published",
            "business_line": "母婴",
            "product_category": "吸奶器",
            "product_name": "P1",
            "channel": "小红书",
            "content_purpose": "产品卖点",
            "campaign_stage": "日常",
            "page_role": "cover_hook",
            "sequence_index": "1",
            "project_name": "项目A",
            "brief_ref": "B-1",
            "review_decision": "",
            "reviewer": "",
            "notes": "",
        }
        row.update(overrides)
        path = self.root / "manifest.csv"
        with path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(row))
            writer.writeheader()
            writer.writerow(row)
        return path

    def test_manifest_fields_override_folder_inference(self):
        self._image()
        report = parse_manifest(
            self.root, self._manifest(product_name="Manifest Product"),
            "company_published",
        )
        self.assertTrue(report.valid)
        self.assertEqual(report.rows[0]["product_name"], "Manifest Product")
        self.assertEqual(report.rows[0]["metadata_status"], "manifest")

    def test_manifest_reports_missing_file_duplicate_and_invalid_enum(self):
        path = self._manifest(page_role="not-a-role")
        report = parse_manifest(self.root, path, "company_published")
        self.assertFalse(report.valid)
        self.assertTrue(report.invalid_rows)

    def test_business_line_is_not_product_category(self):
        self._image()
        report = parse_manifest(
            self.root,
            self._manifest(business_line="母婴线", product_category="奶瓶"),
            "company_published",
        )
        self.assertEqual(report.rows[0]["business_line"], "母婴线")
        self.assertEqual(report.rows[0]["product_category"], "奶瓶")

    def test_page_role_invalid_value_is_rejected(self):
        with self.assertRaises(ValidationError):
            CaseBusinessUpdate(page_role="bad")
        self.assertIn("other", PAGE_ROLES)

    def test_ai_page_role_suggestion_is_not_verified(self):
        image_path = self._image()
        result = run_pipeline(str(image_path), enable_vlm=False)
        with self.Session() as db:
            image = models.Image(
                url="/uploads/a.png", filename="a.png",
                source_type="external_reference", uploader="tester",
            )
            db.add(image)
            db.flush()
            case = crud.create_case_from_analysis(db, image, result)
            db.commit()
            self.assertEqual(case.page_role, "other")
            self.assertEqual(case.trust_status, "ai_unverified")

    def test_historical_source_types_remain_supported(self):
        self.assertEqual(
            set(HISTORICAL_SOURCE_TYPES),
            {"company_finished_asset", "internal_reference"},
        )
        self._image()
        report = parse_manifest(
            self.root,
            self._manifest(source_type="internal_reference"),
            "external_reference",
        )
        self.assertTrue(report.valid)

    def test_dry_run_summary_has_no_database_side_effect(self):
        before = inspect(self.engine).get_table_names()
        summary = dry_run_summary(
            [{"source_type": "external_reference", "metadata_status": "inferred"}],
            None,
        )
        after = inspect(self.engine).get_table_names()
        self.assertEqual(before, after)
        self.assertEqual(summary["metadata_status"]["inferred"], 1)

    def test_old_database_is_upgraded_additively(self):
        old_engine = create_engine(f"sqlite:///{self.root / 'old.db'}")
        with old_engine.begin() as conn:
            conn.execute(text("CREATE TABLE cases (id INTEGER PRIMARY KEY)"))
        original = database.engine
        try:
            database.engine = old_engine
            database._auto_migrate()
        finally:
            database.engine = original
        columns = {col["name"] for col in inspect(old_engine).get_columns("cases")}
        self.assertTrue(
            {"product_name", "content_purpose", "page_role", "sequence_index", "brief_ref"}
            <= columns
        )
        old_engine.dispose()

    def test_external_batch_never_creates_gold_project_and_is_idempotent(self):
        image_path = self._image()
        original_session = batch.SessionLocal
        original_upload = config.UPLOAD_DIR
        batch.SessionLocal = self.Session
        config.UPLOAD_DIR = self.uploads
        item = {
            "path": str(image_path),
            "filename": image_path.name,
            "copy_to_uploads": True,
            "source_type": "external_reference",
            "asset_category": "layout",
            "project_name": "Reference Project",
            "metadata_status": "manifest",
        }
        try:
            first = batch.create_batch([item], background=False)
            second = batch.create_batch([item], background=False)
        finally:
            batch.SessionLocal = original_session
            config.UPLOAD_DIR = original_upload
        with self.Session() as db:
            self.assertEqual(db.query(models.Case).count(), 1)
            project = db.query(models.Project).one()
            self.assertFalse(project.is_gold)
            self.assertEqual(db.get(models.BatchImportJob, first).done, 1)
            self.assertEqual(db.get(models.BatchImportJob, second).skipped, 1)

    def test_manual_business_update_and_review_preserve_version(self):
        image_path = self._image()
        result = run_pipeline(str(image_path), enable_vlm=False)
        with self.Session() as db:
            image = models.Image(
                url="/uploads/a.png", filename="a.png",
                source_type="company_published", uploader="tester",
            )
            db.add(image)
            db.flush()
            case = crud.create_case_from_analysis(db, image, result)
            db.commit()
            crud.update_case_business_fields(
                db, case,
                CaseBusinessUpdate(
                    product_name="P1", content_purpose="产品卖点",
                    page_role="cover_hook", sequence_index=1, brief_ref="B-1",
                    business_line="母婴", product_category="吸奶器",
                    channel="小红书", campaign_stage="日常",
                ),
            )
            reviewed = crud.review_case(
                db, case,
                CaseReviewInput(
                    reviewer="设计负责人", trust_status="verified",
                    product_name="P1", content_purpose="产品卖点",
                    page_role="cover_hook", sequence_index=1, brief_ref="B-1",
                    keep_reasons=["层级清晰"], avoid_reasons=["文字过密"],
                ),
            )
            self.assertEqual(reviewed.trust_status, "verified")
            self.assertEqual(db.query(models.AnalysisVersion).count(), 2)
            self.assertEqual(db.query(models.CaseReview).count(), 1)


if __name__ == "__main__":
    unittest.main()
