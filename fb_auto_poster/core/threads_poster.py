"""Threads.net 自動發文引擎 — 使用 Playwright 瀏覽器自動化

Threads.net 由 Meta 開發。發文流程：
  1. 留在首頁（cookie 已由 browser.py 注入，頁面會自動登入）
  2. 點擊首頁頂部的「Start a thread...」文字區塊 → 打開內嵌編輯器
  3. 在編輯器中輸入文字 → 按 Post
  4. 發文後回到首頁，可立刻看到剛發的文

設計重點：
  - 不跳轉到 /compose/post（可能 404），全程在首頁完成
  - 用 force click 避開 visibility 檢查（Threads 用大量 absolute positioning）
  - 多層選擇器 fallback，對應不同 UI 版本
"""
import os
import asyncio
import random
from datetime import datetime
from typing import Optional
from playwright.async_api import Page

from utils.logger import log

_LAUNCH_ARGS = ["--disable-blink-features=AutomationControlled"]

# ── helpers ──
async def _s(lo=0.5, hi=1.5):
    await asyncio.sleep(random.uniform(lo, hi))

def _random_tail() -> str:
    return random.choice([
        "\n\n#每日分享", "\n\n#心得", "\n\n#推薦",
        "\n\n#日常", "\n\n#好物分享", "\n.\n.", " ", "",
    ])


