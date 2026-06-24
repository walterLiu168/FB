"""Threads.net 自動發文引擎 — 使用 Playwright 瀏覽器自動化

Threads.net 由 Meta 開發，類似 Twitter/X 的短文社群平台。
此模組提供：
  - 自動登入（透過 Instagram cookie / 手動登入）
  - 發文（純文字 / 文字+圖片）
  - 自動隨機 Hashtag
  - 發文間隔控制（防 ban）

工作流程：
  1. 開啟 threads.net
  2. 確認登入狀態
  3. 點擊「新串文」按鈕
  4. 輸入文字 + 上傳圖片
  5. 點擊發布
"""
import os
import asyncio
import random
from datetime import datetime
from typing import Optional
from playwright.async_api import Page

from utils.logger import log

# ── 工具函數 ──
async def _s(lo=0.5, hi=1.5):
    await asyncio.sleep(random.uniform(lo, hi))


async def _dl(lo=30, hi=120):
    """發文間隔：30 秒 ~ 2 分鐘（Threads 較寬鬆）"""
    await asyncio.sleep(random.uniform(lo, hi))


def _random_hashtag() -> str:
    """產生隨機輔助文字（增加自然感）"""
    words = [
        "\n\n#每日分享", "\n\n#生活紀錄", "\n\n#心得", "\n\n#推薦",
        "\n\n#實用技巧", "\n\n#日常", "\n\n#好物分享", "\n\n#討論",
        "\n.\n.", " ", "",
    ]
    return random.choice(words)


