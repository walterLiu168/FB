"""養號引擎 — 模擬真人操作 + 防重複加社團"""
import asyncio
import random
import re

from playwright.async_api import Page
from utils.logger import log


class Nurturer:
    """帳號養護引擎"""

    async def browse_feed(self, page: Page, count: int = 5):
        """模擬瀏覽動態消息，每天 1~10 篇"""
        await page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(random.uniform(3, 6))

        for i in range(min(count, 10)):
            try:
                await page.evaluate("window.scrollBy(0, 800)")
                await asyncio.sleep(random.uniform(3, 8))

                if random.random() < 0.3:
                    like_btn = page.locator('div[aria-label="讚"], div[aria-label="Like"]').first
                    if await like_btn.is_visible():
                        await like_btn.click()
                        await asyncio.sleep(random.uniform(2, 5))

                if random.random() < 0.2:
                    comment_btn = page.locator('div[aria-label="留言"], div[aria-label="Comment"]').first
                    if await comment_btn.is_visible():
                        await comment_btn.click()
                        await asyncio.sleep(random.uniform(4, 8))

                await asyncio.sleep(random.uniform(10, 30))
            except Exception:
                pass

    async def join_groups(self, page: Page, keywords: list[str], max_groups: int = 5):
        """安全加入社團。自動跳過已加入的社團，每組加不超過 max_groups。

        防重複機制：
        - aria-label 含 "Join group XXX" → 可加入
        - aria-label 含 "Leave", "Joined", "Pending" → 跳過
        - 同一 session 記錄名稱，不重複
        """
        joined = 0
        already_member = 0
        joined_names = set()

        for keyword in keywords:
            if joined >= max_groups:
                break
            try:
                await page.goto(
                    f"https://www.facebook.com/search/groups/?q={keyword}",
                    wait_until="domcontentloaded", timeout=60000,
                )
                await asyncio.sleep(random.uniform(4, 7))

                # Find ALL visible buttons with aria-label containing "Join group"
                all_btns = await page.locator(
                    'div[role="button"][aria-label*="Join group" i], '
                    'div[role="button"][aria-label*="Join" i]'
                ).all()

                for btn in all_btns:
                    if joined >= max_groups:
                        break
                    try:
                        if not await btn.is_visible(timeout=1500):
                            continue

                        aria = (await btn.get_attribute("aria-label", timeout=1000) or "").strip()

                        # Skip if already joined/pending
                        if any(w in aria.lower() for w in ["joined", "leave", "退出", "pending", "待審核", "answer"]):
                            already_member += 1
                            continue

                        # Must start with "Join group" / "加入"
                        if not (aria.lower().startswith("join group") or aria.lower().startswith("加入")):
                            continue

                        # Extract group name from aria-label
                        group_name = aria
                        prefix = "Join group"
                        if group_name.lower().startswith(prefix.lower()):
                            group_name = group_name[len(prefix):].strip()
                        elif group_name.startswith("加入"):
                            group_name = group_name[2:].strip()

                        if group_name and group_name in joined_names:
                            continue

                        await btn.click(force=True, timeout=3000)
                        joined += 1
                        if group_name:
                            joined_names.add(group_name)
                        log("NURTURE", "join", f"加入社團 #{joined}: {group_name or keyword}", "✅")

                        await asyncio.sleep(random.uniform(60, 90))
                    except Exception:
                        continue

                # Count "already joined" buttons too
                joined_btns = await page.locator(
                    'div[role="button"][aria-label*="Joined" i], '
                    'div[role="button"][aria-label*="Leave" i], '
                    'div[role="button"][aria-label*="Pending" i], '
                    'span:has-text("已加入"), span:has-text("Joined"), '
                    'span:has-text("Pending"), span:has-text("待審核")'
                ).count()
                already_member += joined_btns

                log("NURTURE", "join",
                    f"搜尋 '{keyword}': 找到 {len(all_btns)} 個 Join 按鈕, "
                    f"已加入 {joined}/{max_groups}, 跳過 {already_member} 個已是成員",
                    "🔍")

            except Exception as e:
                log("NURTURE", "join", f"搜尋 '{keyword}' 異常: {e}", "⚠️")
                continue

        log("NURTURE", "join",
            f"完成：加入 {joined} 個新社團 / 跳過 {already_member} 個已是成員",
            "📊")
        return joined

    async def post_news_to_wall(self, page: Page, news_title: str, news_url: str):
        """抓取新聞/時事自動轉發到個人頁面"""
        try:
            await page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(random.uniform(3, 6))

            # Click "在想什麼"
            clicked = await page.evaluate("""
                () => {
                    const spans = document.querySelectorAll('span');
                    for (const s of spans) {
                        if (s.textContent.includes('mind') || s.textContent.includes('在想')) {
                            const btn = s.closest('[role="button"]');
                            if (btn) { btn.click(); return 'clicked'; }
                            s.click(); return 'clicked';
                        }
                    }
                    return 'not_found';
                }
            """)
            if clicked != 'clicked':
                return {"success": False, "error": "找不到狀態框"}

            await asyncio.sleep(random.uniform(2, 4))

            # Fill content
            editors = await page.locator('[contenteditable="true"]').all()
            for ed in editors:
                if await ed.is_visible(timeout=1000):
                    await ed.click(force=True, timeout=2000)
                    await asyncio.sleep(0.5)
                    await ed.fill(f"{news_title}\n{news_url}")
                    break

            await asyncio.sleep(random.uniform(2, 4))

            # Publish
            for sel in [
                'div[role="button"]:has-text("Post"):not(:has-text("Add"))',
                'div[aria-label="Post"][role="button"]',
            ]:
                btn = page.locator(sel).first
                if await btn.count() > 0:
                    await btn.click(force=True, timeout=3000)
                    return {"success": True}

            return {"success": False, "error": "找不到發佈按鈕"}

        except Exception as e:
            return {"success": False, "error": str(e)}
