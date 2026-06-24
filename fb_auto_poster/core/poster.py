"""發文引擎 — www.facebook.com 主頁面模式 (file chooser 攔截)

使用 Playwright 的 page.expect_file_chooser() 攔截 OS 檔案對話框：
- 點擊 Add to your post / Photo 按鈕時系統會彈出檔案選擇器
- Playwright 攔截並直接設定檔案，完全繞過對話框

工作流程：
1. 開啟 facebook.com
2. 點擊「在想什麼」
3. 在對話框中輸入文字
4. 點擊 Photo 按鈕 → Playwright 攔截 file chooser → 直接設圖片
5. 點擊 Post
"""
import os
import asyncio
import random
from datetime import datetime
from playwright.async_api import Page

from utils.logger import log


async def _s(lo=0.5, hi=1.5):
    await asyncio.sleep(random.uniform(lo, hi))


async def _dl(lo=60, hi=900):
    """社團發文間隔：1 ~ 15 分鐘隨機（避免 FB ban）"""
    await asyncio.sleep(random.uniform(lo, hi))


def _rs() -> str:
    tags = [
        f"\n\n#{''.join(random.choice('abcdefghijklmnopqrstuvwxyz0123456789') for _ in range(6))}",
        f"\n.\n.",
        f"\n{' '.join(random.sample(['🔥','💥','⚡','📌','✅'], k=random.randint(1,3)))}",
        f"\n({random.choice(['今日限定','限時優惠','熱銷中','搶手物件','即將售罄'])})",
    ]
    return random.choice(tags)