class ThreadsPoster:
    """Threads.net 發文引擎"""

    def __init__(self):
        self._screenshot_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "data", "debug_screenshots"
        )

    async def _screenshot(self, page: Page, step: str):
        """除錯截圖"""
        try:
            os.makedirs(self._screenshot_dir, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = os.path.join(self._screenshot_dir, f"threads_{ts}_{step}.png")
            await page.screenshot(path=path, full_page=False)
        except Exception:
            pass

    async def _ensure_logged_in(self, page: Page) -> bool:
        """確認已登入 Threads（透過 Instagram 帳號）

        Threads 使用 Instagram 帳號登入。
        優先檢查頁面上是否有已登入的跡象。
        """
        await page.goto("https://www.threads.net/", wait_until="domcontentloaded", timeout=30000)
        await _s(3, 5)

        # 檢查是否已登入 — 找頭像、發文框等跡象
        logged_in_indicators = [
            'a[href="/@"]',                # 自己的 profile link
            'svg[aria-label="Threads"]',   # Threads logo（登入後才會有完整 UI）
            'div[role="button"]:has-text("Start a thread")',
            'div:has-text("Start a thread")',
            '[aria-label="Home"]',          # 導覽列
            'a[href*="/notifications"]',
        ]

        for sel in logged_in_indicators:
            try:
                el = page.locator(sel).first
                if await el.count() > 0 and await el.is_visible(timeout=1000):
                    return True
            except Exception:
                continue

        # 檢查是否在登入頁面
        try:
            login_indicators = page.locator('text="Log in"').first
            if await login_indicators.count() > 0:
                # 在登入頁面 — 嘗試自動登入
                log("THREADS", "auth", "偵測到登入頁面，嘗試登入...", "🔑")
                logged = await self._try_login(page)
                return logged
        except Exception:
            pass

        # 不確定狀態，假設已登入（cookie 可能已過期但頁面仍在載入中）
        return True

    async def _try_login(self, page: Page) -> bool:
        """嘗試登入 Threads

        Threads 使用 Instagram 登入，所以需要 Instagram cookie。
        """
        try:
            # 找 "Use Instagram" / "Continue with Instagram" 按鈕
            login_selectors = [
                'text="Use Instagram"',
                'text="Continue with Instagram"',
                'text="Log in with Instagram"',
                'a:has-text("Log in")',
            ]

            for sel in login_selectors:
                try:
                    btn = page.locator(sel).first
                    if await btn.is_visible(timeout=2000):
                        await btn.click(timeout=3000)
                        await _s(3, 5)
                        break
                except Exception:
                    continue

            # 檢查是否成功登入
            await _s(2, 4)
            return await self._ensure_logged_in(page)

        except Exception as e:
            log("THREADS", "auth", f"登入失敗: {e}", "❌")
            return False

    async def _click_new_thread_button(self, page: Page) -> bool:
        """點擊發文按鈕

        Threads 有多個發文入口：
          - 底部導覽列的「+」按鈕
          - 主頁面上的 "Start a thread" / "What's new" 區塊
        """
        # 優先點擊底部導覽列的 + 發文按鈕
        selectors = [
            'a[href="/compose/post"]',
            'div[role="button"]:has-text("Start a thread")',
            'div:has-text("Start a thread")',
            'div[aria-label="Start a thread"]',
            'svg[aria-label="New thread"]',
            # 底部導覽列 post 按鈕
            'a[href="/"] svg[aria-label="Post"]',
            # 手機版 UI
            '[data-testid="create-post-button"]',
        ]

        for sel in selectors:
            try:
                el = page.locator(sel).first
                if await el.count() > 0:
                    await el.click(force=True, timeout=3000)
                    await _s(1, 2)
                    return True
            except Exception:
                continue

        return False

    async def _fill_thread_text(self, page: Page, text: str) -> bool:
        """在 Threads 編輯器中填入文字

        Threads 使用 contenteditable div 或 textarea。
        """
        await _s(1, 2)

        # 方法 1: 找 textarea
        try:
            ta = page.locator('textarea').first
            if await ta.count() > 0 and await ta.is_visible(timeout=1000):
                await ta.click(timeout=2000)
                await _s(0.3, 0.8)
                await ta.fill(text)
                return True
        except Exception:
            pass

        # 方法 2: contenteditable div
        try:
            editors = page.locator('[contenteditable="true"]').all()
            for ed in editors:
                if await ed.is_visible(timeout=1000):
                    await ed.click(force=True, timeout=2000)
                    await _s(0.3, 0.8)
                    await ed.fill(text)
                    return True
        except Exception:
            pass

        # 方法 3: 直接用鍵盤輸入
        try:
            await page.keyboard.press("Tab")
            await _s(0.2, 0.5)
            await page.keyboard.type(text, delay=random.randint(30, 80))
            return True
        except Exception:
            pass

        return False

    async def _upload_images(self, page: Page, image_paths: list[str]) -> bool:
        """上傳圖片到 Threads 貼文"""
        if not image_paths:
            return True

        log("THREADS", "post", f"上傳 {len(image_paths)} 張圖片...", "📷")

        # 找附件/圖片按鈕
        attachment_selectors = [
            'svg[aria-label="Attach"]',
            'svg[aria-label="Media"]',
            'input[type="file"]',
            'div[role="button"]:has(svg[aria-label="Attach"])',
            '[data-testid="attach-button"]',
        ]

        for sel in attachment_selectors:
            try:
                btn = page.locator(sel).first
                if await btn.is_visible(timeout=1000):
                    # 嘗試 file chooser 攔截
                    try:
                        async with page.expect_file_chooser(timeout=5000) as fc:
                            await btn.click(force=True, timeout=3000)
                        file_chooser = await fc.value
                        await file_chooser.set_files(image_paths)
                        await _s(2, 4)
                        log("THREADS", "post", f"✅ 圖片上傳成功 ({len(image_paths)} 張)", "📷")
                        return True
                    except Exception:
                        pass
            except Exception:
                continue

        # 直接找 file input
        try:
            fi = page.locator('input[type="file"]').first
            if await fi.count() > 0:
                await fi.set_input_files(image_paths)
                await _s(2, 4)
                return True
        except Exception:
            pass

        log("THREADS", "post", "⚠️ 圖片上傳失敗", "⚠️")
        return False

    async def _click_post_button(self, page: Page) -> bool:
        """點擊發布按鈕"""
        post_selectors = [
            'div[role="button"]:has-text("Post")',
            'div:has-text("Post"):not(:has-text("Start"))',
            'button:has-text("Post")',
            '[data-testid="post-button"]',
            'div[role="button"]:has-text("發布")',
        ]

        for sel in post_selectors:
            try:
                btn = page.locator(sel).last  # 用 last 避免點到其他 Post 文字
                if await btn.is_visible(timeout=1000):
                    await btn.click(force=True, timeout=3000)
                    await _s(3, 5)
                    return True
            except Exception:
                continue

        # 試鍵盤快捷鍵 Ctrl+Enter (Threads 快捷鍵)
        try:
            await page.keyboard.press("Control+Enter")
            await _s(3, 5)
            return True
        except Exception:
            pass

        return False

    async def _try_get_thread_url(self, page: Page) -> str:
        """嘗試取得剛發出的串文 URL"""
        try:
            # Threads URL 格式: threads.net/@username/post/XXXXX
            # 發文後通常會跳轉到個人頁面或回首頁
            current_url = page.url
            if "/post/" in current_url:
                return current_url.split("?")[0]

            # 嘗試找自己的最新貼文連結
            selectors = [
                'a[href*="/post/"]',
                'a[href*="/t/"]',
            ]
            for sel in selectors:
                links = page.locator(sel).all()
                for link in links:
                    href = await link.get_attribute("href") or ""
                    if "/post/" in href:
                        return f"https://www.threads.net{href.split('?')[0]}"
        except Exception:
            pass
        return ""

    # ════════════════════════════════════════════
    #  公開 API
    # ════════════════════════════════════════════

    async def post_thread(
        self,
        page: Page,
        content: str,
        image_paths: Optional[list[str]] = None,
    ) -> dict:
        """發布一篇 Threads 貼文

        Args:
            page: Playwright Page（已載入 cookie）
            content: 貼文內容
            image_paths: 圖片路徑列表（可選）

        Returns:
            {"success": bool, "post_url": str, "error": str|None}
        """
        if not content.strip():
            return {"success": False, "error": "文案不能為空", "post_url": ""}

        try:
            # 1. 確認登入
            logged_in = await self._ensure_logged_in(page)
            if not logged_in:
                await self._screenshot(page, "not_logged_in")
                return {"success": False, "error": "未登入 Threads，請先在瀏覽器中登入", "post_url": ""}

            # 2. 點擊發文按鈕
            clicked = await self._click_new_thread_button(page)
            if not clicked:
                # 試試直接導航到 compose URL
                await page.goto("https://www.threads.net/compose/post", wait_until="domcontentloaded", timeout=15000)
                await _s(2, 4)

            # 3. 填入文字
            text = content + _random_hashtag()
            filled = await self._fill_thread_text(page, text)
            if not filled:
                await self._screenshot(page, "no_editor")
                return {"success": False, "error": "找不到文字編輯器", "post_url": ""}

            # 4. 上傳圖片（如果有）
            if image_paths:
                await self._upload_images(page, image_paths)
                await _s(1, 2)

            # 5. 點擊發布
            published = await self._click_post_button(page)
            if not published:
                await self._screenshot(page, "no_post_btn")
                return {"success": False, "error": "找不到發布按鈕", "post_url": ""}

            # 6. 取得貼文 URL
            post_url = await self._try_get_thread_url(page)

            log("THREADS", "post", f"✅ 發文成功" + (f" | {post_url}" if post_url else ""), "✅")
            return {"success": True, "post_url": post_url, "error": None}

        except Exception as e:
            await self._screenshot(page, "error")
            return {"success": False, "error": str(e)[:200], "post_url": ""}

    async def post_multiple(
        self,
        page: Page,
        posts: list[dict],
        delay_range: tuple = (60, 300),
    ) -> list[dict]:
        """批次發布多篇貼文

        Args:
            page: Playwright Page
            posts: [{"content": str, "images": [str]}, ...]
            delay_range: 每篇間的隨機延遲 (min_seconds, max_seconds)

        Returns:
            [{"success": bool, ...}, ...]
        """
        results = []
        for i, post_data in enumerate(posts):
            if i > 0:
                delay = random.randint(*delay_range)
                log("THREADS", "schedule", f"等待 {delay}s 後發下一篇...", "⏳")
                await asyncio.sleep(delay)

            result = await self.post_thread(
                page,
                content=post_data.get("content", ""),
                image_paths=post_data.get("images"),
            )
            results.append(result)

        return results
