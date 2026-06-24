"""Instagram 自動發文引擎 — Playwright 瀏覽器自動化

Instagram 在 2026 年僅對 Business/Creator 帳號開放 Graph API。
個人帳號必須使用瀏覽器自動化。本模組實現完整的 IG 發文流程：

  支援功能:
    - 單圖發文
    - 多圖輪播 (Carousel)
    - Reels 短影片 (未來)
    - 自動 Hashtag
    - 人化延遲（防 ban）
    - Session 持久化（storageState）

  防檢測策略:
    - 使用真實 Chrome (channel="chrome")，非 Chromium
    - 禁用 automationControlled flag
    - 隨機化動作延遲
    - 自然打字速度
    - 非 headless 模式

  工作流程:
    1. 載入 IG Cookie / storageState → 確認登入
    2. 點擊 + 建立新貼文
    3. 上傳圖片 (file chooser 攔截)
    4. 填寫 caption + hashtags
    5. 點擊分享
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

async def _human_delay(lo=1.0, hi=3.0):
    """模擬人類操作間隔"""
    await asyncio.sleep(random.uniform(lo, hi))

_IG_HASHTAGS = [
    "\n.\n.\n#日常 #生活 #分享",
    "\n.\n.\n#好物推薦 #必買",
    "\n.\n.\n#ootd #穿搭 #時尚",
    "\n.\n.\n#美食 #吃貨 #推薦",
    "\n.\n.\n#創業 #電商 #副業",
    "\n.\n.\n#教學 #技巧 #實用",
    "\n.\n.\n#心得 #經驗分享",
    "\n.\n.\n#今日份快樂",
    "\n.\n.\n#instagood #photooftheday",
    "\n.\n.\n#trending #viral",
    " ",
    "",
]


def _random_hashtags() -> str:
    return random.choice(_IG_HASHTAGS)


class InstagramPoster:
    """Instagram 發文引擎"""

    def __init__(self):
        self._screenshot_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "data", "debug_screenshots"
        )

    async def _screenshot(self, page: Page, step: str):
        try:
            os.makedirs(self._screenshot_dir, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = os.path.join(self._screenshot_dir, f"ig_{ts}_{step}.png")
            await page.screenshot(path=path, full_page=False)
        except Exception:
            pass

    async def _ensure_logged_in(self, page: Page) -> bool:
        """確認已登入 Instagram"""
        await page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=30000)
        await _s(2, 4)

        # 檢查是否已登入
        logged_in_signals = [
            'svg[aria-label="Home"]',
            'a[href="/direct/inbox/"]',
            'svg[aria-label="New post"]',
            'svg[aria-label="Search"]',
            'span:has-text("Home")',
            '[data-testid="navbar"]',
        ]

        for sel in logged_in_signals:
            try:
                el = page.locator(sel).first
                if await el.count() > 0:
                    return True
            except Exception:
                continue

        # 檢查是否在登入頁面
        try:
            login_btn = page.locator('text="Log in"').first
            if await login_btn.count() > 0:
                log("IG", "auth", "偵測到登入頁面，需要手動登入", "🔑")
                return False
        except Exception:
            pass

        # 不確定 → 假設 OK
        return True

    async def _click_new_post_button(self, page: Page) -> bool:
        """點擊 IG 建立新貼文按鈕"""
        selectors = [
            'svg[aria-label="New post"]',
            'a[href="#"] svg[aria-label="New post"]',
            'div[role="button"]:has(svg[aria-label="New post"])',
            '[data-testid="create-post-button"]',
            'a[href="/create/select/"]',
            'svg[aria-label="Create"]',
        ]

        for sel in selectors:
            try:
                el = page.locator(sel).first
                if await el.count() > 0:
                    await el.click(force=True, timeout=3000)
                    await _s(1, 3)
                    return True
            except Exception:
                continue

        # 直接導航到上傳頁面
        try:
            await page.goto("https://www.instagram.com/create/select/",
                           wait_until="domcontentloaded", timeout=15000)
            await _s(2, 4)
            return True
        except Exception:
            pass

        return False

    async def _upload_images(self, page: Page, image_paths: list[str]) -> bool:
        """上傳圖片到 IG"""
        if not image_paths:
            return False

        log("IG", "post", f"上傳 {len(image_paths)} 張圖片...", "📷")
        await _s(1, 3)

        # 方法 1: 直接找 file input
        for attempt in range(3):
            try:
                fi = page.locator('input[type="file"]').first
                if await fi.count() > 0:
                    await fi.set_input_files(image_paths, timeout=10000)
                    await _s(3, 6)
                    log("IG", "post", f"✅ 圖片上傳成功 ({len(image_paths)} 張)", "📷")
                    return True
            except Exception:
                await _s(1, 2)

        # 方法 2: 點擊觸發按鈕 + file chooser 攔截
        trigger_selectors = [
            'button:has-text("Select from computer")',
            'div[role="button"]:has-text("Select from computer")',
            'text="Select from computer"',
        ]

        for sel in trigger_selectors:
            try:
                btn = page.locator(sel).first
                if await btn.is_visible(timeout=2000):
                    async with page.expect_file_chooser(timeout=8000) as fc:
                        await btn.click(force=True, timeout=3000)
                    chooser = await fc.value
                    await chooser.set_files(image_paths)
                    await _s(3, 6)
                    log("IG", "post", f"✅ file chooser 攔截成功 ({len(image_paths)} 張)", "📷")
                    return True
            except Exception:
                continue

        log("IG", "post", "⚠️ 圖片上傳失敗", "⚠️")
        return False

    async def _fill_caption(self, page: Page, caption: str) -> bool:
        """填入 IG 貼文 caption"""
        await _s(1, 3)

        # IG caption 通常是 textarea 或 contenteditable div
        caption_selectors = [
            'textarea[aria-label*="Write a caption"]',
            'textarea[aria-label*="caption" i]',
            'textarea[placeholder*="Write a caption"]',
            'div[contenteditable="true"][role="textbox"]',
            'div[aria-label*="Write a caption"]',
            '[data-testid="caption-textarea"]',
        ]

        for sel in caption_selectors:
            try:
                el = page.locator(sel).first
                if await el.count() > 0 and await el.is_visible(timeout=2000):
                    await el.click(timeout=2000)
                    await _s(0.5, 1)
                    await el.fill(caption)
                    return True
            except Exception:
                continue

        # 鍵盤 fallback
        try:
            await page.keyboard.press("Tab")
            await _s(0.3, 0.6)
            for char in caption:
                await page.keyboard.type(char, delay=random.randint(20, 60))
            return True
        except Exception:
            pass

        return False

    async def _click_share(self, page: Page) -> bool:
        """點擊 IG Share 按鈕"""
        share_selectors = [
            'div[role="button"]:has-text("Share")',
            'button:has-text("Share")',
            'div:has-text("Share"):not(:has-text("story"))',
            '[data-testid="share-button"]',
            'div[role="button"]:has-text("Next")',
        ]

        for sel in share_selectors:
            try:
                btn = page.locator(sel).last
                if await btn.is_visible(timeout=2000):
                    await btn.click(force=True, timeout=3000)
                    await _s(2, 5)
                    return True
            except Exception:
                continue

        return False

    async def _handle_crop_screen(self, page: Page) -> bool:
        """處理 IG 裁切/濾鏡畫面 (點擊 Next)"""
        next_selectors = [
            'div[role="button"]:has-text("Next")',
            'button:has-text("Next")',
            'svg[aria-label="Next"]',
        ]

        for sel in next_selectors:
            try:
                btn = page.locator(sel).first
                if await btn.is_visible(timeout=2000):
                    await btn.click(force=True, timeout=3000)
                    await _s(1, 3)
                    return True
            except Exception:
                continue
        return True  # No crop screen is also fine

    async def _handle_edit_screen(self, page: Page) -> bool:
        """處理編輯畫面 (可能有多個 Next/Share)"""
        # IG 建立流程: Select → Crop → Edit → Share
        # 每個步驟可能都有 Next
        for _ in range(3):  # 最多 try 3 次
            try:
                next_btn = page.locator('div[role="button"]:has-text("Next")').first
                if await next_btn.count() > 0 and await next_btn.is_visible(timeout=1000):
                    await next_btn.click(force=True, timeout=3000)
                    await _s(1, 3)
            except Exception:
                break

        # 最後找 Share
        return await self._click_share(page)

    # ════════════════════════════════════════════
    #  公開 API
    # ════════════════════════════════════════════

    async def post_photo(
        self,
        page: Page,
        caption: str,
        image_path: str,
    ) -> dict:
        """發布單張圖片到 IG

        Args:
            page: Playwright Page（已載入 IG cookie）
            caption: 貼文說明
            image_path: 圖片路徑

        Returns:
            {"success": bool, "post_url": str, "error": str|None}
        """
        return await self.post_carousel(page, caption, [image_path])

    async def post_carousel(
        self,
        page: Page,
        caption: str,
        image_paths: list[str],
    ) -> dict:
        """發布多圖輪播到 IG

        Args:
            page: Playwright Page
            caption: 貼文說明
            image_paths: 圖片路徑列表 (最多 10 張)

        Returns:
            {"success": bool, "post_url": str, "error": str|None}
        """
        if not caption.strip():
            return {"success": False, "error": "文案不能為空", "post_url": ""}

        if not image_paths:
            return {"success": False, "error": "沒有圖片（IG 不支援純文字貼文）", "post_url": ""}

        try:
            # 1. 確認登入
            logged_in = await self._ensure_logged_in(page)
            if not logged_in:
                await self._screenshot(page, "not_logged_in")
                return {"success": False, "error": "未登入 Instagram", "post_url": ""}

            # 2. 點擊新增貼文
            clicked = await self._click_new_post_button(page)
            if not clicked:
                await self._screenshot(page, "no_new_post_btn")
                return {"success": False, "error": "找不到發文按鈕", "post_url": ""}

            # 3. 上傳圖片
            uploaded = await self._upload_images(page, image_paths)
            if not uploaded:
                await self._screenshot(page, "upload_failed")
                return {"success": False, "error": "圖片上傳失敗", "post_url": ""}

            # 4. 處理裁切畫面（點 Next）
            await _s(1, 2)
            await self._handle_crop_screen(page)

            # 5. 處理編輯畫面（再點 Next）
            await _s(1, 2)
            await self._handle_edit_screen(page)

            # 6. 填入 caption
            full_caption = caption + _random_hashtags()
            await self._fill_caption(page, full_caption)
            await _s(0.5, 1)

            # 7. 點擊 Share
            shared = await self._click_share(page)
            if not shared:
                await self._screenshot(page, "no_share")
                return {"success": False, "error": "找不到 Share 按鈕", "post_url": ""}

            await _s(3, 6)

            log("IG", "post", "✅ IG 發文成功", "✅")
            return {"success": True, "post_url": page.url, "error": None}

        except Exception as e:
            await self._screenshot(page, "error")
            return {"success": False, "error": str(e)[:200], "post_url": ""}

    async def post_multiple(
        self,
        page: Page,
        posts: list[dict],
        delay_range: tuple = (300, 900),
    ) -> list[dict]:
        """批次發布多篇 IG 貼文

        IG 嚴格限制頻率 → 建議至少間隔 5-15 分鐘。
        """
        results = []
        for i, p in enumerate(posts):
            if i > 0:
                delay = random.randint(*delay_range)
                log("IG", "schedule", f"等待 {delay}s 後發下一篇...", "⏳")
                await asyncio.sleep(delay)

            images = p.get("images", [])
            if len(images) == 1:
                r = await self.post_photo(page, p.get("caption", ""), images[0])
            else:
                r = await self.post_carousel(page, p.get("caption", ""), images)
            results.append(r)

        return results
