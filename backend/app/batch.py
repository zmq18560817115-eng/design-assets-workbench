"""批量上传与后台异步拆解（并发 + 感知哈希去重 + 进度持久化）。

大批量（尤其开启视觉大模型、每张较慢）时逐张同步不现实：
- 文件先落盘，起后台线程池并发拆解并入库；
- 用 dHash 感知哈希对「已入库」与「本批次内」做近重复去重，跳过重复图；
- DB 写入加锁 + SQLite WAL，避免并发锁竞争。

进度**持久化到 batch_import_jobs 表**：容器重启后仍可查询到批次，未完成的批次由
启动钩子标记为 interrupted（已完成的案例本就已入库；重传时去重会跳过它们）。
"""
from __future__ import annotations

import datetime as dt
import json
import threading
import uuid
import shutil
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from . import config, crud, imagehash, models
from .agents import run_pipeline
from .business_contract import normalize_new_source_type
from .database import SessionLocal

_db_write_lock = threading.Lock()  # 串行化 DB 写入，规避 SQLite 锁竞争


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC).replace(tzinfo=None)


def create_batch(
    items: list[dict],
    *,
    background: bool = True,
    concurrency: int | None = None,
    enable_vlm: bool = True,
) -> str:
    """落库一个批次任务，起后台线程处理，返回 batch_id 供轮询进度。"""
    normalized_items = []
    for raw in items:
        item = dict(raw)
        item["source_type"] = normalize_new_source_type(
            item.get("source_type", ""), "external_reference"
        )
        normalized_items.append(item)
    concurrency = max(1, min(concurrency or config.BATCH_CONCURRENCY, 5))
    batch_id = uuid.uuid4().hex
    db = SessionLocal()
    try:
        db.add(
            models.BatchImportJob(
                id=batch_id,
                status="processing",
                total=len(normalized_items),
                concurrency=concurrency,
                started_at=_now(),
            )
        )
        db.commit()
    finally:
        db.close()
    if background:
        threading.Thread(
            target=_run,
            args=(batch_id, normalized_items, concurrency, enable_vlm),
            daemon=True,
        ).start()
    else:
        _run(batch_id, normalized_items, concurrency, enable_vlm)
    return batch_id


def get_batch(batch_id: str) -> dict | None:
    db = SessionLocal()
    try:
        job = db.get(models.BatchImportJob, batch_id)
        if not job:
            return None
        return {
            "total": job.total,
            "done": job.done,
            "failed": job.failed,
            "skipped": job.skipped,
            "fallback": getattr(job, "fallback", 0) or 0,
            "status": job.status,
            "case_ids": json.loads(job.case_ids or "[]"),
            "errors": json.loads(job.errors or "[]"),
            "skipped_files": json.loads(job.skipped_files or "[]"),
            "concurrency": job.concurrency,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        }
    finally:
        db.close()


def recover_stale_jobs(db) -> int:
    """启动时把仍处于 processing 的批次标记为 interrupted（进程已重启、线程已丢）。"""
    stale = (
        db.query(models.BatchImportJob)
        .filter(models.BatchImportJob.status == "processing")
        .all()
    )
    for job in stale:
        job.status = "interrupted"
        job.finished_at = _now()
        errors = json.loads(job.errors or "[]")
        errors.append("服务重启导致批次中断，未完成素材请重新上传（去重会跳过已入库图）")
        job.errors = json.dumps(errors, ensure_ascii=False)
    return len(stale)


def _record(
    batch_id: str,
    *,
    done: int = 0,
    failed: int = 0,
    skipped: int = 0,
    fallback: int = 0,
    case_id: int | None = None,
    error: str | None = None,
    skipped_file: str | None = None,
) -> None:
    """在写锁内把一条进度增量落库。"""
    with _db_write_lock:
        db = SessionLocal()
        try:
            job = db.get(models.BatchImportJob, batch_id)
            if not job:
                return
            job.done += done
            job.failed += failed
            job.skipped += skipped
            job.fallback = (getattr(job, "fallback", 0) or 0) + fallback
            if case_id is not None:
                ids = json.loads(job.case_ids or "[]")
                ids.append(case_id)
                job.case_ids = json.dumps(ids)
            if error is not None:
                errors = json.loads(job.errors or "[]")
                errors.append(error)
                job.errors = json.dumps(errors, ensure_ascii=False)
            if skipped_file is not None:
                files = json.loads(job.skipped_files or "[]")
                files.append(skipped_file)
                job.skipped_files = json.dumps(files, ensure_ascii=False)
            db.commit()
        finally:
            db.close()


