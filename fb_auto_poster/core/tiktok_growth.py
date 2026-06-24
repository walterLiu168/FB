"""TikTok Growth Engine — 自動互動 + 帳號增長

Playwright-based (非 Selenium)。整合現有 tiktok_uploader 的持久化 profile。

功能：
  - 自動留言：在指定創作者最新影片留言 (跳過置頂)
  - 自動追蹤：追蹤同行/潛在客戶
  - 自動按讚：幫指定創作者的影片按讚
  - 留言詞庫：隨機選用，避免重複模式
  - 排程互動：每 N 分鐘自動執行一次 (模擬真人)
  - 增長報表：追蹤粉絲數 + 互動數變化
"""
import asyncio
import json
import os
import random
import re
from datetime import datetime, timedelta
from typing import Optional

from utils.logger import log
from utils.config import get_data_path

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
_GROWTH_FILE = os.path.join(_DATA_DIR, "tiktok_growth.json")

# ── 預設留言庫 ──
_DEFAULT_COMMENTS = [
    "感謝分享，很實用的資訊！",
    "這個物件真的很棒 👍",
    "專業！學到了",
    "收藏了，謝謝",
    "好的內容，支持 💪",
    "獲益良多，期待更多分享",
    "台灣的房仲就是要這樣專業",
    "實用文，已分享給朋友",
    "市場分析很到位 👏",
    "簡單明瞭，讚",
    "好物件就是要推 🔥",
    "專業仲介，值得信賴",
    "這個價格很可以！",
    "格局真不錯，採光好",
    "地段好，生活機能也棒",
]


