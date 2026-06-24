"""內容行事曆 + 草稿庫 — 排程規劃與物件草稿管理

功能：
  - 草稿箱：儲存未完成的貼文 (欄位+圖片+社團設定)
  - 內容行事曆：月曆檢視排定的貼文
  - 循環發文：每日/每週固定時間重發
  - 拖曳時間軸：視覺化管理發文排程
"""
import json
import os
import threading
from datetime import datetime, timedelta, date
from typing import Optional

from utils.logger import log

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
_DRAFTS_FILE = os.path.join(_DATA_DIR, "drafts.json")
_CALENDAR_FILE = os.path.join(_DATA_DIR, "calendar.json")
_RECURRING_FILE = os.path.join(_DATA_DIR, "recurring.json")

_lock = threading.Lock()


class DraftLibrary:
    """草稿箱 — 儲存/載入/編輯未完成的發文草稿"""
    
    def __init__(self):
        os.makedirs(_DATA_DIR, exist_ok=True)
        self._drafts: list[dict] = self._load()
    
    def _load(self) -> list[dict]:
        try:
            if os.path.exists(_DRAFTS_FILE):
                with open(_DRAFTS_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return []
    
    def _save(self):
        with _lock:
            with open(_DRAFTS_FILE, "w", encoding="utf-8") as f:
                json.dump(self._drafts, f, ensure_ascii=False, indent=2)
    
    def create(self, name: str = "", template_data: dict = None,
               images: list = None, groups: list = None,
               account_id: str = "", template_name: str = "房屋物件") -> str:
        """新增草稿
        
        Returns:
            草稿 ID
        """
        import uuid
        draft_id = uuid.uuid4().hex[:8]
        now = datetime.now().isoformat()
        self._drafts.append({
            "id": draft_id,
            "name": name or f"草稿 {len(self._drafts) + 1}",
            "template_data": template_data or {},
            "template_name": template_name,
            "images": images or [],
            "groups": groups or [],
            "account_id": account_id,
            "created_at": now,
            "updated_at": now,
            "status": "draft",  # draft | scheduled | posted
            "scheduled_at": None,
        })
        self._save()
        log("DRAFT", name, "草稿已建立", "📝")
        return draft_id
    
    def update(self, draft_id: str, **kwargs):
        """更新草稿欄位"""
        for d in self._drafts:
            if d["id"] == draft_id:
                for k, v in kwargs.items():
                    if k in d:
                        d[k] = v
                d["updated_at"] = datetime.now().isoformat()
                self._save()
                return True
        return False
    
    def delete(self, draft_id: str) -> bool:
        before = len(self._drafts)
        self._drafts = [d for d in self._drafts if d["id"] != draft_id]
        if len(self._drafts) < before:
            self._save()
            return True
        return False
    
    def get(self, draft_id: str) -> Optional[dict]:
        for d in self._drafts:
            if d["id"] == draft_id:
                return d
        return None
    
    def list_drafts(self, status: str = None) -> list[dict]:
        """列出草稿，按更新時間倒序"""
        result = list(self._drafts)
        if status:
            result = [d for d in result if d.get("status") == status]
        result.sort(key=lambda d: d.get("updated_at", ""), reverse=True)
        return result
    
    def schedule(self, draft_id: str, at_time: str) -> bool:
        """將草稿排入行事曆"""
        return self.update(draft_id, status="scheduled", scheduled_at=at_time)
    
    def mark_posted(self, draft_id: str) -> bool:
        """標記已發文"""
        return self.update(draft_id, status="posted")
    
    @property
    def stats(self) -> dict:
        counts = {"draft": 0, "scheduled": 0, "posted": 0}
        for d in self._drafts:
            s = d.get("status", "draft")
            counts[s] = counts.get(s, 0) + 1
        counts["total"] = len(self._drafts)
        return counts


class ContentCalendar:
    """內容行事曆 — 日/週/月檢視排程貼文"""
    
    def __init__(self):
        os.makedirs(_DATA_DIR, exist_ok=True)
        self._events = self._load()
    
    def _load(self) -> list[dict]:
        try:
            if os.path.exists(_CALENDAR_FILE):
                with open(_CALENDAR_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return []
    
    def _save(self):
        with _lock:
            with open(_CALENDAR_FILE, "w", encoding="utf-8") as f:
                json.dump(self._events, f, ensure_ascii=False, indent=2)
    
    def add_event(self, date_str: str, time_str: str,
                  title: str, draft_id: str = "",
                  groups: list = None, account_id: str = "") -> str:
        """加入行事曆事件"""
        import uuid
        evt_id = uuid.uuid4().hex[:8]
        scheduled = f"{date_str}T{time_str}:00"
        self._events.append({
            "id": evt_id,
            "title": title,
            "draft_id": draft_id,
            "scheduled_at": scheduled,
            "groups": groups or [],
            "account_id": account_id,
            "status": "pending",
            "created_at": datetime.now().isoformat(),
        })
        self._save()
        return evt_id
    
    def get_events(self, from_date: str = None, to_date: str = None) -> list[dict]:
        """取得指定日期範圍的事件"""
        events = list(self._events)
        if from_date:
            events = [e for e in events if e.get("scheduled_at", "") >= from_date]
        if to_date:
            events = [e for e in events if e.get("scheduled_at", "") <= to_date + "T23:59:59"]
        events.sort(key=lambda e: e.get("scheduled_at", ""))
        return events
    
    def get_today(self) -> list[dict]:
        today = date.today().isoformat()
        return self.get_events(today, today)
    
    def get_week(self) -> list[dict]:
        today = date.today()
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=6)
        return self.get_events(start.isoformat(), end.isoformat())
    
    def get_month(self, year: int = None, month: int = None) -> dict:
        """取得整月行事曆 (以日為 key)"""
        if year is None or month is None:
            today = date.today()
            year, month = today.year, today.month
        
        from_date = date(year, month, 1).isoformat()
        if month == 12:
            to_date = date(year + 1, 1, 1).isoformat()
        else:
            to_date = date(year, month + 1, 1).isoformat()
        
        events = self.get_events(from_date, to_date)
        
        # Group by date
        calendar = {}
        for e in events:
            day = e.get("scheduled_at", "")[:10]
            calendar.setdefault(day, []).append(e)
        
        return {
            "year": year,
            "month": month,
            "days": calendar,
            "total": len(events),
        }
    
    def mark_done(self, event_id: str) -> bool:
        for e in self._events:
            if e["id"] == event_id:
                e["status"] = "done"
                self._save()
                return True
        return False
    
    def mark_failed(self, event_id: str, error: str = "") -> bool:
        for e in self._events:
            if e["id"] == event_id:
                e["status"] = "failed"
                e["error"] = error
                self._save()
                return True
        return False
    
    def get_pending_now(self, window_minutes: int = 5) -> list[dict]:
        """取得現在應該發文的事件 (±N 分鐘內)"""
        now = datetime.now()
        window = timedelta(minutes=window_minutes)
        pending = []
        for e in self._events:
            if e.get("status") != "pending":
                continue
            try:
                sched = datetime.fromisoformat(e["scheduled_at"])
                if abs(now - sched) <= window:
                    pending.append(e)
            except Exception:
                continue
        return pending
    
    @property
    def stats(self) -> dict:
        pending = sum(1 for e in self._events if e.get("status") == "pending")
        done = sum(1 for e in self._events if e.get("status") == "done")
        failed = sum(1 for e in self._events if e.get("status") == "failed")
        return {"pending": pending, "done": done, "failed": failed, "total": len(self._events)}


# ── 智慧發文時間引擎 ──

# 台灣社團預設最佳時段 (基於 FB 社團活躍數據)
_DEFAULT_BEST_TIMES = {
    "weekday": ["09:00", "12:00", "15:00", "20:00", "21:00"],
    "weekend": ["10:00", "14:00", "19:00", "21:00"],
    "dinner": ["18:00", "19:00", "20:00"],  # 晚餐時間最活躍
}


class SmartScheduler:
    """智慧排程引擎 — 根據社團活躍時間推薦最佳發文時段"""
    
    def __init__(self):
        self._group_stats = self._load_stats()
    
    def _load_stats(self) -> dict:
        path = os.path.join(_DATA_DIR, "group_activity.json")
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return {}
    
    def _save_stats(self):
        path = os.path.join(_DATA_DIR, "group_activity.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._group_stats, f, ensure_ascii=False, indent=2)
    
    def get_best_time(self, group_url: str = None, target_date: str = None) -> str:
        """取得最佳發文時間
        
        Args:
            group_url: 社團 URL (可選，有記錄則用社團特定最佳時段)
            target_date: 目標日期 (ISO format)，判斷平日/週末
        
        Returns:
            建議時間 "HH:MM"
        """
        import random
        
        # 判斷平日/週末
        if target_date:
            try:
                d = datetime.fromisoformat(target_date)
                is_weekend = d.weekday() >= 5
            except Exception:
                is_weekend = False
        else:
            is_weekend = date.today().weekday() >= 5
        
        # 社團特定最佳時段
        if group_url and group_url in self._group_stats:
            stats = self._group_stats[group_url]
            if stats.get("best_hours"):
                return random.choice(stats["best_hours"])
        
        # 預設時段
        times = _DEFAULT_BEST_TIMES["weekend"] if is_weekend else _DEFAULT_BEST_TIMES["weekday"]
        return random.choice(times)
    
    def get_next_slot(self, group_url: str = None, min_delay_min: int = 30) -> str:
        """取得下一個可用發文時段 (從現在起算最近的一次)"""
        from datetime import datetime, timedelta
        
        now = datetime.now()
        best = self.get_best_time(group_url)
        best_h, best_m = int(best.split(":")[0]), int(best.split(":")[1])
        
        # 今天的最佳時段
        candidate = now.replace(hour=best_h, minute=best_m, second=0, microsecond=0)
        
        # 如果已經過了，找下一個
        if candidate <= now + timedelta(minutes=min_delay_min):
            candidate += timedelta(hours=3)  # 下一輪
        
        # 不超過凌晨 1 點
        if candidate.hour < 6:
            candidate = candidate.replace(hour=9)
        
        return candidate.strftime("%Y-%m-%d %H:%M")
    
    def record_engagement(self, group_url: str, post_time: str, likes: int):
        """記錄發文互動數據，用於學習最佳時段"""
        if not group_url:
            return
        
        try:
            dt = datetime.fromisoformat(post_time)
            hour = dt.hour
        except Exception:
            return
        
        if group_url not in self._group_stats:
            self._group_stats[group_url] = {"best_hours": [], "hour_scores": {}}
        
        stats = self._group_stats[group_url]
        scores = stats.setdefault("hour_scores", {})
        hour_k = str(hour)
        scores[hour_k] = scores.get(hour_k, 0) + likes + 1  # +1 至少有一次發文記錄
        
        # 取 top 5 時段
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        stats["best_hours"] = [f"{int(h):02d}:00" for h, _ in ranked[:5]]
        self._save_stats()
    
    def generate_week_plan(self, group_url: str = None, posts_per_day: int = 2) -> list[str]:
        """產生一週發文計劃 (7 天 x N 篇)"""
        plan = []
        today = date.today()
        for day_offset in range(7):
            d = today + timedelta(days=day_offset)
            day_name = d.strftime("%Y-%m-%d")
            for _ in range(posts_per_day):
                slot = self.get_best_time(group_url, day_name)
                plan.append(f"{day_name}T{slot}:00")
        plan.sort()
        return plan
    
    def get_stats(self) -> dict:
        """取得學習統計"""
        groups_with_data = len(self._group_stats)
        return {
            "trained_groups": groups_with_data,
            "default_times": _DEFAULT_BEST_TIMES,
        }
