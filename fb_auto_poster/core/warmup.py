"""Instagram / Threads 帳號暖號引擎 — 14 天階段式養號

Instagram 2026 年 ML 檢測極度嚴格。新帳號或閒置帳號如果直接大量操作，
detection rate 超過 80%。暖號是唯一可行的自動化路徑。

階段設計 (14 天):
  階段 1 (Day 1-3):  被動瀏覽 — 只逛不碰，建立「真人使用」模式
  階段 2 (Day 4-7):  輕量互動 — 少量按讚，開始看 Reels/Stories
  階段 3 (Day 8-10): 中量互動 — 追蹤少數帳號 + 有意義留言
  階段 4 (Day 11-14): 正常化 — 首篇貼文 + Stories + 全功能解鎖

防 ban 核心策略:
  - 每日動作量動態浮動 20-30%（絕不重複相同數字）
  - 凌晨 1-6 點絕不活動（睡眠時段模擬）
  - 每週 1-2 天休息日（真人特徵）
  - 動作間隨機延遲（模擬閱讀時間）
  - 分 3-4 個時段執行（不像機器全天候運作）
  - 動作順序隨機化（不是固定 like→follow→comment）
"""
import json
import os
import random
import hashlib
from datetime import datetime, date, timedelta
from typing import Optional

_IG_WARMUP_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "warmup"
)


def _warmup_path(account_id: str) -> str:
    return os.path.join(_IG_WARMUP_DIR, f"{account_id}.json")


# ── 每日限制矩陣（每個階段每天的最大值） ──
# 格式: phase → [like_max, follow_max, unfollow_max, comment_max, story_view_max, browse_minutes]
_LIMITS = {
    1: [0, 0, 0, 0, 5, 15],      # Day 1-3: 只瀏覽
    2: [20, 0, 0, 0, 15, 25],     # Day 4-7: 按讚 + Stories
    3: [35, 10, 0, 3, 25, 30],    # Day 8-10: 追蹤 + 留言
    4: [50, 15, 5, 5, 35, 35],    # Day 11-14: 完整功能
}


def _get_phase(day: int) -> int:
    if day <= 3:
        return 1
    elif day <= 7:
        return 2
    elif day <= 10:
        return 3
    else:
        return 4


def _get_today_limits(day: int) -> dict:
    """取得今天的浮動限制（基礎值 ± 20-30% 隨機化）"""
    phase = _get_phase(day)
    base = _LIMITS[phase]
    variation = random.uniform(0.75, 0.95)  # 永遠低於上限，不測試極限
    return {
        "day": day,
        "phase": phase,
        "phase_name": ["", "被動瀏覽", "輕量互動", "中量互動", "正常化"][phase],
        "max_likes": max(0, int(base[0] * variation)),
        "max_follows": max(0, int(base[1] * variation)),
        "max_unfollows": max(0, int(base[2] * variation)),
        "max_comments": max(0, int(base[3] * variation)),
        "max_story_views": max(0, int(base[4] * variation)),
        "browse_minutes": max(5, int(base[5] * variation)),
    }


def _is_rest_day(account_id: str, today: date) -> bool:
    """判斷今天是否為休息日（每週 1-2 天）"""
    seed = int(hashlib.md5(account_id.encode()).hexdigest()[:8], 16)
    rng = random.Random(seed + today.isocalendar()[1])
    rest_days = rng.sample([0, 1, 2, 3, 4, 5, 6], 2)  # 每週 2 天休息
    return today.weekday() in rest_days


def _is_nighttime() -> bool:
    """凌晨 1-6 點不活動"""
    hour = datetime.now().hour
    return 1 <= hour < 6