def _load_growth() -> dict:
    try:
        if os.path.exists(_GROWTH_FILE):
            with open(_GROWTH_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {"followed": [], "commented_on": [], "daily_stats": {}}


def _save_growth(data: dict):
    os.makedirs(_DATA_DIR, exist_ok=True)
    with open(_GROWTH_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


async def engage_with_video(page, video_url: str, action: str = "comment",
                             text: str = None, comments: list[str] = None):
    """在指定 TikTok 影片上進行互動

    Args:
        page: Playwright Page (已登入)
        video_url: 影片 URL
        action: "comment" | "like" | "both"
        text: 指定留言文字 (None = 隨機)
        comments: 留言詞庫

    Returns:
        {"success": bool, "action": str, "text": str}
    """
    pool = comments or _DEFAULT_COMMENTS

    try:
        await page.goto(video_url, wait_until="domcontentloaded", timeout=15000)
        await asyncio.sleep(random.uniform(3, 6))

        result = {"success": True, "action": action, "text": ""}

        # 按讚
        if action in ("like", "both"):
            like_selectors = [
                'span[data-e2e="like-icon"]',
                'button[aria-label*="讚"]',
                'button[aria-label*="Like"]',
                'span[data-e2e="browse-like-icon"]',
            ]
            for sel in like_selectors:
                try:
                    btn = await page.wait_for_selector(sel, timeout=3000)
                    if btn:
                        await btn.click()
                        await asyncio.sleep(random.uniform(1, 2))
                        log("TIKTOK", "like", "已按讚", "❤️")
                        break
                except Exception:
                    continue

        # 留言
        if action in ("comment", "both"):
            chosen = text or random.choice(pool)
            result["text"] = chosen

            # 找留言框
            comment_selectors = [
                'div[contenteditable="true"][data-e2e="comment-input"]',
                'div[data-e2e="comment-input"] div[contenteditable="true"]',
                'textarea[placeholder*="留言"]',
                'div[role="textbox"]',
            ]
            box = None
            for sel in comment_selectors:
                try:
                    box = await page.wait_for_selector(sel, timeout=5000)
                    if box:
                        break
                except Exception:
                    continue

            if not box:
                # 嘗試點留言按鈕展開
                try:
                    expand_sel = 'span[data-e2e="comment-icon"], button:has-text("留言")'
                    expand_btn = await page.wait_for_selector(expand_sel, timeout=3000)
                    if expand_btn:
                        await expand_btn.click()
                        await asyncio.sleep(2)
                        box = await page.wait_for_selector(
                            'div[contenteditable="true"]', timeout=5000
                        )
                except Exception:
                    pass

            if box:
                await box.click()
                await asyncio.sleep(0.5)
                await page.keyboard.type(chosen, delay=random.randint(60, 150))
                await asyncio.sleep(random.uniform(1, 2))
                await page.keyboard.press("Enter")
                await asyncio.sleep(2)
                log("TIKTOK", "comment", f"已留言: {chosen[:30]}", "💬")
                result["text"] = chosen
            else:
                result["success"] = False
                log("TIKTOK", "comment", "找不到留言框", "❌")

        # 記錄
        data = _load_growth()
        key = video_url[:60]
        data["commented_on"].append({
            "url": video_url, "action": action,
            "text": result["text"], "time": datetime.now().isoformat()
        })
        if len(data["commented_on"]) > 500:
            data["commented_on"] = data["commented_on"][-500:]
        _save_growth(data)

        return result

    except Exception as e:
        return {"success": False, "action": action, "text": "", "error": str(e)[:100]}


async def follow_user(page, username: str):
    """追蹤 TikTok 用戶
    
    Args:
        page: Playwright Page (已登入)
        username: TikTok 用戶名 (不含 @)
    
    Returns:
        {"success": bool, "username": str}
    """
    try:
        await page.goto(f"https://www.tiktok.com/@{username}", wait_until="domcontentloaded", timeout=15000)
        await asyncio.sleep(random.uniform(3, 5))

        follow_selectors = [
            'button[data-e2e="follow-button"]',
            'button:has-text("追蹤")',
            'button:has-text("Follow")',
        ]
        for sel in follow_selectors:
            try:
                btn = await page.wait_for_selector(sel, timeout=5000)
                btn_text = await btn.inner_text()
                if "追蹤中" in btn_text or "Following" in btn_text:
                    log("TIKTOK", username, "已追蹤過，跳過")
                    return {"success": True, "username": username, "already_following": True}
                await btn.click()
                await asyncio.sleep(random.uniform(2, 4))
                log("TIKTOK", username, "已追蹤", "👤")
                break
            except Exception:
                continue

        data = _load_growth()
        data["followed"].append({
            "username": username, "time": datetime.now().isoformat()
        })
        _save_growth(data)

        return {"success": True, "username": username}

    except Exception as e:
        return {"success": False, "username": username, "error": str(e)[:100]}


async def comment_on_latest(page, username: str, count: int = 1,
                            comments: list[str] = None):
    """在指定用戶的最新影片留言 (自動跳過置頂影片)

    參考 TikTok-Bot-Automation 的置頂影片處理邏輯：
    - 先計算有多少置頂影片 (pinned badge)
    - 點第一支影片
    - 按右箭頭跳過置頂
    - 開始留言
    """
    pool = comments or _DEFAULT_COMMENTS

    try:
        await page.goto(f"https://www.tiktok.com/@{username}", wait_until="domcontentloaded", timeout=15000)
        await asyncio.sleep(random.uniform(3, 5))

        # 計算置頂數量
        pinned = await page.query_selector_all('div[data-e2e="video-card-badge"]')
        pinned_count = len(pinned)

        # 點第一支影片
        first_video = await page.wait_for_selector('div[data-e2e="user-post-item"]', timeout=10000)
        if first_video:
            await first_video.click()
            await asyncio.sleep(3)

        # 跳過置頂
        for _ in range(pinned_count):
            try:
                right = await page.wait_for_selector('button[data-e2e="arrow-right"]', timeout=3000)
                if right:
                    await right.click()
                    await asyncio.sleep(1)
            except Exception:
                break

        # 留言
        results = []
        for i in range(count):
            chosen = random.choice(pool)
            try:
                box = await page.wait_for_selector('div[contenteditable="true"]', timeout=5000)
                if box:
                    await box.click()
                    await asyncio.sleep(0.3)
                    await page.keyboard.type(chosen, delay=random.randint(60, 130))
                    await asyncio.sleep(1)
                    await page.keyboard.press("Enter")
                    await asyncio.sleep(2)
                    log("TIKTOK", f"{username}#{i+1}", f"留言: {chosen[:25]}", "💬")
                    results.append({"success": True, "text": chosen})
                else:
                    results.append({"success": False, "text": chosen, "error": "no input"})
            except Exception as e:
                results.append({"success": False, "text": chosen, "error": str(e)[:60]})

            if i < count - 1:
                await asyncio.sleep(random.uniform(2, 4))
                # 下一支影片
                try:
                    right = await page.wait_for_selector('button[data-e2e="arrow-right"]', timeout=3000)
                    if right:
                        await right.click()
                        await asyncio.sleep(2)
                except Exception:
                    break

        return {"success": all(r["success"] for r in results), "results": results}

    except Exception as e:
        return {"success": False, "error": str(e)[:100]}


def get_growth_stats() -> dict:
    """取得增長統計"""
    data = _load_growth()
    today = datetime.now().strftime("%Y-%m-%d")

    followed_today = sum(
        1 for f in data.get("followed", [])
        if f.get("time", "").startswith(today)
    )
    commented_today = sum(
        1 for c in data.get("commented_on", [])
        if c.get("time", "").startswith(today)
    )

    return {
        "total_followed": len(data.get("followed", [])),
        "total_commented": len(data.get("commented_on", [])),
        "followed_today": followed_today,
        "commented_today": commented_today,
    }
