"""Instagram 自動留言引擎 — 關鍵字搜尋 + 自動留言

IG 不支援直接在搜尋結果回覆（不像 Threads），
改為兩種策略：
  1. Hashtag 搜尋 → 瀏覽貼文 → 留言
  2. 探索頁面 (Explore) → 相關貼文 → 留言

工作流程：
  1. 用 hashtag 搜尋 instagram.com/explore/tags/{keyword}/
  2. 爬取貼文列表
  3. 判斷貼文是否為目標客群
  4. 逐篇開啟 → 留言 → 記錄
"""
import os
import json
import asyncio
import random
from datetime import datetime
from typing import Optional

from utils.logger import log

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
_IG_REPLIED_FILE = os.path.join(_DATA_DIR, "ig_replied.json")
_IG_REPLY_TEMPLATES_FILE = os.path.join(_DATA_DIR, "ig_reply_templates.json")

_DEFAULT_REPLY_TEMPLATES = [
    "Great post! Love this 🔥",
    "This is so helpful, thanks for sharing! 🙌",
    "Amazing content! Keep it up 💪",
    "Love your style! 😍",
    "This is exactly what I needed, thank you! ✨",
    "So inspiring! Thanks for the motivation 🌟",
    "Great tips! I'll definitely try this 👍",
    "Wow, this looks amazing! 🔥",
    "Love the energy in this post! 💯",
    "Thanks for sharing this gem! 💎",
    "好棒的分享！學到了 🙌",
    "這個資訊太實用了，感謝分享 ✨",
    "完全同意！我也是這樣想的 💯",
    "太厲害了！請繼續分享 🔥",
    "讚！收藏起來 👍",
]