def _finish(batch_id: str) -> None:
    with _db_write_lock:
        db = SessionLocal()
        try:
            job = db.get(models.BatchImportJob, batch_id)
            if job and job.status == "processing":
                job.status = "completed"
                job.finished_at = _now()
                db.commit()
        finally:
            db.close()


def _run(
    batch_id: str,
    items: list[dict],
    concurrency: int | None = None,
    enable_vlm: bool = True,
) -> None:
    concurrency = max(1, min(concurrency or config.BATCH_CONCURRENCY, 5))
    # 预载已入库哈希，作为去重基线
    db = SessionLocal()
    try:
        categories = {it.get("asset_category", "layout") for it in items}
        seen_by_category: dict[str, list[str]] = {
            category: [
                h for h, _ in crud.load_image_hashes(db, asset_category=category)
            ]
            for category in categories
        }
    except Exception:
        seen_by_category = {}
    finally:
        db.close()
    seen_lock = threading.Lock()

    def worker(it: dict) -> None:
        try:
            phash = ""
            try:
                phash = imagehash.dhash(it["path"])
            except Exception:
                phash = ""
            # 去重：与已入库 + 本批次已见比对
            if phash:
                with seen_lock:
                    category = it.get("asset_category", "layout")
                    seen = seen_by_category.setdefault(category, [])
                    dup = any(imagehash.is_duplicate(phash, h) for h in seen)
                    if not dup:
                        seen.append(phash)
                if dup:
                    _record(batch_id, skipped=1, skipped_file=it["filename"])
                    return

            result = run_pipeline(
                it["path"],
                asset_category=it.get("asset_category", "layout"),
                enable_vlm=enable_vlm,
            )

            with _db_write_lock:  # DB 写入串行
                wdb = SessionLocal()
                copied_path = None
                try:
                    source_path = Path(it["path"])
                    stored_name = it.get("stored_name") or (
                        f"{uuid.uuid4().hex}{source_path.suffix.lower()}"
                    )
                    if it.get("copy_to_uploads"):
                        copied_path = config.UPLOAD_DIR / stored_name
                        shutil.copy2(source_path, copied_path)
                    image = models.Image(
                        url=it.get("url") or f"/uploads/{stored_name}",
                        filename=it["filename"],
                        source="batch",
                        source_type=it.get("source_type", "external_reference"),
                        source_url=it.get("source_url", ""),
                        rights_note=it.get("rights_note", ""),
                        visibility="team",
                        uploader=it.get("uploader", "anonymous"),
                        phash=phash,
                    )
                    wdb.add(image)
                    wdb.flush()
                    case = crud.create_case_from_analysis(
                        wdb,
                        image,
                        result,
                        product_category=it.get("product_category", ""),
                        asset_category=it.get("asset_category", "layout"),
                        asset_subcategory=it.get("asset_subcategory", ""),
                        business_metadata=it,
                    )
                    project_name = (it.get("project_name") or "").strip()
                    if project_name:
                        project = (
                            wdb.query(models.Project)
                            .filter(models.Project.name == project_name)
                            .first()
                        )
                        if not project:
                            project = models.Project(
                                name=project_name,
                                business_line=it.get("business_line", ""),
                                status="active",
                                is_gold=False,
                            )
                            wdb.add(project)
                            wdb.flush()
                        case.project_id = project.id
                    cid = case.id
                    job = wdb.get(models.BatchImportJob, batch_id)
                    if job:
                        job.done += 1
                        ids = json.loads(job.case_ids or "[]")
                        ids.append(cid)
                        job.case_ids = json.dumps(ids)
                        if result.analyzed_by in ("", "启发式规则"):
                            job.fallback = (getattr(job, "fallback", 0) or 0) + 1
                    wdb.commit()
                except Exception:
                    wdb.rollback()
                    if copied_path:
                        copied_path.unlink(missing_ok=True)
                    raise
                finally:
                    wdb.close()
        except Exception as exc:  # noqa: BLE001
            _record(batch_id, failed=1, error=f"{it['filename']}: {exc}")

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        list(pool.map(worker, items))

    _finish(batch_id)
