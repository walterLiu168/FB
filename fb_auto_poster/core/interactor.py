"""自動留言互動引擎"""
import random

from playwright.async_api import Page

from utils.randomizer import short_delay, random_delay


_COMMENT_TEMPLATES = [
    "請問還有嗎？",
    "已私訊～",
    "想了解一下價錢",
    "+1 謝謝",
    "有興趣！",
    "方便私訊嗎？",
    "請問在哪個地區？",
    "太划算了！",
    "已分享～",
    "想知道更多細節",
    "讚！",
    "推一個",
]


class Interactor:
    """FB 自動留言互動引擎"""

    async def like_post(self, page: Page, post_url: str) -> dict:
        """在指定貼文按讚（最佳努力）"""
        try:
            await page.goto(post_url, wait_until="domcontentloaded", timeout=60000)
            await short_delay(3, 6)

            # FB 讚的按鈕在不同版型/語言會變，這裡用多組 selector 兼容
            selectors = [
                'div[aria-label="讚"][role="button"]',
                'div[aria-label="Like"][role="button"]',
                'div[aria-label*="讚"][role="button"]',
                'div[aria-label*="Like"][role="button"]',
                'span:has-text("讚")',
                'span:has-text("Like")',
            ]

            for sel in selectors:
                try:
                    btn = page.locator(sel).first
                    if await btn.is_visible(timeout=1500):
                        await btn.click(force=True, timeout=3000)
                        await short_delay(1, 2)
                        return {"success": True}
                except Exception:
                    continue

            return {"success": False, "error": "找不到讚按鈕（可能已按過或版型改動）"}
        except Exception as e:
            return {"success": False, "error": str(e)[:150]}

    async def comment_on_post(self, page: Page, post_url: str, comment: str = ""):
        """在指定貼文留言"""
        if not comment:
            comment = random.choice(_COMMENT_TEMPLATES)
        try:
            await page.goto(post_url, wait_until="domcontentloaded", timeout=60000)
            await short_delay(3, 6)

            comment_box = page.locator('div[aria-label*="留言"], div[role="textbox"]').first
            if await comment_box.is_visible():
                await comment_box.click()
                await short_delay(1, 3)
                await comment_box.fill(comment)
                await short_delay(1, 3)
                await page.keyboard.press("Enter")
                await short_delay(2, 4)
                return {"success": True, "comment": comment}
            return {"success": False, "error": "找不到留言框"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def comment_on_hot_posts(self, page: Page, count: int = 3):
        """在熱門貼文自動留言"""
        commented = 0
        try:
            await page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=60000)
            await short_delay(3, 6)

            for _ in range(count):
                try:
                    comment_box = page.locator('div[aria-label*="留言"], div[role="textbox"]').first
                    if await comment_box.is_visible():
                        await comment_box.click()
                        await short_delay(1, 3)
                        comment = random.choice(_COMMENT_TEMPLATES)
                        await comment_box.fill(comment)
                        await short_delay(1, 3)
                        await page.keyboard.press("Enter")
                        commented += 1
                        await random_delay(30, 60)
                except Exception:
                    continue
        except Exception:
            pass
        return commented
