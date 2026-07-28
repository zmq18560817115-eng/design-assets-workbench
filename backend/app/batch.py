"""批量上传与后台异步拆解（并发 + 感知哈希去重）。

大批量（尤其开启视觉大模型、每张较慢）时逐张同步不现实：
- 文件先落盘，起后台线程池并发拆解并入库；
- 用 dHash 感知哈希对「已入库」与「本批次内」做近重复去重，跳过重复图；
- DB 写入加锁 + SQLite WAL，避免并发锁竞争。

进度存于内存（容器重启会丢进度，但已完成的案例已持久化）。
"""
from __future__ import annotations

import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

from . import config, crud, imagehash, models
from .agents import run_pipeline
from .database import SessionLocal

_batches: dict[str, dict] = {}
_state_lock = threading.Lock()   # 保护进度字典与已见哈希集合
_db_write_lock = threading.Lock()  # 串行化 DB 写入，避免 SQLite 锁竞争


def create_batch(items: list[dict]) -> str:
    """items: [{path, url, filename, uploader}]，返回 batch_id 并启动后台处理。"""
    batch_id = uuid.uuid4().hex
    with _state_lock:
        _batches[batch_id] = {
            "total": len(items),
            "done": 0,
            "failed": 0,
            "skipped": 0,
            "status": "processing",
            "case_ids": [],
            "errors": [],
            "skipped_files": [],
            "concurrency": config.BATCH_CONCURRENCY,
            "started_at": time.time(),
        }
    threading.Thread(target=_run, args=(batch_id, items), daemon=True).start()
    return batch_id


def get_batch(batch_id: str) -> dict | None:
    with _state_lock:
        b = _batches.get(batch_id)
        return dict(b) if b else None


def _run(batch_id: str, items: list[dict]) -> None:
    # 预载已入库哈希，作为去重基线
    db = SessionLocal()
    try:
        categories = {it.get("asset_category", "layout") for it in items}
        seen_by_category: dict[str, list[str]] = {
            category: [
                h
                for h, _ in crud.load_image_hashes(
                    db, asset_category=category
                )
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
                    with _state_lock:
                        _batches[batch_id]["skipped"] += 1
                        _batches[batch_id]["skipped_files"].append(it["filename"])
                    return

            result = run_pipeline(
                it["path"], asset_category=it.get("asset_category", "layout")
            )

            with _db_write_lock:  # DB 写入串行
                wdb = SessionLocal()
                try:
                    image = models.Image(
                        url=it["url"],
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
                    )
                    cid = case.id
                finally:
                    wdb.close()
            with _state_lock:
                _batches[batch_id]["done"] += 1
                _batches[batch_id]["case_ids"].append(cid)
        except Exception as exc:  # noqa: BLE001
            with _state_lock:
                _batches[batch_id]["failed"] += 1
                _batches[batch_id]["errors"].append(f"{it['filename']}: {exc}")

    with ThreadPoolExecutor(max_workers=config.BATCH_CONCURRENCY) as pool:
        list(pool.map(worker, items))

    with _state_lock:
        _batches[batch_id]["status"] = "completed"
        _batches[batch_id]["finished_at"] = time.time()
