"""暖號執行器 — 用 Playwright 執行人化瀏覽 + 互動

不直接和 IG DOM 打架。策略是：
  1. 載入 IG Cookie → 開 IG 首頁
  2. 被動瀏覽（隨機滾動 + 停留）→ 模擬真人閱讀
  3. 少量按讚（Explore 或首頁動態牆隨機選貼文）
  4. 看 Stories（點擊 stories tray）
  5. 追蹤推薦帳號（首頁建議追蹤區塊）
  6. 有意義留言（從模板庫選 + 加隨機表情）
"""
import asyncio
import random
from datetime import datetime
from typing import Optional

from utils.logger import log


# ── 隨機留言模板（暖號用，必須自然且多樣） ──
_WARMUP_COMMENTS = [
    "Love this! 🔥",
    "Great shot! 📸",
    "This is so cool!",
    "Nice one! 👏",
    "Beautiful! ❤️",
    "Love the vibe! ✨",
    "So good! 😍",
    "Wow, amazing! 🙌",
    "Incredible work! 💪",
    "This made my day! ☀️",
    "So inspiring 🌟",
    "Love this perspective!",
    "Great content!",
    "This is fire 🔥",
    "Obsessed! ✨",
    "Absolutely love this 💯",
    "Perfect timing 📸",
    "What a masterpiece!",
    "So creative! 🎨",
    "Youre killing it!",
    "This is the content I needed 💎",
    "So underrated!",
    "Goals! 🙌",
    "Best one Ive seen today!",
    "Literal perfection 👌",
]


async def _human_delay(lo=0.5, hi=3.0):
    await asyncio.sleep(random.uniform(lo, hi))


async def _scroll_random(page, count=3):
    """隨機向下滾動，模擬瀏覽"""
    for _ in range(count):
        scroll = random.randint(300, 900)
        await page.evaluate(f"window.scrollBy(0, {scroll})")
        await _human_delay(1.5, 4.0)


async def _browse_session(page, minutes=5) -> int:
    """被動瀏覽：隨機滾動、停留、看內容。不互動。"""
    log("WARMUP", "browse", f"瀏覽 {minutes} 分鐘", "👀")
    end = asyncio.get_event_loop().time() + (minutes * 60)

    while asyncio.get_event_loop().time() < end:
        # 滾動
        await _scroll_random(page, random.randint(1, 3))
        # 模擬閱讀停留
        await _human_delay(2, 8)
        # 有時快速向上回滾
        if random.random() < 0.3:
            await page.evaluate(f"window.scrollBy(0, -{random.randint(200, 600)})")
            await _human_delay(1, 3)

    return minutes


async def _like_posts(page, count=10) -> int:
    """在首頁動態牆隨機按讚。不重複、不會連續點。"""
    done = 0
    tried = 0
    max_tries = count * 3

    # 滾動到有足夠貼文
    await _scroll_random(page, 5)
    await _human_delay(1, 2)

    while done < count and tried < max_tries:
        tried += 1
        try:
            # 用 aria-label 找 like 按鈕（未被按過的）
            like_btns = page.locator('svg[aria-label="Like"], svg[aria-label="Unlike"]').all()
            if not like_btns:
                like_btns = page.locator('span:has(svg[aria-label="Like"])').all()
            if not like_btns:
                like_btns = page.locator('div[role="button"]:has(svg[aria-label="Like"])').all()

            if not like_btns:
                await _scroll_random(page, 2)
                await _human_delay(1, 2)
                continue

            btn = random.choice(like_btns[:20])
            parent = btn.locator("..").first
            try:
                await parent.click(timeout=3000)
            except Exception:
                await btn.click(force=True, timeout=3000)

            done += 1
            log("WARMUP", "like", f"{done}/{count}", "❤️")
            await _human_delay(15, 45)  # 按讚間隔：15-45 秒（真人閱讀時間）
        except Exception:
            await _scroll_random(page, 1)
            await _human_delay(2, 4)
            continue

    return done


async def _view_stories(page, count=5) -> int:
    """點擊並觀看 Stories"""
    done = 0
    try:
        # Stories tray
        story_selectors = [
            'div[role="button"]:has(img[data-testid="story-ring"])',
            'li:has(button):has(canvas)',
            'button:has(img[alt*="story" i])',
        ]

        story_btn = None
        for sel in story_selectors:
            try:
                el = page.locator(sel).first
                if await el.count() > 0:
                    story_btn = el
                    break
            except Exception:
                continue

        if story_btn:
            await story_btn.click(timeout=3000)
            await _human_delay(2, 5)

            # 觀看幾個 stories
            for _ in range(count):
                await _human_delay(3, 8)  # 看 story
                try:
                    # 點右側前進
                    await page.keyboard.press("ArrowRight")
                    await _human_delay(0.5, 1)
                except Exception:
                    pass
                done += 1

            # 退出 stories
            await page.keyboard.press("Escape")
            await _human_delay(0.5, 1)
    except Exception as e:
        log("WARMUP", "story", f"Stories error: {e}", "⚠️")

    return done


async def _follow_suggested(page, count=5) -> int:
    """追蹤 IG 推薦的帳號"""
    done = 0
    tried = 0

    await _scroll_random(page, 3)
    await _human_delay(1, 3)

    # IG 首頁推薦追蹤區塊
    follow_btns = page.locator('div[role="button"]:has-text("Follow")').all()
    if not follow_btns:
        follow_btns = page.locator('button:has-text("Follow")').all()

    for btn in follow_btns[: count * 3]:
        if done >= count:
            break
        try:
            text = await btn.inner_text()
            if "follow" in text.lower() and "following" not in text.lower():
                await btn.click(timeout=3000)
                done += 1
                tried += 1
                log("WARMUP", "follow", f"{done}/{count}", "👤")
                await _human_delay(45, 90)  # 追蹤間隔 45-90 秒
        except Exception:
            continue
        if tried >= count * 4:
            break

    return done


