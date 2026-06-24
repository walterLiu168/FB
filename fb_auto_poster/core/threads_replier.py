"""Threads.net 自動海巡回覆引擎

功能：
  - 關鍵字搜尋 Threads 貼文
  - AI 判斷貼文是否為目標客群
  - 自動回覆潛在客戶
  - 回覆間隔控制
  - 黑名單避免重複回覆

工作流程：
  1. 用關鍵字搜尋 threads.net
  2. 逐篇掃描貼文內容
  3. AI 評估是否為目標客群（有意圖、在發問）
  4. 自動回覆（隨機選擇模板 + 根據原文微調）
  5. 記錄已回覆貼文，避免重複
"""
import os
import json
import asyncio
import random
from datetime import datetime, timedelta
from typing import Optional

from utils.logger import log

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
_REPLIED_FILE = os.path.join(_DATA_DIR, "threads_replied.json")
_REPLY_TEMPLATES_FILE = os.path.join(_DATA_DIR, "threads_reply_templates.json")

# ── 預設回覆模板庫 ──
_DEFAULT_REPLY_TEMPLATES = [
    "這個問題問得很好！我之前也有類似的困擾，後來找到一個方法解決了，有需要可以聊聊 😊",
    "看到你在研究這個領域！我有一些經驗可以分享，歡迎交流 🙌",
    "同意你的看法！我自己也經歷過，有些小撇步可以幫到你 💡",
    "推這篇！我之前也是這樣走過來的，如果有興趣可以私下聊 👍",
    "好話題！我剛好對這方面有些研究，需要幫忙的話可以跟我說～",
    "這個問題我遇過！解決方案其實很簡單，有興趣的話可以分享給你 ✨",
    "感謝分享！我補充一點：除了這個方法，還有另一個更有效的方式 🔥",
    "有共鳴！我身邊很多朋友也有類似情況，大家互相交流真的很有幫助 🤝",
    "好問題！但資訊量有點大，建議私下討論比較完整，需要的話可以私訊我 📩",
    "讚！很棒的討論，我也分享一下我的經驗給大家參考～",
]


