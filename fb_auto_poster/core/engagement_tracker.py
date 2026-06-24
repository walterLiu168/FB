"""發文成效追蹤器 — 自動檢查已發貼文的讚數/留言/分享

功能:
  - 每次啟動時掃描待追蹤貼文
  - 定時 (每 2 小時) 檢查貼文互動數據
  - 記錄歷史趨勢 (可匯出報表)
  - 追蹤上限: 最近 100 篇貼文
"""
import json
import os
import asyncio
import time
from datetime import datetime, timedelta
from typing import Optional

from utils.logger import log

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
_TRACKER_FILE = os.path.join(_DATA_DIR, "engagement_tracker.json")
_MAX_TRACKED = 100


class EngagementTracker:
    """貼文互動追蹤器"""
    
    def __init__(self):
        os.makedirs(_DATA_DIR, exist_ok=True)
        self._data: dict = {"posts": {}, "last_scan": None}
        self._load()
    
    def _load(self):
        try:
            if os.path.exists(_TRACKER_FILE):
                with open(_TRACKER_FILE, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
        except Exception:
            self._data = {"posts": {}, "last_scan": None}
    
    def _save(self):
        try:
            # 只保留最近 100 筆
            posts = self._data.get("posts", {})
            if len(posts) > _MAX_TRACKED:
                sorted_posts = sorted(posts.items(), key=lambda x: x[1].get("posted_at", ""))
                self._data["posts"] = dict(sorted_posts[-_MAX_TRACKED:])
            with open(_TRACKER_FILE, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
    
    def register_post(self, post_url: str, title: str = "", account_id: str = ""):
        """註冊新貼文開始追蹤"""
        key = self._url_to_key(post_url)
        self._data["posts"][key] = {
            "url": post_url,
            "title": title,
            "account_id": account_id,
            "posted_at": datetime.now().isoformat(),
            "snapshots": [],
            "latest": {"likes": 0, "comments": 0, "shares": 0, "scanned_at": None},
        }
        self._save()
        log("ENGAGE", title or key, "開始追蹤", "📊")
    
    def record_snapshot(self, post_url: str, likes: int, comments: int, shares: int):
        """記錄一筆互動快照"""
        key = self._url_to_key(post_url)
        if key not in self._data["posts"]:
            return
        
        post = self._data["posts"][key]
        now_str = datetime.now().isoformat()
        
        # Keep max 48 snapshots (2 days at 1hr interval)
        post["snapshots"].append({
            "time": now_str,
            "likes": likes,
            "comments": comments,
            "shares": shares,
        })
        if len(post["snapshots"]) > 48:
            post["snapshots"] = post["snapshots"][-48:]
        
        post["latest"] = {
            "likes": likes,
            "comments": comments,
            "shares": shares,
            "scanned_at": now_str,
        }
        self._data["last_scan"] = now_str
        self._save()
    
    def get_top_posts(self, limit: int = 10, metric: str = "likes") -> list[dict]:
        """取得互動最高的貼文"""
        posts = list(self._data.get("posts", {}).values())
        posts.sort(key=lambda p: p.get("latest", {}).get(metric, 0), reverse=True)
        return posts[:limit]
    
    def get_trend(self, hours: int = 24) -> dict:
        """取得最近 N 小時的整體趨勢"""
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
        total_likes = 0
        total_comments = 0
        total_shares = 0
        post_count = 0
        
        for p in self._data.get("posts", {}).values():
            for snap in p.get("snapshots", []):
                if snap.get("time", "") >= cutoff:
                    total_likes += snap.get("likes", 0)
                    total_comments += snap.get("comments", 0)
                    total_shares += snap.get("shares", 0)
            if p.get("posted_at", "") >= cutoff:
                post_count += 1
        
        return {
            "period_hours": hours,
            "posts_published": post_count,
            "total_likes": total_likes,
            "total_comments": total_comments,
            "total_shares": total_shares,
            "avg_likes_per_post": round(total_likes / post_count, 1) if post_count else 0,
        }
    
    def get_summary(self) -> dict:
        """取得追蹤摘要"""
        posts = self._data.get("posts", {})
        active = sum(1 for p in posts.values() if p.get("latest", {}).get("scanned_at"))
        total_likes = sum(p.get("latest", {}).get("likes", 0) for p in posts.values())
        return {
            "tracked": len(posts),
            "scanned": active,
            "total_likes": total_likes,
            "top_posts": self.get_top_posts(5),
        }
    
    def _url_to_key(self, url: str) -> str:
        """URL 轉簡潔 key"""
        import hashlib
        return hashlib.md5(url.encode()).hexdigest()[:12]
    
    def export_report(self) -> str:
        """匯出純文字報表"""
        lines = ["=" * 50, "  FB POSTER — 發文成效報表", "=" * 50, ""]
        trend = self.get_trend(168)  # 7 days
        lines.append(f"📅 近 7 日: {trend['posts_published']} 篇貼文")
        lines.append(f"❤️ 總讚數: {trend['total_likes']}")
        lines.append(f"💬 總留言: {trend['total_comments']}")
        lines.append(f"📤 總分享: {trend['total_shares']}")
        lines.append(f"📊 平均讚: {trend['avg_likes_per_post']:.1f}/篇")
        lines.append("")
        lines.append("🏆 互動排行榜 (前 10):")
        for i, p in enumerate(self.get_top_posts(10), 1):
            name = p.get("title", "?")
            l = p.get("latest", {})
            lines.append(f"  {i:2}. {name[:40]:40s} ❤️{l.get('likes',0):4d} 💬{l.get('comments',0):3d} 📤{l.get('shares',0):3d}")
        
        return "\n".join(lines)


async def scan_page_engagement(page, post_url: str) -> dict:
    """使用 Playwright 掃描單篇貼文的互動數據
    
    Args:
        page: Playwright Page (已登入 FB)
        post_url: 貼文網址
    
    Returns:
        {"likes": int, "comments": int, "shares": int, "error": str|None}
    """
    try:
        await page.goto(post_url, wait_until="domcontentloaded", timeout=15000)
        await asyncio.sleep(3)
        
        likes = 0
        comments = 0
        shares = 0
        
        # 嘗試提取互動數 (FB 的 DOM 結構常變，多種 fallback)
        text = await page.inner_text("body")
        
        import re
        # "X 則留言" or "X comments"
        m = re.search(r"([\d,]+)\s*(?:則留言|comments|個留言)", text)
        if m:
            comments = int(m.group(1).replace(",", ""))
        
        # Like counts are harder — try aria-label
        try:
            like_els = await page.query_selector_all('[aria-label*="讚"]')
            for el in like_els:
                aria = await el.get_attribute("aria-label") or ""
                m = re.search(r"([\d,]+)\s*個?\s*讚", aria)
                if m:
                    lst = int(m.group(1).replace(",", ""))
                    if lst > likes:
                        likes = lst
        except Exception:
            pass
        
        # Shares: "X 次分享"
        m = re.search(r"([\d,]+)\s*(?:次分享|shares|個分享)", text)
        if m:
            shares = int(m.group(1).replace(",", ""))
        
        return {"likes": likes, "comments": comments, "shares": shares, "error": None}
        
    except Exception as e:
        return {"likes": 0, "comments": 0, "shares": 0, "error": str(e)[:100]}