def _generate_sessions(limits: dict) -> list[dict]:
    """將每日動作量拆分為 3-4 個時段"""
    n_sessions = random.choice([3, 3, 4])
    sessions = []
    total_likes = limits["max_likes"]
    total_follows = limits["max_follows"]
    total_comments = limits["max_comments"]
    total_stories = limits["max_story_views"]
    total_browse = limits["browse_minutes"]

    for i in range(n_sessions):
        remaining = n_sessions - i
        session = {
            "likes": total_likes // remaining if i < n_sessions - 1 else total_likes,
            "follows": total_follows // remaining if i < n_sessions - 1 else total_follows,
            "comments": total_comments // remaining if i < n_sessions - 1 else total_comments,
            "story_views": total_stories // remaining if i < n_sessions - 1 else total_stories,
            "browse_minutes": max(1, total_browse // remaining),
        }
        total_likes -= session["likes"]
        total_follows -= session["follows"]
        total_comments -= session["comments"]
        total_stories -= session["story_views"]
        total_browse -= session["browse_minutes"]
        sessions.append(session)
    return sessions


# ════════════════════════════════════════════
#  暖號狀態管理
# ════════════════════════════════════════════

def load_warmup_state(account_id: str) -> dict:
    """載入帳號的暖號狀態"""
    path = _warmup_path(account_id)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return _init_state(account_id)


def _init_state(account_id: str) -> dict:
    now = datetime.now().isoformat()
    return {
        "account_id": account_id,
        "started_at": now,
        "day": 1,
        "last_session": None,
        "sessions_completed_today": 0,
        "total_likes": 0,
        "total_follows": 0,
        "total_comments": 0,
        "total_story_views": 0,
        "total_browse_minutes": 0,
        "rest_days_taken": 0,
        "post_history": [],
        "followed_users": [],
        "liked_posts": [],       # post_url → date
        "commented_posts": [],   # post_url → date
        "created_at": now,
    }


def save_warmup_state(account_id: str, state: dict):
    os.makedirs(_IG_WARMUP_DIR, exist_ok=True)
    with open(_warmup_path(account_id), "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def get_daily_plan(account_id: str) -> dict:
    """取得今日暖號計畫（供 UI 顯示和執行）"""
    state = load_warmup_state(account_id)
    today = date.today()

    # 檢查是否該休息
    rest = _is_rest_day(account_id, today)
    night = _is_nighttime()

    limits = _get_today_limits(state["day"])
    sessions = _generate_sessions(limits) if not rest else []

    plan = {
        "account_id": account_id,
        "day": state["day"],
        "phase": limits["phase"],
        "phase_name": limits["phase_name"],
        "is_rest_day": rest,
        "is_nighttime": night,
        "should_skip": rest or night,
        "limits": limits,
        "sessions": sessions,
        "sessions_done": state.get("sessions_completed_today", 0),
        "total_sessions": len(sessions),
        "progress_pct": (
            (state.get("sessions_completed_today", 0) / max(len(sessions), 1)) * 100
        ),
        "lifetime_likes": state.get("total_likes", 0),
        "lifetime_follows": state.get("total_follows", 0),
        "lifetime_comments": state.get("total_comments", 0),
        "started_at": state.get("started_at"),
    }
    return plan


def record_session_done(account_id: str, session_result: dict):
    """記錄一個暖號時段完成"""
    state = load_warmup_state(account_id)
    now = datetime.now().isoformat()

    state["last_session"] = now
    state["sessions_completed_today"] = state.get("sessions_completed_today", 0) + 1
    state["total_likes"] = state.get("total_likes", 0) + session_result.get("likes_done", 0)
    state["total_follows"] = state.get("total_follows", 0) + session_result.get("follows_done", 0)
    state["total_comments"] = state.get("total_comments", 0) + session_result.get("comments_done", 0)
    state["total_story_views"] = state.get("total_story_views", 0) + session_result.get("stories_viewed", 0)
    state["total_browse_minutes"] = state.get("total_browse_minutes", 0) + session_result.get("browse_minutes", 0)
    state["liked_posts"].extend(session_result.get("liked_posts", []))
    state["commented_posts"].extend(session_result.get("commented_posts", []))
    state["followed_users"].extend(session_result.get("followed_users", []))

    save_warmup_state(account_id, state)


def advance_day(account_id: str) -> int:
    """換日：檢查是否需要推進天數"""
    state = load_warmup_state(account_id)
    today_str = date.today().isoformat()
    last_date = state.get("last_session_date", "")

    if last_date != today_str:
        # 新的一天
        if _is_rest_day(account_id, date.today()):
            state["rest_days_taken"] = state.get("rest_days_taken", 0) + 1
        else:
            state["day"] = min(state["day"] + 1, 14)
        state["sessions_completed_today"] = 0
        state["last_session_date"] = today_str
        save_warmup_state(account_id, state)

    return state["day"]


def reset_warmup(account_id: str):
    """重置暖號記錄（帳號重置用）"""
    state = _init_state(account_id)
    save_warmup_state(account_id, state)


def get_all_warmup_status() -> list[dict]:
    """取得所有帳號的暖號摘要"""
    results = []
    for fn in os.listdir(_IG_WARMUP_DIR) if os.path.exists(_IG_WARMUP_DIR) else []:
        if fn.endswith(".json"):
            acc_id = fn.replace(".json", "")
            plan = get_daily_plan(acc_id)
            results.append({
                "account_id": acc_id,
                "day": plan["day"],
                "phase": plan["phase_name"],
                "progress": f"{plan['sessions_done']}/{plan['total_sessions']}",
                "is_rest": plan["is_rest_day"],
                "should_skip": plan["should_skip"],
            })
    return results
