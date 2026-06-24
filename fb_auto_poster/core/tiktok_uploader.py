"""TikTok 上傳器 — 使用 Playwright 持久化瀏覽器設定檔

流程：
  1. 第一次：瀏覽器開啟 → 用戶手動登入 TikTok
  2. 儲存登入狀態到 data/tiktok_profile/{nickname}/
  3. 之後每次上傳直接載入設定檔，不需重新登入
"""
import asyncio
import os
from typing import List, Optional

from utils.config import get_data_path
from utils.secret_store import encrypt_secret, decrypt_secret, mask
from utils.logger import log

_ACCOUNTS_FILE = "tiktok_accounts.json"
_PROFILE_DIR = "tiktok_profile"


# ─────────────────────────── 帳號儲存 ───────────────────────────

def _accounts_path() -> str:
    from utils.config import load_json, save_json as _save
    return _ACCOUNTS_FILE, load_json, _save


def _load_raw() -> dict:
    from utils.config import load_json
    return load_json(_ACCOUNTS_FILE, {})


def _save_raw(data: dict) -> None:
    from utils.config import save_json
    save_json(_ACCOUNTS_FILE, data)


def _profile_path(nickname: str) -> str:
    """使用者設定檔目錄 data/tiktok_profile/{nickname}/"""
    p = get_data_path(os.path.join(_PROFILE_DIR, nickname))
    os.makedirs(p, exist_ok=True)
    return p


def _is_logged_in(nickname: str) -> bool:
    """檢查是否已登入（有儲存的設定檔）"""
    profile_dir = _profile_path(nickname)
    state_file = os.path.join(profile_dir, "state.json")
    return os.path.exists(state_file)


def list_accounts() -> List[dict]:
    data = _load_raw()
    result = []
    for nickname, rec in data.items():
        logged_in = _is_logged_in(nickname)
        token_preview = "✅ 已登入" if logged_in else mask(rec.get("session_id_enc", ""), 6)
        result.append({
            "nickname": nickname,
            "token_preview": token_preview,
            "logged_in": logged_in,
        })
    return result


def save_account(nickname: str, session_id: str = "") -> None:
    if not nickname:
        raise ValueError("暱稱為必填")
    data = _load_raw()
    rec = {}
    if session_id:
        rec["session_id_enc"] = encrypt_secret(session_id)
    data[nickname] = rec
    _save_raw(data)


def remove_account(nickname: str) -> bool:
    import shutil
    data = _load_raw()
    if nickname in data:
        del data[nickname]
        _save_raw(data)
        # 刪除設定檔
        profile_dir = _profile_path(nickname)
        if os.path.exists(profile_dir):
            shutil.rmtree(profile_dir, ignore_errors=True)
        return True
    return False


# ─────────────────────────── Playwright 上傳 ───────────────────────────


async def _login(nickname: str) -> bool:
    """第一次執行：開啟瀏覽器讓用戶手動登入 TikTok，儲存設定檔"""
    from playwright.async_api import async_playwright

    profile_dir = _profile_path(nickname)

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=profile_dir,
            headless=False,
            viewport={"width": 1280, "height": 900},
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-web-security",
                "--disable-features=IsolateOrigins,site-per-process",
                "--no-sandbox",
                "--disable-setuid-sandbox",
            ],
        )

        page = await context.new_page()
        await page.goto("https://www.tiktok.com/", wait_until="networkidle")

        log("TIKTOK", nickname, "瀏覽器已開啟，請手動登入 TikTok", "🔑")

        # 等待直到 URL 不再指向登入頁面（最多 5 分鐘）
        for _ in range(300):
            current = page.url
            if "passport" not in current and "login" not in current.lower() and current != "about:blank":
                break
            await asyncio.sleep(1)

        # 儲存登入狀態
        await page.goto("https://www.tiktok.com/tiktokstudio/upload", wait_until="networkidle")
        await asyncio.sleep(2)

        await context.close()

    log("TIKTOK", nickname, "登入狀態已儲存", "✅")
    return True


