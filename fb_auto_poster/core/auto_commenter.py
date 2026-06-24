"""自動留言暖帖引擎 — 發文後自動留言提升觸及率

功能:
  - 預設 10+ 組留言模板 (隨機選用避免重複)
  - 自訂留言詞庫
  - 留言間隔隨機 (3-10 分鐘)
  - 可設定每篇貼文留言數 (預設 1 則)
"""
import asyncio
import json
import os
import random
from datetime import datetime
from typing import Optional

from utils.logger import log

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
_COMMENTS_FILE = os.path.join(_DATA_DIR, "auto_comments.json")

# ── 預設留言模板庫 ──
_DEFAULT_COMMENTS = [
    "優質物件，歡迎預約賞屋！🏠",
    "稀有釋出，動作要快喔～",
    "好房不等人，有興趣歡迎私訊 😊",
    "格局方正，通風採光一級棒！",
    "近學區、商圈，生活機能超便利 👍",
    "誠意出售，價格可談，歡迎來電",
    "滿意的房子，值得您親自來看看！",
    "這個價位真的很划算，錯過可惜～",
    "歡迎分享給有需要的朋友 🙏",
    "物件資訊歡迎私訊索取詳細資料",
    "稀有物件釋出，歡迎預約 🏠✨",
    "好物件不等人，趕快私訊約看 📩",
    "格局方正採光好，生活機能一級棒 👍",
    "近捷運/交流道，交通超方便 🚗",
    "誠意出售，歡迎出價討論！",
    "已有多組詢問，想看要快～",
    "屋主自售，省仲介費 💰",
    "附完整產權資料，交易有保障 ✅",
    "社區管理完善，居住品質高 🏙️",
    "投資自住兩相宜，穩定收租中 📈",
]


class AutoCommenter:
    """自動留言引擎"""
    
    def __init__(self):
        os.makedirs(_DATA_DIR, exist_ok=True)
        self._comments = self._load_comments()
        self._used = {}  # post_url -> [used_comment_indices]
        self._settings = {
            "enabled": True,
            "comments_per_post": 1,
            "min_delay_minutes": 3,
            "max_delay_minutes": 10,
        }
        self._load_settings()
    
    def _load_comments(self) -> list[str]:
        try:
            if os.path.exists(_COMMENTS_FILE):
                with open(_COMMENTS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data if isinstance(data, list) else list(_DEFAULT_COMMENTS)
        except Exception:
            pass
        # 首次建立
        self._save_comments(_DEFAULT_COMMENTS)
        return list(_DEFAULT_COMMENTS)
    
    def _save_comments(self, comments: list[str]):
        try:
            with open(_COMMENTS_FILE, "w", encoding="utf-8") as f:
                json.dump(comments, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
    
    def _load_settings(self):
        settings_file = os.path.join(_DATA_DIR, "auto_comment_settings.json")
        try:
            if os.path.exists(settings_file):
                with open(settings_file, "r", encoding="utf-8") as f:
                    self._settings.update(json.load(f))
        except Exception:
            pass
    
    def save_settings(self, **kwargs):
        self._settings.update(kwargs)
        settings_file = os.path.join(_DATA_DIR, "auto_comment_settings.json")
        try:
            with open(settings_file, "w", encoding="utf-8") as f:
                json.dump(self._settings, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
    
    def pick_comment(self, post_url: str) -> Optional[str]:
        """為指定貼文挑選一則留言 (避免重複)"""
        if not self._comments:
            return None
        
        used = self._used.get(post_url, [])
        available = [i for i in range(len(self._comments)) if i not in used]
        
        if not available:
            # 全部都用過了，重置並重新挑選
            self._used[post_url] = []
            available = list(range(len(self._comments)))
        
        idx = random.choice(available)
        self._used.setdefault(post_url, []).append(idx)
        return self._comments[idx]
    
    @property
    def comment_count(self) -> int:
        return len(self._comments)
    
    @property
    def is_enabled(self) -> bool:
        return self._settings.get("enabled", True)
    
    @property
    def comments_per_post(self) -> int:
        return self._settings.get("comments_per_post", 1)
    
    @property
    def delay_range(self) -> tuple:
        return (
            self._settings.get("min_delay_minutes", 3),
            self._settings.get("max_delay_minutes", 10),
        )
    
    def add_comment(self, text: str):
        """新增留言模板"""
        if text.strip() and text.strip() not in self._comments:
            self._comments.append(text.strip())
            self._save_comments(self._comments)
    
    def remove_comment(self, index: int):
        """刪除留言模板"""
        if 0 <= index < len(self._comments):
            self._comments.pop(index)
            self._save_comments(self._comments)
    
    def list_comments(self) -> list[str]:
        return list(self._comments)


async def auto_comment_on_post(
    page,
    post_url: str,
    commenter: AutoCommenter = None,
) -> dict:
    """使用 Playwright 在指定貼文留言
    
    Returns:
        {"success": bool, "comment": str, "error": str|None}
    """
    if commenter is None:
        commenter = AutoCommenter()
    
    if not commenter.is_enabled:
        return {"success": False, "comment": "", "error": "auto-comment disabled"}
    
    text = commenter.pick_comment(post_url)
    if not text:
        return {"success": False, "comment": "", "error": "no templates available"}
    
    try:
        # 導航到貼文
        await page.goto(post_url, wait_until="domcontentloaded", timeout=15000)
        await asyncio.sleep(random.uniform(2, 5))
        
        # 找留言框
        comment_selectors = [
            'div[role="textbox"][aria-label*="留言"]',
            'div[aria-label*="留言"][contenteditable="true"]',
            'div[aria-label*="Comment"][role="textbox"]',
            'form[role="presentation"] div[contenteditable="true"]',
        ]
        
        comment_box = None
        for sel in comment_selectors:
            try:
                comment_box = await page.wait_for_selector(sel, timeout=3000)
                if comment_box:
                    break
            except Exception:
                continue
        
        if not comment_box:
            return {"success": False, "comment": text, "error": "找不到留言框"}
        
        # 輸入留言
        await comment_box.click()
        await asyncio.sleep(0.5)
        await page.keyboard.type(text, delay=random.randint(50, 150))
        await asyncio.sleep(random.uniform(1, 2))
        
        # 按 Enter 送出
        await page.keyboard.press("Enter")
        await asyncio.sleep(2)
        
        log("COMMENT", post_url[:50], f"已留言: {text[:30]}...", "💬")
        return {"success": True, "comment": text, "error": None}
        
    except Exception as e:
        return {"success": False, "comment": text, "error": str(e)[:100]}