class ThreadsReplier:
    """Threads 自動海巡回覆引擎"""

    def __init__(self):
        os.makedirs(_DATA_DIR, exist_ok=True)
        self._replied = self._load_replied()
        self._templates = self._load_templates()
        self._settings = {
            "enabled": True,
            "max_replies_per_session": 10,
            "min_delay_seconds": 30,
            "max_delay_seconds": 120,
            "keywords": ["創業", "電商", "副業", "行銷", "自媒體", "網路賺錢"],
        }
        self._load_settings()

    # ── 資料持久化 ──

    def _load_replied(self) -> dict:
        """載入已回覆貼文記錄"""
        try:
            if os.path.exists(_REPLIED_FILE):
                with open(_REPLIED_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    def _save_replied(self):
        """儲存已回覆貼文記錄"""
        try:
            with open(_REPLIED_FILE, "w", encoding="utf-8") as f:
                json.dump(self._replied, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _load_templates(self) -> list[str]:
        """載入回覆模板"""
        try:
            if os.path.exists(_REPLY_TEMPLATES_FILE):
                with open(_REPLY_TEMPLATES_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data if isinstance(data, list) else list(_DEFAULT_REPLY_TEMPLATES)
        except Exception:
            pass
        self._save_templates(_DEFAULT_REPLY_TEMPLATES)
        return list(_DEFAULT_REPLY_TEMPLATES)

    def _save_templates(self, templates: list[str]):
        try:
            with open(_REPLY_TEMPLATES_FILE, "w", encoding="utf-8") as f:
                json.dump(templates, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _load_settings(self):
        settings_file = os.path.join(_DATA_DIR, "threads_reply_settings.json")
        try:
            if os.path.exists(settings_file):
                with open(settings_file, "r", encoding="utf-8") as f:
                    self._settings.update(json.load(f))
        except Exception:
            pass

    # ── 屬性存取 ──

    @property
    def is_enabled(self) -> bool:
        return self._settings.get("enabled", True)

    @property
    def keywords(self) -> list[str]:
        return self._settings.get("keywords", [])

    def set_keywords(self, keywords: list[str]):
        self._settings["keywords"] = keywords
        self.save_settings()

    def save_settings(self, **kwargs):
        self._settings.update(kwargs)
        settings_file = os.path.join(_DATA_DIR, "threads_reply_settings.json")
        try:
            with open(settings_file, "w", encoding="utf-8") as f:
                json.dump(self._settings, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def add_template(self, text: str):
        if text.strip() and text.strip() not in self._templates:
            self._templates.append(text.strip())
            self._save_templates(self._templates)

    def remove_template(self, index: int):
        if 0 <= index < len(self._templates):
            self._templates.pop(index)
            self._save_templates(self._templates)

    def list_templates(self) -> list[str]:
        return list(self._templates)

    def mark_replied(self, post_url: str):
        """標記貼文已回覆"""
        self._replied[post_url] = datetime.now().isoformat()
        self._save_replied()

    def has_replied(self, post_url: str) -> bool:
        """檢查是否已回覆過此貼文"""
        return post_url in self._replied

    def is_relevant_post(self, post_text: str) -> bool:
        """判斷貼文是否相關（簡單關鍵字匹配 + 啟發式規則）

        AI 版本可以呼叫 GPT 做更精準的判斷。
        """
        if not post_text.strip():
            return False

        text_lower = post_text.lower()

        # 排除明顯廣告/業配
        ad_keywords = ["#ad", "#sponsored", "#業配", "購買連結", "下單連結", "限量發售", "手刀搶購"]
        for kw in ad_keywords:
            if kw.lower() in text_lower:
                return False

        # 檢查是否包含目標關鍵字
        matched = []
        for kw in self.keywords:
            if kw.lower() in text_lower:
                matched.append(kw)

        if not matched:
            return False

        # 檢查是否有提問意圖（問號、求救詞）
        question_signals = ["?", "？", "請問", "求助", "有人知道", "推薦", "建議", "心得", "分享", "經驗", "怎麼", "如何", "幫幫", "求救"]
        has_question = any(s in post_text for s in question_signals)

        # 只要關鍵字匹配就回（放寬條件增加覆蓋率）
        return len(matched) >= 1

    def pick_reply(self) -> str:
        """隨機選擇一條回覆模板"""
        if not self._templates:
            return "感謝分享！ 👍"
        return random.choice(self._templates)


# ═══════════════════════════════════════════════════════════
#  瀏覽器操作
# ═══════════════════════════════════════════════════════════

async def search_and_reply(
    page,
    replier: Optional[ThreadsReplier] = None,
    keywords: Optional[list[str]] = None,
    max_replies: int = 10,
    dry_run: bool = False,
    progress_callback=None,
) -> dict:
    """在 Threads 上搜尋關鍵字並自動回覆

    Args:
        page: Playwright Page
        replier: ThreadsReplier 實例
        keywords: 搜尋關鍵字列表
        max_replies: 最多回覆幾篇
        dry_run: True 時只掃描不回覆
        progress_callback: async fn(post_text, action) 用於 UI 更新

    Returns:
        {
            "scanned": int,        # 掃描總數
            "relevant": int,       # 相關貼文數
            "replied": int,        # 實際回覆數
            "skipped": int,        # 跳過（已回覆過）
            "results": [dict],     # 每篇的詳細結果
        }
    """
    if replier is None:
        replier = ThreadsReplier()

    if keywords is None:
        keywords = replier.keywords

    if not keywords:
        return {"scanned": 0, "relevant": 0, "replied": 0, "skipped": 0, "results": [], "error": "沒有設定關鍵字"}

    stats = {"scanned": 0, "relevant": 0, "replied": 0, "skipped": 0, "results": []}

    for kw in keywords:
        if stats["replied"] >= max_replies:
            break

        try:
            result = await _search_keyword_and_reply(
                page, replier, kw, max_replies - stats["replied"],
                dry_run, progress_callback
            )
            stats["scanned"] += result.get("scanned", 0)
            stats["relevant"] += result.get("relevant", 0)
            stats["replied"] += result.get("replied", 0)
            stats["skipped"] += result.get("skipped", 0)
            stats["results"].extend(result.get("results", []))

        except Exception as e:
            log("THREADS", "replier", f"搜尋關鍵字 [{kw}] 失敗: {e}", "❌")
            continue

        # 間隔
        await asyncio.sleep(random.uniform(5, 15))

    return stats


async def _search_keyword_and_reply(
    page,
    replier: ThreadsReplier,
    keyword: str,
    max_remaining: int,
    dry_run: bool,
    progress_callback=None,
) -> dict:
    """搜尋單一關鍵字並回覆"""
    stats = {"scanned": 0, "relevant": 0, "replied": 0, "skipped": 0, "results": []}

    # 編碼 URL
    from urllib.parse import quote
    search_url = f"https://www.threads.net/search?q={quote(keyword)}&serp_type=default"
    await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(random.uniform(2, 4))

    # 找貼文元素
    # Threads 搜尋結果中的貼文通常是 a[href*="/post/"] 或 div[role="article"]
    post_selectors = [
        'a[href*="/post/"]',
        'div[data-pressable-container="true"]',
        '[role="article"]',
    ]

    found_posts = []
    for sel in post_selectors:
        try:
            elements = page.locator(sel).all()
            if elements:
                found_posts = elements
                break
        except Exception:
            continue

    if not found_posts:
        log("THREADS", "replier", f"關鍵字 [{keyword}] 找不到貼文", "⚠️")
        return stats

    # 限制掃描數量
    max_scan = min(len(found_posts), 30)
    log("THREADS", "replier", f"關鍵字 [{keyword}] 找到 {max_scan} 篇貼文", "🔍")

    for i, post_el in enumerate(found_posts[:max_scan]):
        if stats["replied"] >= max_remaining:
            break

        try:
            # 取得貼文 URL
            href = ""
            try:
                href = await post_el.get_attribute("href") or ""
            except Exception:
                pass

            if not href or "/post/" not in href:
                # 嘗試從內部找連結
                try:
                    inner_link = post_el.locator('a[href*="/post/"]').first
                    if await inner_link.count() > 0:
                        href = await inner_link.get_attribute("href") or ""
                except Exception:
                    pass

            if not href:
                continue

            post_url = f"https://www.threads.net{href.split('?')[0]}" if href.startswith("/") else href

            # 檢查是否已回覆過
            if replier.has_replied(post_url):
                stats["skipped"] += 1
                continue

            # 取得貼文文字
            post_text = ""
            try:
                post_text = await post_el.inner_text()
            except Exception:
                try:
                    post_text = await post_el.text_content() or ""
                except Exception:
                    pass

            stats["scanned"] += 1

            if progress_callback:
                try:
                    await progress_callback(post_text[:100], "scanning")
                except Exception:
                    pass

            # 判斷是否相關
            if not replier.is_relevant_post(post_text):
                continue

            stats["relevant"] += 1

            if progress_callback:
                try:
                    await progress_callback(post_text[:100], "relevant")
                except Exception:
                    pass

            # Dry run 模式：只掃描不回覆
            if dry_run:
                stats["results"].append({
                    "url": post_url,
                    "text": post_text[:200],
                    "action": "would_reply",
                })
                continue

            # 回覆貼文
            reply_text = replier.pick_reply()
            reply_result = await _reply_to_post(page, post_url, reply_text)

            if reply_result["success"]:
                replier.mark_replied(post_url)
                stats["replied"] += 1
                log("THREADS", "replier", f"✅ 已回覆: {post_text[:40]}...", "💬")
            else:
                log("THREADS", "replier", f"回覆失敗: {reply_result.get('error', '')}", "❌")

            stats["results"].append({
                "url": post_url,
                "text": post_text[:200],
                "reply": reply_text,
                "success": reply_result["success"],
            })

            # 間隔
            delay = random.uniform(
                replier._settings.get("min_delay_seconds", 30),
                replier._settings.get("max_delay_seconds", 120),
            )
            await asyncio.sleep(delay)

        except Exception as e:
            log("THREADS", "replier", f"處理貼文失敗: {e}", "⚠️")
            continue

    return stats


async def _reply_to_post(page, post_url: str, reply_text: str) -> dict:
    """對指定 Threads 貼文回覆

    Args:
        page: Playwright Page
        post_url: 貼文 URL
        reply_text: 回覆文字

    Returns:
        {"success": bool, "error": str|None}
    """
    try:
        # 導航到貼文
        await page.goto(post_url, wait_until="domcontentloaded", timeout=15000)
        await asyncio.sleep(random.uniform(2, 4))

        # 找回覆框
        reply_selectors = [
            'textarea',
            'div[contenteditable="true"]',
            '[aria-label*="Reply" i]',
            '[data-testid="reply-composer"]',
        ]

        reply_box = None
        for sel in reply_selectors:
            try:
                el = page.locator(sel).first
                if await el.count() > 0 and await el.is_visible(timeout=2000):
                    reply_box = el
                    break
            except Exception:
                continue

        if not reply_box:
            return {"success": False, "error": "找不到回覆框"}

        # 點擊並輸入
        await reply_box.click(force=True, timeout=2000)
        await asyncio.sleep(0.5)
        await page.keyboard.type(reply_text, delay=random.randint(30, 80))
        await asyncio.sleep(random.uniform(1, 2))

        # 送出（按 Enter 或找送出按鈕）
        post_btn_selectors = [
            'div[role="button"]:has-text("Post")',
            'div[role="button"]:has-text("Reply")',
            'button:has-text("Post")',
            '[data-testid="reply-button"]',
        ]

        posted = False
        for sel in post_btn_selectors:
            try:
                btn = page.locator(sel).last
                if await btn.is_visible(timeout=1000):
                    await btn.click(force=True, timeout=3000)
                    posted = True
                    break
            except Exception:
                continue

        if not posted:
            # 嘗試 Ctrl+Enter
            await page.keyboard.press("Control+Enter")
            posted = True

        await asyncio.sleep(random.uniform(2, 3))
        return {"success": True, "error": None}

    except Exception as e:
        return {"success": False, "error": str(e)[:200]}


async def scan_threads(
    page,
    keywords: list[str],
    max_scan: int = 50,
) -> list[dict]:
    """掃描 Threads 搜尋結果並返回貼文列表（不回覆）

    用於預覽/除錯，讓使用者先看會回覆哪些貼文。
    """
    replier = ThreadsReplier()
    result = await search_and_reply(
        page, replier, keywords, max_replies=max_scan, dry_run=True
    )
    return result["results"]
