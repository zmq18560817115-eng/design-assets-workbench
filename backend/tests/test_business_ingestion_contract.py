from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from unittest.mock import patch
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
    is_company_evidence,
    normalize_new_source_type,
    parse_manifest,
)
from app.database import Base
from app.ingestion import dry_run_summary
from app.main import batch_review_cases
from app.schemas import (
    BatchReviewInput,
    CaseBusinessUpdate,
    CaseReviewInput,
)
from scripts import import_asset_library, import_company_finished_assets


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

    def test_review_and_batch_review_do_not_clear_business_fields(self):
        image_path = self._image()
        result = run_pipeline(str(image_path), enable_vlm=False)
        with self.Session() as db:
            image = models.Image(
                url="/uploads/a.png",
                filename="a.png",
                source_type="company_published",
                uploader="tester",
            )
            db.add(image)
            db.flush()
            case = crud.create_case_from_analysis(db, image, result)
            crud.update_case_business_fields(
                db,
                case,
                CaseBusinessUpdate(
                    product_name="P1",
                    content_purpose="产品卖点",
                    page_role="cover_hook",
                    sequence_index=3,
                    brief_ref="B-3",
                    business_line="母婴",
                    product_category="吸奶器",
                    channel="小红书",
                    campaign_stage="日常",
                ),
            )
            crud.review_case(
                db,
                case,
                CaseReviewInput(reviewer="reviewer", trust_status="verified"),
            )
            batch_review_cases(
                BatchReviewInput(
                    case_ids=[case.id],
                    action="confirm",
                    reviewer="reviewer",
                ),
                db,
            )
            db.refresh(case)
            self.assertEqual(
                (
                    case.product_name,
                    case.content_purpose,
                    case.page_role,
                    case.sequence_index,
                    case.brief_ref,
                ),
                ("P1", "产品卖点", "cover_hook", 3, "B-3"),
            )

    def test_invalid_new_source_type_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "invalid source_type"):
            normalize_new_source_type("unused_internal", "external_reference")
        with self.assertRaisesRegex(ValueError, "invalid source_type"):
            batch.create_batch(
                [{
                    "path": "unused",
                    "filename": "unused.png",
                    "source_type": "internal_reference",
                }],
                background=False,
            )
        self.assertFalse(is_company_evidence("company_revision", "ai_unverified"))
        self.assertTrue(is_company_evidence("company_revision", "verified"))
        self.assertFalse(is_company_evidence("company_published", "rejected"))

    def test_local_only_batch_disables_visual_model(self):
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
        }
        try:
            with patch("app.batch.run_pipeline", wraps=run_pipeline) as mocked:
                batch.create_batch(
                    [item], background=False, enable_vlm=False
                )
            self.assertIs(mocked.call_args.kwargs["enable_vlm"], False)
        finally:
            batch.SessionLocal = original_session
            config.UPLOAD_DIR = original_upload

    def test_local_only_import_scripts_disable_visual_model(self):
        self._image("line/a.png")
        with (
            patch.object(import_asset_library, "init_db"),
            patch.object(import_asset_library, "close_db"),
            patch.object(
                import_asset_library,
                "execute_items",
                return_value={"failed": 0},
            ) as external_execute,
            patch.object(
                sys,
                "argv",
                [
                    "import_asset_library.py",
                    str(self.root),
                    "--execute",
                    "--local-only",
                ],
            ),
        ):
            self.assertEqual(import_asset_library.main(), 0)
        self.assertIs(external_execute.call_args.kwargs["enable_vlm"], False)

        with (
            patch.object(import_company_finished_assets, "init_db"),
            patch.object(import_company_finished_assets, "close_db"),
            patch.object(
                import_company_finished_assets,
                "execute_items",
                return_value={"failed": 0},
            ) as company_execute,
            patch.object(
                sys,
                "argv",
                [
                    "import_company_finished_assets.py",
                    str(self.root),
                    "--execute",
                    "--local-only",
                    "--workers",
                    "3",
                ],
            ),
        ):
            self.assertEqual(import_company_finished_assets.main(), 0)
        self.assertIs(company_execute.call_args.kwargs["enable_vlm"], False)
        self.assertEqual(company_execute.call_args.kwargs["concurrency"], 3)


if __name__ == "__main__":
    unittest.main()
