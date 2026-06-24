"""自動刪文定時器 — 排程定時清理過期貼文"""
import json
import os
from datetime import datetime, timedelta
from typing import Optional

from utils.logger import get_post_logs_for_clean, log


class AutoCleaner:
    """自動刪文引擎 — 由排程器驅動"""

    def __init__(self):
        self._retention_hours = 168  # 預設保留 7 天 (168 小時)

    def set_retention(self, hours: int):
        """設定保留幾小時內的貼文"""
        self._retention_hours = max(1, hours)

    def get_retention(self) -> int:
        return self._retention_hours

    def run_clean(self, account_id: str, params: dict = None) -> int:
        """執行清理任務 — 掃描並記錄過期待刪貼文

        由 APScheduler 定時呼叫（同步版本）。
        params 可包含:
            - retention_hours: 覆蓋保留時間
            - dry_run: True 只記錄不實際刪除

        Returns: 應刪除的貼文數量
        """
        retention = params.get("retention_hours", self._retention_hours) if params else self._retention_hours
        dry_run = params.get("dry_run", False) if params else False

        posts = get_post_logs_for_clean()
        now = datetime.now()
        to_delete = []

        for post in posts:
            try:
                delete_time = datetime.strptime(post["delete_at"], "%Y-%m-%d %H:%M")
                if now >= delete_time:
                    to_delete.append(post)
            except (ValueError, Exception):
                continue

        if dry_run:
            log("CLEAN", "system", f"排程清理 (預演): 發現 {len(to_delete)} 篇過期待刪", "⏳")
            return len(to_delete)

        # 實際執行刪除需要透過 BrowserManager + Deleter
        # 此處先記錄排程觸發，實際刪除由各帳號的 Deleter 完成
        for post in to_delete:
            log("CLEAN", post["account"], f"自動刪除過期貼文: {post['detail']}", "⏳ 佇列中")

        log("CLEAN", "system", f"排程清理完成: {len(to_delete)} 篇已排入刪除佇列", "✅")
        return len(to_delete)

    def estimate_next_clean(self) -> str:
        """估算下次清理可刪除的數量"""
        posts = get_post_logs_for_clean()
        now = datetime.now()
        count = 0
        for post in posts:
            try:
                delete_time = datetime.strptime(post["delete_at"], "%Y-%m-%d %H:%M")
                if now >= delete_time:
                    count += 1
            except Exception:
                continue
        return f"有 {count} 篇貼文等待清理"


def get_pending_deletes() -> list[dict]:
    """讀取待刪除貼文清單（從 pending_deletes.json）

    Returns: list of {account_id, group_url, group_name, delete_at, detail, retention_hours}
    """
    path = _get_pending_deletes_path()
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_pending_deletes(items: list[dict]):
    """儲存待刪除貼文清單"""
    path = _get_pending_deletes_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def add_pending_delete(
    account_id: str,
    delete_at: str,
    detail: str = "",
    group_url: str = "",
    retention_hours: int = 168,
):
    """新增一筆待刪除貼文記錄"""
    items = get_pending_deletes()
    items.append({
        "account_id": account_id,
        "group_url": group_url,
        "detail": detail,
        "delete_at": delete_at,
        "retention_hours": retention_hours,
    })
    save_pending_deletes(items)


def get_expired_deletes() -> list[dict]:
    """取得所有已過期的待刪除貼文"""
    items = get_pending_deletes()
    now = datetime.now()
    expired = []
    for item in items:
        try:
            delete_time = datetime.strptime(item["delete_at"], "%Y-%m-%d %H:%M")
            if now >= delete_time:
                expired.append(item)
        except (ValueError, KeyError):
            continue
    return expired


def remove_pending_deletes(indices: set[int]):
    """移除指定索引的待刪除貼文"""
    items = get_pending_deletes()
    remaining = [item for i, item in enumerate(items) if i not in indices]
    save_pending_deletes(remaining)


def _get_pending_deletes_path() -> str:
    from utils.config import get_data_path
    return get_data_path("pending_deletes.json")