class Poster:
    """FB 發文引擎 — file chooser 攔截模式"""

    async def _try_get_post_url(self, page: Page) -> str:
        """嘗試取得剛發出的貼文 permalink（最佳努力）

        FB 版型常改，這裡只做「抓得到就存，抓不到就留空」。
        """
        # 1) Toast / 提示條上的「查看貼文 / View post」
        selectors = [
            'a:has-text("查看貼文")',
            'a:has-text("View post")',
            'a[role="link"]:has-text("查看貼文")',
            'a[role="link"]:has-text("View post")',
        ]
        for sel in selectors:
            try:
                a = page.locator(sel).first
                if await a.is_visible(timeout=1500):
                    href = await a.get_attribute("href")
                    if href and ("facebook.com" in href):
                        return href.split("?")[0]
            except Exception:
                continue

        # 2) 動態牆第一篇貼文的時間戳連結（可能不一定是你剛發的）
        # 只當作 fallback，避免完全沒有 URL。
        try:
            for sel in [
                'a[href*="/posts/"]',
                'a[href*="permalink.php"]',
                'a[href*="story_fbid"]',
            ]:
                a = page.locator(sel).first
                if await a.count() > 0:
                    href = await a.get_attribute("href")
                    if href and ("facebook.com" in href):
                        return href.split("?")[0]
        except Exception:
            pass

        return ""

    @staticmethod
    async def _screenshot(page: Page, step: str):
        try:
            d = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "debug_screenshots")
            os.makedirs(d, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            await page.screenshot(path=os.path.join(d, f"{ts}_{step}.png"), full_page=False)
        except Exception:
            pass

    async def _post_to_wall(
        self, page: Page, text: str, image_paths: list[str] = None
    ) -> dict:
        """在 www.facebook.com 發文（含圖片）"""
        # ── 1. 載入 FB ──
        await page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=60000)
        await _s(3, 6)

        if await page.locator('input[name="email"]').count() > 0:
            await self._screenshot(page, "not_logged_in")
            return {"success": False, "error": "未登入"}

        # ── 2. 點擊「在想什麼」 ──
        clicked = await self._click_status_box(page)
        if not clicked:
            await self._screenshot(page, "no_status_box")
            return {"success": False, "error": "找不到狀態框"}
        await _s(2, 4)

        # ── 3. 輸入文字 ──
        filled = await self._fill_editor(page, text)
        if not filled:
            await self._screenshot(page, "no_editor")
            return {"success": False, "error": "找不到編輯器"}
        await _s(1, 2)

        # ── 4. 上傳圖片（Playwright file chooser 攔截） ──
        if image_paths:
            await self._upload_via_chooser(page, image_paths)

        # ── 5. 點擊發布 ──
        await _s(1, 2)
        published = await self._click_publish(page)
        if not published:
            await self._screenshot(page, "no_publish")
            return {"success": False, "error": "找不到發布按鈕"}

        await _s(3, 6)
        log("POST", "wall", "✅ 發文成功", "✅")
        post_url = await self._try_get_post_url(page)
        return {"success": True, "post_url": post_url}

    async def _click_status_box(self, page: Page) -> bool:
        """點擊主頁面上的「在想什麼」狀態框"""
        # 先試 CSS 選擇器（最準確）
        selectors = [
            'span:has-text("在想什麼")',
            'span:has-text("在想什麼，")',
            'span:has-text("What\'s on your mind")',
        ]
        for sel in selectors:
            try:
                el = page.locator(sel).first
                if await el.count() > 0:
                    # 往上找到 clickable parent
                    parent = page.locator(sel).first.locator('xpath=ancestor::*[@role="button" or @tabindex="0"][1]')
                    if await parent.count() == 0:
                        parent = el
                    await parent.click(force=True, timeout=3000)
                    return True
            except Exception:
                continue

        # 降級到 JS walker — 但要避開 Messenger
        try:
            result = await page.evaluate("""
                () => {
                    const spans = document.querySelectorAll('span');
                    for (const s of spans) {
                        const t = s.textContent.trim();
                        if (t.includes('mind') || t.includes('在想') || t.includes('Create a post')) {
                            // Make sure this is NOT inside Messenger
                            const inDialog = s.closest('[role="dialog"]');
                            if (inDialog) continue; // skip Messenger/chat dialogs
                            
                            const clickable = s.closest('[role="button"], a[tabindex="0"], div[tabindex="0"]');
                            if (clickable) {
                                clickable.click();
                                return 'clicked_btn';
                            }
                            s.click();
                            return 'clicked_span';
                        }
                    }
                    return 'not_found';
                }
            """)
            return str(result).startswith('clicked')
        except Exception:
            return False

    async def _fill_editor(self, page: Page, text: str) -> bool:
        """在對話框中填入文字（contenteditable div）"""
        await _s(1, 3)

        # 方法 1: contenteditable div
        editors = await page.locator('[contenteditable="true"]').all()
        for ed in editors:
            try:
                if await ed.is_visible(timeout=1000):
                    await ed.click(force=True, timeout=2000)
                    await _s(0.3, 0.8)
                    await ed.fill(text)
                    return True
            except Exception:
                continue

        # 方法 2: JS execCommand
        try:
            found = await page.evaluate("""(text) => {
                const editors = document.querySelectorAll('[contenteditable="true"]');
                for (const e of editors) {
                    if (e.offsetParent !== null) {
                        e.focus();
                        document.execCommand('insertText', false, text);
                        return true;
                    }
                }
                return false;
            }""", text)
            return bool(found)
        except Exception:
            return False

    async def _upload_via_chooser(self, page: Page, image_paths: list[str]):
        """使用 Playwright file chooser 攔截上傳圖片

        Playwright 會攔截 OS 的檔案選擇對話框，
        點擊圖片按鈕時直接設定檔案，完全不碰 UI 選單。
        """
        log("POST", "wall", f"上傳 {len(image_paths)} 張圖片...", "📷")

        # 先找對話框中的圖片按鈕
        # FB 的按鈕可能是 aria-label="Photo/video" 或就是一個小 SVG icon
        photo_selectors = [
            '[role="dialog"] div[aria-label*="Photo" i][role="button"]',
            '[role="dialog"] div[aria-label*="照片"][role="button"]',
            '[role="dialog"] div[aria-label*="video" i][role="button"]',
            '[aria-label*="Photo/video" i]',
            '[aria-label*="photo" i]',
            # "Add to your post" toolbar 內第一個按鈕（通常是圖片）
        ]

        clicked_photo = False
        for sel in photo_selectors:
            try:
                btn = page.locator(sel).first
                if await btn.is_visible(timeout=1000):
                    # 使用 expect_file_chooser 攔截！
                    async with page.expect_file_chooser() as fc:
                        await btn.click(force=True, timeout=3000)
                    try:
                        file_chooser = await fc.value
                        await file_chooser.set_files(image_paths)
                        log("POST", "wall", f"✅ file chooser 攔截成功 ({len(image_paths)} 張)", "📷")
                        clicked_photo = True
                        break
                    except Exception as e:
                        log("POST", "wall", f"chooser set_files failed: {e}", "⚠️")
                        # btn clicked but no chooser → 可能是 FB 彈出了子選單而非檔案對話框
                        # 關閉子選單並繼續
            except Exception:
                continue

        if not clicked_photo:
            # JS: 找對話框中所有帶 SVG 的按鈕（通常照片/影片 icon）
            try:
                result = await page.evaluate("""
                    () => {
                        const dialog = document.querySelector('[role="dialog"]');
                        if (!dialog) return 'no_dialog';
                        
                        // Find small icon buttons (likely photo/video/tag/feeling)
                        const btns = Array.from(dialog.querySelectorAll('div[role="button"]'));
                        // Try clicking each icon button and check for file chooser
                        for (const btn of btns) {
                            const hasSvg = !!btn.querySelector('svg');
                            const w = btn.offsetWidth || 0;
                            if (hasSvg && w < 65) {
                                btn.click();
                                return 'clicked_svg';
                            }
                        }
                        return 'no_svg_btn';
                    }
                """)

                if str(result) == 'clicked_svg':
                    # Wait for any sub-menu to appear, then bypass it
                    await _s(1, 2)
                    # Check if a menu/popover appeared
                    menus = await page.locator('[role="menu"], [role="listbox"]').all()
                    if menus:
                        # Press Escape to close sub-menu
                        await page.keyboard.press("Escape")
                        await _s(0.5, 1)

                    # Now try file chooser interception again
                    try:
                        async with page.expect_file_chooser(timeout=5000) as fc:
                            # Click the SVG button again
                            await page.evaluate("""
                                () => {
                                    const dialog = document.querySelector('[role="dialog"]');
                                    if (!dialog) return;
                                    const btns = dialog.querySelectorAll('div[role="button"]');
                                    for (const b of btns) {
                                        if (b.querySelector('svg') && b.offsetWidth < 65) {
                                            b.click();
                                            break;
                                        }
                                    }
                                }
                            """)
                        file_chooser = await fc.value
                        await file_chooser.set_files(image_paths)
                        log("POST", "wall", f"✅ 第二輪 file chooser 成功 ({len(image_paths)} 張)", "📷")
                    except Exception:
                        log("POST", "wall", "file chooser 攔截失敗，嘗試直接 file input", "⚠️")
                else:
                    log("POST", "wall", f"JS click result: {result}", "⚠️")
            except Exception as e:
                log("POST", "wall", f"JS approach failed: {e}", "⚠️")

        # 最終保險：直接找 file input（可能已出現或一直是 hidden）
        if not clicked_photo:
            for attempt in range(3):
                try:
                    file_input = page.locator('input[type="file"]').first
                    if await file_input.count() > 0:
                        await file_input.set_input_files(image_paths)
                        log("POST", "wall", f"✅ 直接 file input 上傳成功 ({len(image_paths)} 張)", "📷")
                        break
                except Exception:
                    await _s(1, 2)

        await _s(3, 6)

    async def _click_publish(self, page: Page) -> bool:
        for sel in [
            'div[role="button"]:has-text("Post"):not(:has-text("Add"))',
            'div[role="button"]:has-text("發佈")',
            'div[role="dialog"] div[role="button"]:has-text("Post")',
            'div[role="dialog"] div[aria-label="Post"]',
            'div[aria-label="Post"][role="button"]',
            '[aria-label*="Post" i][role="button"]:not(:has-text("Add"))',
            'div[aria-label*="發佈"][role="button"]',
        ]:
            try:
                btn = page.locator(sel).first
                if await btn.count() > 0:
                    await btn.click(force=True, timeout=3000)
                    return True
            except Exception:
                continue
        return False

    # ── 發文到社團 ──
    async def _post_to_group(
        self, page: Page, group_name: str, text: str, image_paths: list[str] = None
    ) -> dict:
        """發文到指定社團（搜尋 → 進入 → 發文）

        如果 group_name 是 URL（含 facebook.com/groups/），直接進入。
        否則搜尋社團名稱後點擊第一個結果。
        """
        try:
            # ── 判斷是 URL 還是名稱 ──
            if "facebook.com/groups/" in group_name:
                # 直接進入
                await page.goto(group_name, wait_until="domcontentloaded", timeout=45000)
                log("POST", "group", f"直接進入社團: {group_name[:60]}", "🔗")
            else:
                # 搜尋社團
                encoded = group_name.replace(" ", "+")
                await page.goto(
                    f"https://www.facebook.com/search/groups/?q={encoded}",
                    wait_until="domcontentloaded", timeout=30000
                )
                await _s(2, 4)

                # 找社團連結 — 優先精確匹配名稱
                found = False
                for sel in [
                    f'a:has-text("{group_name}")',
                    f'a[aria-label*="{group_name}"]',
                    'a[href*="/groups/"]',
                ]:
                    try:
                        links = page.locator(sel).all()
                        if not links:
                            continue
                        # 選第一個可見的
                        for link in links:
                            if await link.is_visible(timeout=1500):
                                href = await link.get_attribute("href", timeout=1000) or ""
                                if "/groups/" in href:
                                    await link.click(force=True)
                                    found = True
                                    break
                        if found:
                            break
                    except Exception:
                        continue

                if not found:
                    await self._screenshot(page, "group_not_found")
                    return {"success": False, "error": f"找不到社團: {group_name}"}

            await _s(3, 6)

            # ── 在社團頁面找發文框 ──
            clicked = await self._click_status_box(page)

            if not clicked:
                # 有些社團需要在「討論」分頁才能發文
                disc_tabs = [
                    'a:has-text("討論")',
                    'a:has-text("Discussion")',
                    'div[role="tab"]:has-text("討論")',
                    'div[role="button"]:has-text("討論")',
                ]
                for tab_sel in disc_tabs:
                    try:
                        tab = page.locator(tab_sel).first
                        if await tab.is_visible(timeout=2000):
                            await tab.click(force=True)
                            await _s(2, 4)
                            clicked = await self._click_status_box(page)
                            if clicked:
                                break
                    except Exception:
                        continue

            if not clicked:
                # 最後手段：直接在社團 URL 後加 #
                current = page.url
                if "?" in current:
                    compose_url = current + "&view=composer"
                else:
                    compose_url = current.rstrip("/") + "/?view=composer"
                log("POST", "group", f"嘗試 compose URL: {compose_url[:60]}", "🔗")
                # Not wrapping in try/except since we'll just continue with current page

            await _s(2, 4)
            await self._fill_editor(page, text)
            await _s(1, 2)

            if image_paths:
                await self._upload_via_chooser(page, image_paths)

            published = await self._click_publish(page)
            if published:
                await _s(3, 6)
                log("POST", "group", f"社團 {group_name} 發文成功 ✅", "✅")
                post_url = await self._try_get_post_url(page)
                return {"success": True, "post_url": post_url}
            else:
                await self._screenshot(page, "group_no_publish")
                return {"success": False, "error": "找不到發布按鈕"}

        except Exception as e:
            await self._screenshot(page, "group_error")
            return {"success": False, "error": str(e)}

    # ── 公開 API ──
    async def post_general(
        self, page, content, image_paths=None, groups=None
    ) -> dict:
        if not content.strip():
            return {"success": False, "error": "文案不能為空"}

        text = content + _rs()
        results = {"success": True, "posted_to": []}

        if groups:
            for group in groups:
                r = await self._post_to_group(page, group, text, image_paths)
                results["posted_to"].append({"group": group, **r})
                if r.get("success"):
                    await _dl(60, 180)
        else:
            r = await self._post_to_wall(page, text, image_paths)
            results["posted_to"].append({"group": "個人頁面", **r})

        return results

    async def post_marketplace(
        self, page, title, price, location, description, image_paths=None
    ) -> dict:
        try:
            await page.goto("https://www.facebook.com/marketplace/create",
                           wait_until="domcontentloaded", timeout=45000)
            await _s(3, 6)

            for sel in ['input[aria-label*="Title" i]', 'input[aria-label*="標題"]']:
                try:
                    inp = page.locator(sel).first
                    if await inp.is_visible(timeout=1000):
                        await inp.fill(title)
                        break
                except Exception:
                    continue

            for sel in ['input[aria-label*="Price" i]', 'input[aria-label*="價格"]']:
                try:
                    inp = page.locator(sel).first
                    if await inp.is_visible(timeout=1000):
                        await inp.fill(str(price))
                        break
                except Exception:
                    continue

            await self._fill_editor(page, description)
            await _s(1, 2)

            if image_paths:
                await self._upload_via_chooser(page, image_paths)

            if not await self._click_publish(page):
                await self._screenshot(page, "marketplace_no_publish")
                return {"success": False, "error": "找不到發布按鈕"}

            await _s(3, 6)
            return {"success": True}
        except Exception as e:
            await self._screenshot(page, "marketplace_error")
            return {"success": False, "error": str(e)}