async def _comment_random(page, count=3) -> int:
    """在隨機貼文留言"""
    done = 0
    for _ in range(count * 3):
        if done >= count:
            break
        try:
            # 找 comment textarea
            boxes = page.locator('textarea[aria-label*="comment" i]').all()
            if not boxes:
                boxes = page.locator('textarea[placeholder*="comment" i]').all()
            if not boxes:
                await _scroll_random(page, 2)
                await _human_delay(1, 2)
                continue

            box = random.choice(boxes[:5])
            await box.click(timeout=2000)
            await _human_delay(0.5, 1.5)

            comment = random.choice(_WARMUP_COMMENTS)
            await box.fill(comment)
            await _human_delay(0.5, 1)

            await page.keyboard.press("Enter")
            done += 1
            log("WARMUP", "comment", f"{done}/{count}: {comment[:30]}", "💬")
            await _human_delay(60, 180)  # 留言間隔 1-3 分鐘

        except Exception:
            await _scroll_random(page, 1)
            await _human_delay(2, 5)
            continue

    return done


# ════════════════════════════════════════════
#  公開 API
# ════════════════════════════════════════════

async def run_warmup_session(page, plan: dict) -> dict:
    """執行一個暖號時段

    依照 plan 中的 session 限制執行瀏覽/按讚/追蹤/留言。
    實際執行量永遠低於限制值（再加一層隨機保險）。

    Returns:
        {"likes_done": int, "follows_done": int, "comments_done": int,
         "stories_viewed": int, "browse_minutes": int, ...}
    """
    if not plan.get("sessions"):
        return {"likes_done": 0, "follows_done": 0, "comments_done": 0,
                "stories_viewed": 0, "browse_minutes": 0, "status": "rest_day"}

    session_idx = plan.get("sessions_done", 0)
    if session_idx >= len(plan["sessions"]):
        return {"likes_done": 0, "follows_done": 0, "comments_done": 0,
                "stories_viewed": 0, "browse_minutes": 0, "status": "all_done"}

    session_plan = plan["sessions"][session_idx]
    result = {
        "likes_done": 0, "follows_done": 0, "comments_done": 0,
        "stories_viewed": 0, "browse_minutes": 0,
    }

    try:
        # Step 1: 被動瀏覽
        browse_mins = max(1, session_plan.get("browse_minutes", 3))
        result["browse_minutes"] = await _browse_session(page, browse_mins)

        # Step 2: 看 Stories
        if session_plan.get("story_views", 0) > 0:
            stories_target = min(session_plan["story_views"], random.randint(3, 8))
            result["stories_viewed"] = await _view_stories(page, stories_target)

        # Step 3: 按讚
        if session_plan.get("likes", 0) > 0:
            likes_target = min(session_plan["likes"], random.randint(3, 10))
            result["likes_done"] = await _like_posts(page, likes_target)

        # Step 4: 追蹤
        if session_plan.get("follows", 0) > 0:
            follow_target = min(session_plan["follows"], 3)
            result["follows_done"] = await _follow_suggested(page, follow_target)

        # Step 5: 留言
        if session_plan.get("comments", 0) > 0:
            comment_target = min(session_plan["comments"], 2)
            result["comments_done"] = await _comment_random(page, comment_target)

        result["status"] = "ok"
        log("WARMUP", "session", (
            f"Done: {result['browse_minutes']}m browse, "
            f"{result['likes_done']} likes, {result['follows_done']} follows, "
            f"{result['comments_done']} comments"
        ), "✅")

    except Exception as e:
        result["status"] = f"error: {e}"
        log("WARMUP", "session", f"Failed: {e}", "❌")

    return result


async def run_warmup_full_day(page, account_id: str) -> dict:
    """執行一整天所有剩餘的暖號時段

    自動檢查休息日、黑夜，並排隊所有未完成的時段。
    每個時段之間有 2-4 小時的隨機間隔。

    Returns:
        合計結果 dict
    """
    from core.warmup import get_daily_plan, load_warmup_state, record_session_done, advance_day

    advance_day(account_id)
    plan = get_daily_plan(account_id)

    if plan["should_skip"]:
        reason = "nighttime" if plan["is_nighttime"] else "rest_day"
        log("WARMUP", "daily", f"Skip: {reason}", "⏸️")
        return {"status": "skipped", "reason": reason}

    state = load_warmup_state(account_id)
    sessions_done = state.get("sessions_completed_today", 0)
    total_sessions = len(plan["sessions"])
    remaining = max(0, total_sessions - sessions_done)

    if remaining == 0:
        log("WARMUP", "daily", "All sessions done today", "✅")
        return {"status": "all_done"}

    aggregate = {"likes_done": 0, "follows_done": 0, "comments_done": 0,
                 "stories_viewed": 0, "browse_minutes": 0, "sessions_run": 0}

    for i in range(remaining):
        if i > 0:
            gap_min = random.randint(120, 240)  # 2-4 小時
            log("WARMUP", "daily", f"Next session in {gap_min} min", "⏳")
            await asyncio.sleep(gap_min * 60)

        r = await run_warmup_session(page, plan)
        record_session_done(account_id, r)

        for k in ("likes_done", "follows_done", "comments_done", "stories_viewed", "browse_minutes"):
            aggregate[k] = aggregate.get(k, 0) + r.get(k, 0)
        aggregate["sessions_run"] += 1

    aggregate["status"] = "ok"
    return aggregate