async def _upload_with_playwright(
    nickname: str,
    video_path: str,
    title: str,
    tags: Optional[List[str]] = None,
) -> dict:
    """使用 Playwright 持久化設定檔上傳 TikTok"""
    from playwright.async_api import async_playwright

    if not os.path.exists(video_path):
        return {"success": False, "error": f"找不到影片檔: {video_path}"}

    profile_dir = _profile_path(nickname)

    # 如果沒有登入狀態，先要求登入
    if not _is_logged_in(nickname):
        log("TIKTOK", nickname, "尚未登入 TikTok，請先完成登入", "🔑")
        ok = await _login(nickname)
        if not ok:
            return {"success": False, "error": "登入失敗"}

    # 組合標題 + hashtags
    if tags:
        tag_str = " ".join([t if t.startswith("#") else f"#{t}" for t in tags if t.strip()])
        caption = f"{title}\n{tag_str}" if tag_str else title
    else:
        caption = title

    try:
        async with async_playwright() as p:
            context = await p.chromium.launch_persistent_context(
                user_data_dir=profile_dir,
                headless=False,
                viewport={"width": 1280, "height": 900},
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-web-security",
                    "--disable-features=IsolateOrigins,site-per-process",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                ],
            )

            page = await context.new_page()

            # 前往 TikTok Studio 上傳頁面（使用 domcontentloaded 更快，timeout 拉長）
            try:
                await page.goto("https://www.tiktok.com/tiktokstudio/upload", wait_until="domcontentloaded", timeout=90000)
            except Exception as e:
                log("TIKTOK", nickname, f"導航逾時，目前網址: {page.url}", "⚠️")
                # 如果被導到登入頁，表示設定檔登入已過期
                if "passport" in page.url or "login" in page.url:
                    await context.close()
                    return {"success": False, "error": "登入已過期，請重新在 TikTok 設定中點「🔑 登入」"}
                # 否則再試一次
                try:
                    await page.goto("https://www.tiktok.com/tiktokstudio/upload", wait_until="domcontentloaded", timeout=90000)
                except Exception:
                    pass

            await asyncio.sleep(5)

            # 選擇影片檔案
            file_input = page.locator('input[type="file"]').first
            if await file_input.is_visible(timeout=8000):
                await file_input.set_input_files(video_path)
                log("TIKTOK", nickname, "影片已選取，處理中...", "⏳")
            else:
                await context.close()
                return {"success": False, "error": "找不到上傳區，請確認已登入"}

            # 等待上傳完成（最多 3 分鐘）
            await asyncio.sleep(5)
            log("TIKTOK", nickname, "影片上傳中，請稍候...", "⏳")
            try:
                await page.wait_for_function(
                    "() => document.querySelector('div[contenteditable]') !== null || document.querySelector('textarea') !== null",
                    timeout=120000,
                )
            except Exception:
                pass  # 超時繼續

            await asyncio.sleep(3)

            # 填入標題
            caption_area = page.locator('div[contenteditable="true"]').first
            if await caption_area.is_visible(timeout=5000):
                await caption_area.click()
                await asyncio.sleep(1)
                await caption_area.fill(caption)
                log("TIKTOK", nickname, "標題已填入", "✅")
            else:
                textarea = page.locator('textarea').first
                if await textarea.is_visible(timeout=3000):
                    await textarea.fill(caption)

            # 點擊發布
            post_btn = page.locator('button:has-text("Post"), button:has-text("發布")').first
            if await post_btn.is_visible(timeout=5000):
                await post_btn.click()
                log("TIKTOK", nickname, "已送出發布", "✅")
            else:
                post_btn = page.locator('div[role="dialog"] button:has-text("Post")').first
                if await post_btn.is_visible(timeout=3000):
                    await post_btn.click()

            await asyncio.sleep(3)
            await context.close()

        log("TIKTOK", nickname, "TikTok 上傳完成", "✅")
        return {"success": True, "publish_id": "", "error": ""}

    except Exception as e:
        return {"success": False, "error": f"Playwright 上傳失敗: {str(e)[:150]}"}


def upload_video(
    nickname: str,
    video_path: str,
    title: str,
    tags: Optional[List[str]] = None,
    **kwargs,
) -> dict:
    """TikTok 上傳（同步版本）

    第一次使用需要手動登入，之後自動重複使用設定檔。
    """
    if not nickname:
        return {"success": False, "error": "請先選擇 TikTok 帳號"}

    try:
        result = asyncio.run(_upload_with_playwright(nickname, video_path, title, tags))
        return result
    except Exception as e:
        return {"success": False, "error": f"執行異常: {str(e)[:150]}"}