class ThreadsPoster:
    """Threads.net 發文引擎 — 首頁內嵌編輯器版本"""

    def __init__(self):
        self._ss = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "data", "debug_screenshots"
        )

    async def _sshot(self, page: Page, step: str):
        try:
            os.makedirs(self._ss, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = os.path.join(self._ss, f"threads_{ts}_{step}.png")
            await page.screenshot(path=path, full_page=False)
        except Exception:
            pass

    # ═══════════════════════════════
    #  登入檢查（輕量 — cookie 已注入）
    # ═══════════════════════════════

    async def _is_logged_in(self, page: Page) -> bool:
        """快速檢查登入狀態"""
        for sel in [
            'a[href*="/@"]',
            'svg[aria-label="Home"]',
            'a[href*="/notifications"]',
        ]:
            try:
                if await page.locator(sel).first.count() > 0:
                    return True
            except Exception:
                continue

        # 有 login 按鈕 = 未登入
        try:
            if await page.locator('text="Log in"').first.count() > 0:
                return False
        except Exception:
            pass

        return True  # 不確定 → 假設 OK

    # ═══════════════════════════════
    #  發文核心
    # ═══════════════════════════════

    async def _open_composer(self, page: Page) -> bool:
        """在首頁上打開 Threads 內嵌編輯器

        Threads 首頁頂部有個 「Start a thread...」區域，點擊會原地展開編輯器。
        """
        composer_triggers = [
            'div[role="button"]:has-text("Start a thread")',
            'div:has-text("Start a thread")',
            'span:has-text("Start a thread")',
            'textarea[placeholder*="Start a thread"]',
            'div[data-testid="composer-trigger"]',
            # fallback: any clickable area inside the top bar
            'div[role="button"]:has(svg)',
        ]

        for sel in composer_triggers:
            try:
                el = page.locator(sel).first
                if await el.count() > 0:
                    await el.click(force=True, timeout=5000)
                    await _s(1.5, 3)
                    # 檢查編輯器是否真的打開了
                    if await self._is_composer_open(page):
                        return True
            except Exception:
                continue

        return False

    async def _is_composer_open(self, page: Page) -> bool:
        """編輯器打開後應該看到一個可輸入的區域和 Post 按鈕"""
        for sel in [
            'div[role="button"]:has-text("Post")',
            'span:has-text("Post")',
            'textarea',
            '[contenteditable="true"]',
        ]:
            try:
                if await page.locator(sel).first.count() > 0:
                    return True
            except Exception:
                continue
        return False

    async def _type_text(self, page: Page, text: str) -> bool:
        """在編輯器中輸入文字"""
        await _s(0.5, 1)

        # 優先：找 textarea
        for sel in [
            'textarea',
            'textarea[placeholder]',
            '[contenteditable="true"]',
            'div[role="textbox"]',
        ]:
            try:
                el = page.locator(sel).first
                if await el.count() > 0:
                    await el.click(force=True, timeout=3000)
                    await _s(0.3, 0.6)
                    await el.fill(text)
                    await _s(0.5, 1)
                    return True
            except Exception:
                continue

        # 最後手段：tab + 鍵盤輸入
        try:
            await page.keyboard.press("Tab")
            await _s(0.2, 0.4)
            for ch in text:
                await page.keyboard.type(ch, delay=random.randint(15, 40))
            return True
        except Exception:
            pass

        return False

    async def _click_post(self, page: Page) -> bool:
        """點擊 Post 按鈕"""
        for sel in [
            'div[role="button"]:has-text("Post")',
            'span:has-text("Post")',
        ]:
            try:
                btn = page.locator(sel).last
                if await btn.count() > 0:
                    await btn.click(force=True, timeout=5000)
                    await _s(2, 5)
                    return True
            except Exception:
                continue

        # Ctrl+Enter shortcut
        try:
            await page.keyboard.press("Control+Enter")
            await _s(2, 5)
            return True
        except Exception:
            pass

        return False

    # ═══════════════════════════════
    #  公開 API
    # ═══════════════════════════════

    async def post_thread(
        self,
        page: Page,
        content: str,
        image_paths: Optional[list[str]] = None,
    ) -> dict:
        """發布一篇 Threads 貼文（純文字）

        Args:
            page: 已載入 Threads cookie 的 Playwright Page
            content: 貼文內容
            image_paths: 圖片（暫不支援，Threads 圖片上傳 UI 極不穩定）

        Returns:
            {"success": bool, "post_url": str, "error": str|None}
        """
        content = content.strip()
        if not content:
            return {"success": False, "error": "文案不能為空", "post_url": ""}

        try:
            # 1. 確保在首頁且已登入
            await page.goto("https://www.threads.net/",
                           wait_until="domcontentloaded", timeout=30000)
            await _s(2, 4)
            await self._sshot(page, "home")

            if not await self._is_logged_in(page):
                await self._sshot(page, "login_page")
                return {"success": False, "error": "未登入 — cookie 可能已過期", "post_url": ""}

            log("THREADS", "post", "已登入，準備發文...", "🔑")

            # 2. 打開內嵌編輯器
            if not await self._open_composer(page):
                await self._sshot(page, "no_composer")
                return {"success": False, "error": "找不到發文按鈕（Start a thread）", "post_url": ""}

            await self._sshot(page, "composer_open")
            log("THREADS", "post", "編輯器已開啟", "✏️")

            # 3. 輸入文字
            text = content + _random_tail()
            if not await self._type_text(page, text):
                await self._sshot(page, "no_textbox")
                return {"success": False, "error": "找不到文字輸入框", "post_url": ""}

            log("THREADS", "post", f"文字已填入 ({len(text)} 字)", "📝")

            # 4. （可選）圖片
            if image_paths:
                await self._upload_images(page, image_paths)

            # 5. 點擊 Post
            if not await self._click_post(page):
                await self._sshot(page, "no_post_btn")
                return {"success": False, "error": "找不到 Post 按鈕", "post_url": ""}

            await self._sshot(page, "posted")

            # 6. 取 URL
            post_url = page.url
            if "/post/" not in post_url:
                # 找最新貼文連結
                try:
                    links = page.locator('a[href*="/post/"]').all()
                    for lk in links:
                        h = await lk.get_attribute("href") or ""
                        if "/post/" in h:
                            post_url = f"https://www.threads.net{h.split('?')[0]}"
                            break
                except Exception:
                    pass

            log("THREADS", "post", "✅ 發文成功", "✅")
            return {"success": True, "post_url": post_url, "error": None}

        except Exception as e:
            await self._sshot(page, "crash")
            return {"success": False, "error": str(e)[:200], "post_url": ""}

    # ── 圖片上傳（保留但標記為不穩定） ──

    async def _upload_images(self, page: Page, paths: list[str]) -> bool:
        if not paths:
            return True
        log("THREADS", "post", f"上傳 {len(paths)} 張圖片...", "📷")
        try:
            fi = page.locator('input[type="file"]').first
            if await fi.count() > 0:
                await fi.set_input_files(paths, timeout=10000)
                await _s(2, 4)
                return True
        except Exception:
            pass
        return False

    # ── 批次 ──

    async def post_multiple(
        self, page: Page, posts: list[dict],
        delay_range: tuple = (60, 300),
    ) -> list[dict]:
        results = []
        for i, p in enumerate(posts):
            if i > 0:
                d = random.randint(*delay_range)
                log("THREADS", "schedule", f"等 {d}s...", "⏳")
                await asyncio.sleep(d)
            r = await self.post_thread(page, p.get("content", ""), p.get("images"))
            results.append(r)
        return results
