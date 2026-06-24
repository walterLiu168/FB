"""足跡清理排程器 — 每小時自動清除追蹤資料 + 輪換指紋

FB 追蹤你的方式（及我們的反制）:
─────────────────────────────────────────────
1. Tracking cookies (_fbp, _fbc, fr)  →  只保留登入 cookies，其他全部定時清除
2. localStorage ID (__dyn, __csr)     →  每小時 clear()
3. Cache / ETag 追蹤                   →  清除 Cache API
4. IndexedDB (fbtrace, fbss)           →  刪除所有 IndexedDB
5. Service Worker                      →  取消註冊所有 SW
6. 指紋一致性（同一組 UA+viewport）     →  輪換時換新的 UA/viewport
7. 行為時間模式（每天固定時間發文）     →  排程加入 ±15 分鐘隨機偏移
8. IP 地址（不在此層級處理）            →  使用者自行搭配 VPN/Proxy
─────────────────────────────────────────────
"""
import asyncio
import random
from typing import Optional

from utils.logger import log

# ── 全域 BrowserManager 參照 ──
# BrowserManager 在 start() 時自動註冊自己到這裡
_BROWSER_MANAGER = None


def register_browser_manager(bm):
    """BrowserManager 啟動時呼叫，註冊到全域參照"""
    global _BROWSER_MANAGER
    _BROWSER_MANAGER = bm


class FootprintCleaner:
    """每小時足跡清理器 — 由排程器驅動"""

    def __init__(self):
        self._interval_minutes = 60
        self._random_jitter = 15     # ±15 分鐘隨機偏移

    def set_browser_manager(self, bm):
        """設定 BrowserManager 實例"""
        self._browser_manager = bm

    async def clean_all_accounts(self, account_ids: list[str] = None) -> dict:
        """對所有活躍帳號執行足跡清理

        Returns: {"cleaned": int, "accounts": [str], "errors": [str]}
        """
        bm = getattr(self, '_browser_manager', None) or _BROWSER_MANAGER
        if not bm:
            log("CLEAN", "system", "Footprint clean skipped: BrowserManager not available", "⚠️")
            return {"cleaned": 0, "accounts": [], "errors": ["BrowserManager not set"]}

        cleaned = 0
        results = []

        for account_id in list(bm._contexts.keys()):
            if account_ids and account_id not in account_ids:
                continue

            try:
                result = await bm.rotate_footprint(account_id)
                cleaned += 1
                results.append(f"{account_id[:8]}...: cleared {result.get('cleared_cookies', 0)} cookies")
                log("CLEAN", account_id,
                    f"Footprint rotated: {result.get('cleared_cookies', 0)} tracking cookies cleared",
                    "✅")
            except Exception as e:
                results.append(f"{account_id[:8]}...: ERROR - {e}")
                log("CLEAN", account_id, f"Footprint rotation failed: {e}", "❌")

        return {
            "cleaned": cleaned,
            "accounts": results,
            "errors": [],
        }

    def schedule_job_params(self) -> dict:
        """回傳給 APScheduler 的排程參數

        每小時的第 random.randint(0, 59) 分執行，
        使各台電腦的清理時間不同，不會形成固定模式。
        """
        return {
            "type": "footprint_clean",
            "cron": f"{random.randint(0, 59)} * * * *",
            "description": "每小時自動清除追蹤足跡",
        }
