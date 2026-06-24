"""批量發文操作模組 — 多物件一次發送到多社團

功能:
  - 從 listings.json 載入待發物件
  - 選取多個物件 + 多個社團 → 批次排程發文
  - 支援漸進式發送 (每篇間隔隨機延遲)
  - 進度追蹤 + 失敗重試
"""
import asyncio
import json
import os
import random
from datetime import datetime, timedelta
from typing import Callable, Optional

from utils.logger import log
from utils.config import get_data_path

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")


class BulkPostQueue:
    """批量發文佇列"""
    
    def __init__(self):
        self._queue_file = os.path.join(_DATA_DIR, "bulk_queue.json")
        self._items: list[dict] = []
        self._load()
    
    def _load(self):
        try:
            if os.path.exists(self._queue_file):
                with open(self._queue_file, "r", encoding="utf-8") as f:
                    self._items = json.load(f)
        except Exception:
            self._items = []
    
    def _save(self):
        os.makedirs(_DATA_DIR, exist_ok=True)
        with open(self._queue_file, "w", encoding="utf-8") as f:
            json.dump(self._items, f, ensure_ascii=False, indent=2)
    
    def add(self, template_data: dict, groups: list[str], account_id: str = ""):
        """加入一條發文任務
        
        Args:
            template_data: 模板填值後的物件資料
            groups: 目標社團 URL 列表
            account_id: 發文帳號
        """
        self._items.append({
            "id": f"bulk_{len(self._items)}_{int(datetime.now().timestamp())}",
            "data": template_data,
            "groups": groups,
            "account_id": account_id,
            "status": "pending",
            "created_at": datetime.now().isoformat(),
            "error": None,
            "posted_at": None,
        })
        self._save()
    
    def add_batch(self, listings: list[dict], groups: list[str], account_id: str = ""):
        """批量加入多個物件"""
        for item in listings:
            self.add(item.get("data", item), groups, account_id)
    
    def get_pending(self, limit: int = 10) -> list[dict]:
        return [i for i in self._items if i.get("status") == "pending"][:limit]
    
    def mark_done(self, item_id: str):
        for i in self._items:
            if i["id"] == item_id:
                i["status"] = "done"
                i["posted_at"] = datetime.now().isoformat()
                break
        self._save()
    
    def mark_failed(self, item_id: str, error: str):
        for i in self._items:
            if i["id"] == item_id:
                i["status"] = "failed"
                i["error"] = error
                break
        self._save()
    
    def clear_completed(self):
        self._items = [i for i in self._items if i["status"] == "pending"]
        self._save()
    
    def get_stats(self) -> dict:
        pending = sum(1 for i in self._items if i["status"] == "pending")
        done = sum(1 for i in self._items if i["status"] == "done")
        failed = sum(1 for i in self._items if i["status"] == "failed")
        return {"pending": pending, "done": done, "failed": failed, "total": len(self._items)}
    
    def remove(self, item_id: str):
        self._items = [i for i in self._items if i["id"] != item_id]
        self._save()
    
    def list_all(self) -> list[dict]:
        return list(self._items)


class BulkOperator:
    """批量發文執行器"""
    
    def __init__(self, queue: BulkPostQueue = None):
        self.queue = queue or BulkPostQueue()
        self._running = False
        self._pause = False
        self._on_progress: Optional[Callable] = None
    
    def set_progress_callback(self, cb: Callable):
        self._on_progress = cb
    
    def pause(self):
        self._pause = True
    
    def resume(self):
        self._pause = False
    
    def stop(self):
        self._running = False
    
    async def run(
        self,
        post_func: Callable,  # async def post_func(page, data, group) -> bool
        page,
        batch_size: int = 5,
        min_delay_sec: int = 120,
        max_delay_sec: int = 600,
    ) -> dict:
        """執行批量發文
        
        Args:
            post_func: 發文函式 (page, data, group_url) -> success:bool
            page: Playwright Page
            batch_size: 每批處理幾篇
            min_delay_sec / max_delay_sec: 每篇間隔秒數
        """
        self._running = True
        results = {"total": 0, "done": 0, "failed": 0}
        
        items = self.queue.get_pending(batch_size)
        results["total"] = len(items)
        
        for i, item in enumerate(items):
            if not self._running:
                break
            
            while self._pause and self._running:
                await asyncio.sleep(1)
            
            if self._on_progress:
                self._on_progress(i + 1, len(items), item.get("id", ""))
            
            data = item.get("data", {})
            groups = item.get("groups", [])
            
            all_ok = True
            for group_url in groups:
                try:
                    ok = await post_func(page, data, group_url)
                    if not ok:
                        all_ok = False
                        break
                except Exception as e:
                    all_ok = False
                    log("BULK", item["id"], str(e)[:80], "❌")
                    break
            
            if all_ok:
                self.queue.mark_done(item["id"])
                results["done"] += 1
                log("BULK", item["id"], f"完成 ({i+1}/{len(items)})", "✅")
            else:
                self.queue.mark_failed(item["id"], "發送失敗")
                results["failed"] += 1
            
            # 間隔延遲
            if i < len(items) - 1:
                delay = random.randint(min_delay_sec, max_delay_sec)
                log("BULK", item["id"], f"等待 {delay}s 後繼續...", "⏳")
                await asyncio.sleep(delay)
        
        self._running = False
        return results