class InstagramReplier:
    """IG 自動留言引擎"""

    def __init__(self):
        os.makedirs(_DATA_DIR, exist_ok=True)
        self._replied = self._load_replied()
        self._templates = self._load_templates()
        self._settings = {
            "enabled": True,
            "max_comments_per_session": 10,
            "min_delay_seconds": 30,
            "max_delay_seconds": 120,
            "keywords": ["創業", "電商", "副業", "行銷", "自媒體"],
        }
        self._load_settings()

    def _load_replied(self) -> dict:
        try:
            if os.path.exists(_IG_REPLIED_FILE):
                with open(_IG_REPLIED_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    def _save_replied(self):
        try:
            with open(_IG_REPLIED_FILE, "w", encoding="utf-8") as f:
                json.dump(self._replied, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _load_templates(self) -> list[str]:
        try:
            if os.path.exists(_IG_REPLY_TEMPLATES_FILE):
                with open(_IG_REPLY_TEMPLATES_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data if isinstance(data, list) else list(_DEFAULT_REPLY_TEMPLATES)
        except Exception:
            pass
        self._save_templates(_DEFAULT_REPLY_TEMPLATES)
        return list(_DEFAULT_REPLY_TEMPLATES)

    def _save_templates(self, templates: list[str]):
        try:
            with open(_IG_REPLY_TEMPLATES_FILE, "w", encoding="utf-8") as f:
                json.dump(templates, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _load_settings(self):
        sf = os.path.join(_DATA_DIR, "ig_reply_settings.json")
        try:
            if os.path.exists(sf):
                with open(sf, "r", encoding="utf-8") as f:
                    self._settings.update(json.load(f))
        except Exception:
            pass

    @property
    def is_enabled(self) -> bool:
        return self._settings.get("enabled", True)

    @property
    def keywords(self) -> list[str]:
        return self._settings.get("keywords", [])

    def save_settings(self, **kwargs):
        self._settings.update(kwargs)
        sf = os.path.join(_DATA_DIR, "ig_reply_settings.json")
        try:
            with open(sf, "w", encoding="utf-8") as f:
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
        self._replied[post_url] = datetime.now().isoformat()
        self._save_replied()

    def has_replied(self, post_url: str) -> bool:
        return post_url in self._replied

    def pick_reply(self) -> str:
        if not self._templates:
            return "Great post! 👍"
        return random.choice(self._templates)


# ════════════════════════════════════════════
#  瀏覽器操作
# ════════════════════════════════════════════

async def ig_patrol_and_comment(
    page,
    replier: Optional[InstagramReplier] = None,
    keywords: Optional[list[str]] = None,
    max_comments: int = 10,
    dry_run: bool = False,
    progress_callback=None,
) -> dict:
    """IG Hashtag 巡邏 + 自動留言

    對每個關鍵字搜尋 hashtag 頁面，找到熱門貼文後留言。
    """
    if replier is None:
        replier = InstagramReplier()
    if keywords is None:
        keywords = replier.keywords
    if not keywords:
        return {"scanned": 0, "relevant": 0, "commented": 0, "skipped": 0, "results": [], "error": "No keywords"}

    stats = {"scanned": 0, "relevant": 0, "commented": 0, "skipped": 0, "results": []}

    for kw in keywords[:5]:  # limit to 5 keywords per session
        if stats["commented"] >= max_comments:
            break
        try:
            r = await _patrol_hashtag(page, replier, kw, max_comments - stats["commented"], dry_run, progress_callback)
            for k in ("scanned", "relevant", "commented", "skipped"):
                stats[k] += r.get(k, 0)
            stats["results"].extend(r.get("results", []))
        except Exception as e:
            log("IG", "patrol", f"Hashtag [{kw}] failed: {e}", "❌")
            continue
        await asyncio.sleep(random.uniform(5, 15))

    return stats


async def _patrol_hashtag(page, replier, keyword: str, max_remaining: int, dry_run: bool, progress_callback=None) -> dict:
    """巡邏單一 hashtag"""
    stats = {"scanned": 0, "relevant": 0, "commented": 0, "skipped": 0, "results": []}

    # Remove # if present
    tag = keyword.lstrip("#").strip().replace(" ", "")
    from urllib.parse import quote
    url = f"https://www.instagram.com/explore/tags/{quote(tag)}/"
    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(random.uniform(2, 5))

    # Find post links on the hashtag page
    post_links = page.locator('a[href*="/p/"]').all()
    if not post_links:
        post_links = page.locator('a[href*="/reel/"]').all()

    if not post_links:
        log("IG", "patrol", f"Tag [{tag}] no posts found", "⚠️")
        return stats

    max_scan = min(len(post_links), 20)
    log("IG", "patrol", f"Tag #{tag}: {max_scan} posts", "🔍")

    for i, link_el in enumerate(post_links[:max_scan]):
        if stats["commented"] >= max_remaining:
            break

        try:
            href = await link_el.get_attribute("href") or ""
            if not href or ("/p/" not in href and "/reel/" not in href):
                continue

            post_url = f"https://www.instagram.com{href.split('?')[0]}" if href.startswith("/") else href

            if replier.has_replied(post_url):
                stats["skipped"] += 1
                continue

            stats["scanned"] += 1

            if progress_callback:
                try:
                    await progress_callback(post_url, "scanning")
                except Exception:
                    pass

            if dry_run:
                stats["results"].append({"url": post_url, "action": "would_comment"})
                continue

            # Open post and comment
            comment_result = await _comment_on_post(page, post_url, replier.pick_reply())
            if comment_result["success"]:
                replier.mark_replied(post_url)
                stats["commented"] += 1
                log("IG", "patrol", f"Commented: {post_url[:50]}", "💬")
            else:
                log("IG", "patrol", f"Comment failed: {comment_result.get('error','')[:60]}", "❌")

            stats["results"].append({"url": post_url, "success": comment_result["success"]})

            delay = random.uniform(
                replier._settings.get("min_delay_seconds", 30),
                replier._settings.get("max_delay_seconds", 120),
            )
            await asyncio.sleep(delay)

        except Exception as e:
            log("IG", "patrol", f"Post error: {e}", "⚠️")
            continue

    return stats


async def _comment_on_post(page, post_url: str, comment_text: str) -> dict:
    """對 IG 貼文留言"""
    try:
        await page.goto(post_url, wait_until="domcontentloaded", timeout=15000)
        await asyncio.sleep(random.uniform(2, 4))

        # Find comment box
        comment_selectors = [
            'textarea[aria-label*="Add a comment"]',
            'textarea[placeholder*="Add a comment"]',
            'textarea[aria-label*="comment" i]',
            'form[role="presentation"] textarea',
        ]

        comment_box = None
        for sel in comment_selectors:
            try:
                el = page.locator(sel).first
                if await el.count() > 0 and await el.is_visible(timeout=2000):
                    comment_box = el
                    break
            except Exception:
                continue

        if not comment_box:
            return {"success": False, "error": "Comment box not found"}

        await comment_box.click(timeout=2000)
        await asyncio.sleep(0.5)
        await page.keyboard.type(comment_text, delay=random.randint(20, 50))
        await asyncio.sleep(random.uniform(0.5, 1))

        # Hit Enter to post
        await page.keyboard.press("Enter")
        await asyncio.sleep(random.uniform(2, 3))

        return {"success": True, "error": None}

    except Exception as e:
        return {"success": False, "error": str(e)[:200]}
