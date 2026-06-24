"""自動加入 FB 社團模組 — 3,600+ 台灣精選社團取自 SnapPost 資料庫

功能：
- 預載 3,632 個台灣社團 (依縣市/主題分類)
- 智慧加入：每次隨機 3-5 個，間隔 60-120 秒
- 追蹤已加入/待審核/被拒絕狀態
- 支援自訂社團清單
- 格式自動偵測 (URL 字串 / {url, name, category} dict)
"""
import asyncio
import json
import os
import random
from datetime import datetime
from typing import Optional, Union

from utils.logger import log

# ── 精簡 fallback (若 available_groups.json 不存在) ──
_DEFAULT_GROUPS = [
    "https://facebook.com/groups/taoyuan.house/",
    "https://facebook.com/groups/zhongli.house/",
    "https://facebook.com/groups/台灣房屋買賣交流/",
    "https://facebook.com/groups/房屋買賣租屋/",
    "https://facebook.com/groups/Taiwan.buy.sell/",
]


def _extract_url(item) -> str:
    """從 dict 或字串中提取 URL"""
    if isinstance(item, dict):
        return item.get("url", "")
    return str(item)


def _get_data_file(filename: str) -> str:
    from utils.config import get_data_path as _gdp
    return _gdp(filename)


_data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
os.makedirs(_data_dir, exist_ok=True)


class GroupJoiner:
    """自動加入社團引擎 — 支援 3,600+ 社團"""
    
    def __init__(self):
        self.groups_file = _get_data_file("available_groups.json")
        self.status_file = _get_data_file("joined_groups.json")
        self._ensure_files()
    
    def _ensure_files(self):
        if not os.path.exists(self.groups_file):
            os.makedirs(os.path.dirname(self.groups_file), exist_ok=True)
            with open(self.groups_file, "w", encoding="utf-8") as f:
                json.dump(_DEFAULT_GROUPS, f, ensure_ascii=False, indent=2)
        if not os.path.exists(self.status_file):
            with open(self.status_file, "w", encoding="utf-8") as f:
                json.dump({}, f, ensure_ascii=False, indent=2)
    
    def get_pending_groups(self, count: int = 5) -> list[str]:
        """取得尚未加入的社團 URL 列表"""
        available = self._load_groups()
        joined = self._load_status()
        
        urls = [_extract_url(g) for g in available]
        
        pending = []
        for u in urls:
            if u not in joined or joined[u].get("status") == "failed":
                pending.append(u)
            if len(pending) >= count:
                break
        
        if len(pending) < count:
            remaining = count - len(pending)
            existing = [
                (u, joined.get(u, {}).get("joined_at", ""))
                for u in urls
                if u in joined and joined[u].get("status") == "joined"
            ]
            existing.sort(key=lambda x: x[1])
            for u, _ in existing[:remaining]:
                if u not in pending:
                    pending.append(u)
        
        return pending
    
    def mark_joined(self, group_url: str, success: bool, error: str = ""):
        status = self._load_status()
        status[group_url] = {
            "status": "joined" if success else "failed",
            "joined_at": datetime.now().isoformat(),
            "error": error,
        }
        self._save_status(status)
    
    def get_stats(self) -> dict:
        status = self._load_status()
        total = len(self._load_groups())
        joined = sum(1 for v in status.values() if v.get("status") == "joined")
        pending = sum(1 for v in status.values() if v.get("status") == "pending")
        failed = sum(1 for v in status.values() if v.get("status") == "failed")
        remaining = total - joined - pending - failed
        
        return {
            "total": total, "joined": joined,
            "pending": pending, "failed": failed, "remaining": remaining,
        }
    
    def get_categories(self) -> list[str]:
        """取得所有社團分類"""
        cats = set()
        for g in self._load_groups():
            if isinstance(g, dict):
                c = g.get("category", "")
                if c:
                    cats.add(c)
        return sorted(cats)
    
    def get_groups_by_category(self, category: str) -> list[str]:
        """依分類取得社團 URL 列表"""
        result = []
        for g in self._load_groups():
            if isinstance(g, dict):
                if g.get("category") == category:
                    result.append(g.get("url", ""))
        return result
    
    def add_custom_groups(self, urls: list) -> int:
        groups = self._load_groups()
        existing_urls = {_extract_url(g) for g in groups}
        added = 0
        for url in urls:
            url = url.strip()
            if url and url not in existing_urls:
                groups.append({"url": url, "name": url.split("/")[-1], "category": "自訂"})
                existing_urls.add(url)
                added += 1
        if added:
            self._save_groups(groups)
        return added
    
    def reset_failed(self):
        status = self._load_status()
        for g in list(status.keys()):
            if status[g].get("status") == "failed":
                del status[g]
        self._save_status(status)
    
    def _load_groups(self) -> list:
        try:
            with open(self.groups_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return list(_DEFAULT_GROUPS)
    
    def _save_groups(self, groups: list):
        with open(self.groups_file, "w", encoding="utf-8") as f:
            json.dump(groups, f, ensure_ascii=False, indent=2)
    
    def _load_status(self) -> dict:
        try:
            with open(self.status_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    
    def _save_status(self, status: dict):
        with open(self.status_file, "w", encoding="utf-8") as f:
            json.dump(status, f, ensure_ascii=False, indent=2)


async def join_groups_async(
    page,
    count: int = 3,
    joiner: GroupJoiner = None,
    on_progress=None,
) -> dict:
    if joiner is None:
        joiner = GroupJoiner()
    
    targets = joiner.get_pending_groups(count)
    results = {"joined": 0, "failed": 0, "skipped": 0}
    
    for group_url in targets:
        try:
            await page.goto(group_url, wait_until="domcontentloaded", timeout=15000)
            delay = random.uniform(3, 8)
            await asyncio.sleep(delay)
            
            join_selectors = [
                'div[aria-label="加入社團"]',
                'span:has-text("加入社團")',
                'div[role="button"]:has-text("加入")',
                'div[aria-label="Join group"]',
                'span:has-text("Join")',
            ]
            
            joined = False
            for selector in join_selectors:
                try:
                    btn = await page.wait_for_selector(selector, timeout=3000)
                    if btn:
                        await btn.click()
                        await asyncio.sleep(random.uniform(2, 5))
                        try:
                            confirm = await page.wait_for_selector(
                                'div[aria-label="回答問題"]', timeout=2000
                            )
                            if confirm:
                                await page.keyboard.press("Escape")
                                joiner.mark_joined(group_url, False, "需要回答問題")
                                results["skipped"] += 1
                                if on_progress:
                                    on_progress(group_url, "skipped", "需要回答問題")
                                break
                        except Exception:
                            pass
                        joiner.mark_joined(group_url, True)
                        results["joined"] += 1
                        joined = True
                        if on_progress:
                            on_progress(group_url, "joined", "成功")
                        break
                except Exception:
                    continue
            
            if not joined:
                joiner.mark_joined(group_url, False, "找不到加入按鈕")
                results["failed"] += 1
                if on_progress:
                    on_progress(group_url, "failed", "找不到加入按鈕")
            
            wait = random.uniform(60, 120)
            log("GROUP_JOIN", group_url, f"等待 {wait:.0f}s 後繼續...", "⏳")
            await asyncio.sleep(wait)
            
        except Exception as e:
            joiner.mark_joined(group_url, False, str(e)[:100])
            results["failed"] += 1
            if on_progress:
                on_progress(group_url, "failed", str(e)[:50])
    
    return results
