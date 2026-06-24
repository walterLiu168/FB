"""自動刪文引擎 — 使用 Playwright 刪除過期 FB 貼文（async）"""
import asyncio
import random

from playwright.async_api import Page
from utils.logger import log


class Deleter:
    """FB 貼文刪除引擎"""

    async def delete_by_url(self, page: Page, post_url: str) -> int:
        """精準刪除：直接打開貼文 URL 然後刪除該貼文（最佳努力）

        Returns: deleted(0/1)
        """
        deleted = 0
        try:
            await page.goto(post_url, wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(random.uniform(3, 6))

            option_btn = page.locator(
                'div[aria-label="貼文選項"], '
                'div[aria-label="Post options"], '
                'div[aria-label="Actions for this post"], '
                'div[aria-label*="更多"], '
                'div[aria-label*="More"]'
            ).first
            if await option_btn.is_visible(timeout=5000):
                await option_btn.click()
                await asyncio.sleep(random.uniform(1.5, 3))

                delete_btn = page.locator(
                    'div[role="menuitem"]:has-text("刪除"), '
                    'div[role="menuitem"]:has-text("Delete"), '
                    'span:has-text("刪除貼文"), '
                    'span:has-text("Delete post")'
                ).first
                if await delete_btn.is_visible(timeout=5000):
                    await delete_btn.click()
                    await asyncio.sleep(random.uniform(1.5, 3))

                    confirm_btn = page.locator(
                        'div[aria-label="刪除"], '
                        'div[aria-label="Delete"], '
                        'button:has-text("刪除"), '
                        'button:has-text("Delete")'
                    ).first
                    if await confirm_btn.is_visible(timeout=5000):
                        await confirm_btn.click()
                        deleted = 1
                        log("DELETE", "url", "已精準刪除貼文", "🗑️", detail=post_url[:80])
        except Exception as e:
            log("DELETE", "url", f"精準刪除失敗: {str(e)[:120]}", "❌")
        return deleted

    async def delete_from_group(self, page: Page, group_url: str, max_posts: int = 10) -> int:
        """刪除指定社團中的貼文"""
        deleted = 0
        try:
            # 優先嘗試最新排序，讓「剛發的貼文」更容易出現在前幾則
            url = group_url
            if "facebook.com/groups/" in group_url and "sorting_setting" not in group_url:
                url = group_url.rstrip("/") + "/?sorting_setting=CHRONOLOGICAL"
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(random.uniform(3, 6))

            for _ in range(max_posts):
                try:
                    option_btn = page.locator(
                        'div[aria-label="貼文選項"], '
                        'div[aria-label="Post options"], '
                        'div[aria-label="Actions for this post"], '
                        'div[aria-label*="更多"], '
                        'div[aria-label*="More"]'
                    ).first
                    if await option_btn.is_visible():
                        await option_btn.click()
                        await asyncio.sleep(random.uniform(2, 4))

                        delete_btn = page.locator(
                            'div[role="menuitem"]:has-text("刪除"), '
                            'div[role="menuitem"]:has-text("Delete"), '
                            'span:has-text("刪除貼文"), '
                            'span:has-text("Delete post")'
                        ).first
                        if await delete_btn.is_visible():
                            await delete_btn.click()
                            await asyncio.sleep(random.uniform(2, 4))

                            confirm_btn = page.locator(
                                'div[aria-label="刪除"], '
                                'div[aria-label="Delete"], '
                                'button:has-text("刪除"), '
                                'button:has-text("Delete")'
                            ).first
                            if await confirm_btn.is_visible():
                                await confirm_btn.click()
                                deleted += 1
                                log("DELETE", "group", f"已刪除社團貼文 #{deleted}", "🗑️")
                                await asyncio.sleep(random.uniform(30, 60))
                except Exception:
                    continue
        except Exception as e:
            log("DELETE", "group", f"社團刪文流程失敗: {str(e)[:120]}", "❌")
        return deleted

    async def delete_all_from_wall(self, page: Page, max_posts: int = 50) -> int:
        """刪除個人頁面貼文（謹慎使用）"""
        deleted = 0
        try:
            await page.goto("https://www.facebook.com/me/", wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(random.uniform(3, 6))

            for _ in range(max_posts):
                try:
                    option_btn = page.locator(
                        'div[aria-label="貼文選項"], '
                        'div[aria-label="Post options"], '
                        'div[aria-label="Actions for this post"], '
                        'div[aria-label*="更多"], '
                        'div[aria-label*="More"]'
                    ).first
                    if await option_btn.is_visible():
                        await option_btn.click()
                        await asyncio.sleep(random.uniform(2, 4))

                        delete_btn = page.locator(
                            'div[role="menuitem"]:has-text("刪除"), '
                            'div[role="menuitem"]:has-text("Delete"), '
                            'span:has-text("刪除貼文"), '
                            'span:has-text("Delete post")'
                        ).first
                        if await delete_btn.is_visible():
                            await delete_btn.click()
                            await asyncio.sleep(random.uniform(2, 4))

                            confirm_btn = page.locator(
                                'div[aria-label="刪除"], '
                                'div[aria-label="Delete"], '
                                'button:has-text("刪除"), '
                                'button:has-text("Delete")'
                            ).first
                            if await confirm_btn.is_visible():
                                await confirm_btn.click()
                                deleted += 1
                                log("DELETE", "wall", f"已刪除個人貼文 #{deleted}", "🗑️")
                                await asyncio.sleep(random.uniform(30, 60))
                except Exception:
                    continue
        except Exception as e:
            log("DELETE", "wall", f"個人刪文流程失敗: {str(e)[:120]}", "❌")
        return deleted
