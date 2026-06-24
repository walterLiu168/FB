"""刪除配額管理 — 控制每日最多刪除數量

使用情境：
- 排程可能每 10 分鐘檢查一次，但使用者只希望「每天最多刪 N 篇」
- 我們用「已提交刪除任務數」作為保守計數，避免爆量
"""

from __future__ import annotations

import os
from datetime import datetime

from utils.config import load_json, save_json, get_data_path

_FILE = "delete_quota.json"


def _today_key() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _load() -> dict:
    return load_json(_FILE, {})


def _save(data: dict) -> None:
    # 確保 data 目錄存在
    os.makedirs(os.path.dirname(get_data_path(_FILE)), exist_ok=True)
    save_json(_FILE, data)


def get_used(tag: str = "default") -> int:
    """取得今天已使用的刪除數（以『已提交』計算）"""
    data = _load()
    today = _today_key()
    rec = (data.get(today) or {}).get(tag) or {}
    try:
        return int(rec.get("used", 0) or 0)
    except Exception:
        return 0


def reserve(n: int, daily_limit: int, tag: str = "default") -> int:
    """保留刪除配額，回傳實際允許的數量

    Args:
        n: 想刪的數量
        daily_limit: 每日上限
        tag: 不同任務共用同一天可用不同 tag（例如 interval / weekly）
    """
    n = max(0, int(n or 0))
    daily_limit = max(0, int(daily_limit or 0))
    if daily_limit <= 0 or n <= 0:
        return 0

    data = _load()
    today = _today_key()
    day = data.get(today) or {}
    rec = day.get(tag) or {"used": 0}
    used = int(rec.get("used", 0) or 0)

    remaining = max(0, daily_limit - used)
    allowed = min(n, remaining)
    if allowed <= 0:
        return 0

    rec["used"] = used + allowed
    day[tag] = rec
    data[today] = day
    _save(data)
    return allowed

