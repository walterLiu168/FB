"""Captcha 自動辨識模組 — 2captcha API + 手動輸入 fallback

支援：
  - 2captcha 自動解碼 (每月 $0.002/張)
  - 本地手動輸入 dialog (免費用，彈出視窗讓用戶輸入)
  - 自動偵測 captcha 類型 (text / recaptcha v2 / hcaptcha)
  - 設定檔管理 API key
"""
import asyncio
import base64
import io
import json
import os
import threading
import time
from typing import Optional

from utils.logger import log
from utils.universal_config import get, get_int

_CAPTCHA_KEY = get("CAPTCHA_API_KEY", "MOCK")
_MOCK_MODE = _CAPTCHA_KEY == "MOCK" or not _CAPTCHA_KEY


def is_configured() -> bool:
    """檢查 captcha API 是否已設定"""
    return not _MOCK_MODE


def set_api_key(key: str):
    """設定 2captcha API key"""
    global _CAPTCHA_KEY, _MOCK_MODE
    _CAPTCHA_KEY = key
    _MOCK_MODE = (key == "MOCK" or not key)
    # 寫入 .env
    try:
        env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env")
        content = ""
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                content = f.read()
        if "CAPTCHA_API_KEY=" in content:
            import re
            content = re.sub(r"CAPTCHA_API_KEY=.*", f"CAPTCHA_API_KEY={key}", content)
        else:
            content += f"\nCAPTCHA_API_KEY={key}\n"
        with open(env_path, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception:
        pass


class ManualCaptchaDialog:
    """手動輸入 Captcha 的對話框 (tkinter)"""

    def __init__(self, image_bytes: bytes = None, prompt: str = "請輸入驗證碼"):
        self._result: Optional[str] = None
        self._image_bytes = image_bytes
        self._prompt = prompt
        self._thread = threading.Thread(target=self._show, daemon=True)
        self._thread.start()

    def _show(self):
        import tkinter as tk
        from tkinter import ttk

        self._root = tk.Tk()
        self._root.title("驗證碼輸入")
        self._root.geometry("350x250")
        self._root.configure(bg="#2b2b2b")
        self._root.attributes('-topmost', True)

        # 提示
        label = ttk.Label(self._root, text=self._prompt, font=("Arial", 11))
        label.pack(pady=(15, 5))

        # 圖片 (如果有)
        if self._image_bytes:
            try:
                from PIL import Image, ImageTk
                img = Image.open(io.BytesIO(self._image_bytes))
                img = img.resize((200, 60), Image.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                img_label = ttk.Label(self._root, image=photo)
                img_label.image = photo
                img_label.pack(pady=5)
            except Exception:
                pass

        # 輸入框
        self._entry = ttk.Entry(self._root, font=("Arial", 14), justify="center")
        self._entry.pack(pady=10, padx=20, fill=tk.X)
        self._entry.focus_set()

        # 按鈕
        btn_frame = ttk.Frame(self._root)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text="確定", command=self._on_ok).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="取消", command=self._on_cancel).pack(side=tk.LEFT, padx=5)

        # Enter = 確定
        self._entry.bind("<Return>", lambda e: self._on_ok())

        self._root.mainloop()

    def _on_ok(self):
        self._result = self._entry.get().strip()
        self._root.destroy()

    def _on_cancel(self):
        self._result = None
        self._root.destroy()

    def get_result(self, timeout: float = 120) -> Optional[str]:
        """等待用戶輸入結果"""
        self._thread.join(timeout=timeout)
        return self._result


async def solve_text_captcha(page, selector: str = 'img[src*="captcha"]') -> Optional[str]:
    """辨識文字驗證碼
    
    策略：
      1. 嘗試 2captcha API (若已設定)
      2. 截圖 → 彈出視窗請使用者手動輸入
    """
    try:
        # 等待 captcha 圖片出現
        img_el = await page.wait_for_selector(selector, timeout=5000)
        if not img_el:
            return None

        # 截圖
        screenshot = await img_el.screenshot()
        if not screenshot:
            return None

        # 嘗試 2captcha
        if is_configured():
            result = await _solve_via_2captcha(screenshot, "text")
            if result:
                return result

        # Fallback: 手動輸入
        log("CAPTCHA", "manual", "彈出視窗請使用者輸入驗證碼", "📝")
        dialog = ManualCaptchaDialog(screenshot, "請輸入圖片中的驗證碼")
        return dialog.get_result(timeout=120)

    except Exception as e:
        log("CAPTCHA", "text", str(e)[:80], "❌")
        return None


async def solve_recaptcha(page, site_key: str = None) -> Optional[str]:
    """辨識 reCAPTCHA v2"""
    if not is_configured():
        log("CAPTCHA", "recaptcha", "未設定 API key，需要手動處理", "⚠️")
        return None

    try:
        current_url = page.url
        # 等待 recaptcha iframe
        frame = await page.wait_for_selector('iframe[src*="recaptcha"]', timeout=5000)
        if not frame:
            return None

        # 截圖整個頁面
        screenshot = await page.screenshot(type="png")

        result = await _solve_via_2captcha(screenshot, "recaptcha_v2", site_key=site_key, page_url=current_url)
        if result:
            # 填入 token
            await page.evaluate(f'document.getElementById("g-recaptcha-response").innerHTML = "{result}"')
            await page.evaluate("___grecaptcha_cfg.clients[0].___grecaptcha_cfg.callback()")
            return result
    except Exception as e:
        log("CAPTCHA", "recaptcha", str(e)[:80], "❌")

    return None


async def _solve_via_2captcha(image_bytes: bytes, captcha_type: str = "text", **kwargs) -> Optional[str]:
    """透過 2captcha API 解碼
    
    Args:
        image_bytes: captcha 圖片 PNG bytes
        captcha_type: "text" | "recaptcha_v2" | "hcaptcha"
    
    2captcha API 格式: https://2captcha.com/2captcha-api
    """
    if _MOCK_MODE:
        return None

    try:
        import requests

        # Step 1: Submit captcha
        if captcha_type == "text":
            img_base64 = base64.b64encode(image_bytes).decode()
            data = {
                "key": _CAPTCHA_KEY,
                "method": "base64",
                "body": img_base64,
                "json": 1,
            }
        else:
            site_key = kwargs.get("site_key", "")
            page_url = kwargs.get("page_url", "")
            data = {
                "key": _CAPTCHA_KEY,
                "method": "userrecaptcha" if captcha_type == "recaptcha_v2" else "hcaptcha",
                "googlekey": site_key,
                "pageurl": page_url,
                "json": 1,
            }

        resp = requests.post("https://api.2captcha.com/in.php", data=data, timeout=30)
        submit_result = resp.json()

        if submit_result.get("status") != 1 and not submit_result.get("request"):
            log("CAPTCHA", "submit", submit_result.get("error_text", "unknown"), "❌")
            return None

        request_id = submit_result.get("request")

        # Step 2: Poll for result (max 2 minutes)
        for attempt in range(24):
            await asyncio.sleep(5)
            poll_resp = requests.get(
                "https://api.2captcha.com/res.php",
                params={"key": _CAPTCHA_KEY, "action": "get", "id": request_id, "json": 1},
                timeout=15,
            )
            poll_data = poll_resp.json()
            if poll_data.get("status") == 1:
                solution = poll_data.get("request")
                log("CAPTCHA", "solved", f"已解 ({attempt * 5 + 5}s)", "✅")
                return solution
            if poll_data.get("request") == "ERROR_CAPTCHA_UNSOLVABLE":
                break

        log("CAPTCHA", "poll", "解碼逾時或無法解決", "⏱️")
        return None

    except Exception as e:
        log("CAPTCHA", "2captcha", str(e)[:80], "❌")
        return None


async def check_and_solve_captcha(page, timeout: float = 10) -> bool:
    """自動偵測頁面上是否有 captcha 並嘗試解決
    
    Returns:
        True: 已解決或無 captcha
        False: 仍有 captcha 無法解決
    """
    try:
        # 檢查 recaptcha
        has_recaptcha = await page.query_selector('iframe[src*="recaptcha"]')
        if has_recaptcha:
            site_key = None
            try:
                src = await has_recaptcha.get_attribute("src") or ""
                import re
                m = re.search(r"k=([^&]+)", src)
                if m:
                    site_key = m.group(1)
            except Exception:
                pass
            return await solve_recaptcha(page, site_key) is not None

        # 檢查 hcaptcha
        has_hcaptcha = await page.query_selector('iframe[src*="hcaptcha"]')
        if has_hcaptcha:
            site_key = None
            try:
                src = await has_hcaptcha.get_attribute("src") or ""
                import re
                m = re.search(r"sitekey=([^&]+)", src)
                if m:
                    site_key = m.group(1)
            except Exception:
                pass
            result = await _solve_via_2captcha(
                await page.screenshot(type="png"),
                "hcaptcha",
                site_key=site_key or "default",
                page_url=page.url,
            )
            return result is not None

        # 檢查圖片驗證碼
        img_captcha = await page.query_selector('img[src*="captcha"], img[src*="Captcha"], img[id*="captcha"]')
        if img_captcha:
            result = await solve_text_captcha(page)
            if result:
                # 填入輸入框
                input_sel = 'input[name*="captcha"], input[id*="captcha"], input[placeholder*="驗證"]'
                input_el = await page.query_selector(input_sel)
                if input_el:
                    await input_el.fill(result)
                    # 嘗試自動提交
                    submit_sel = 'button[type="submit"], input[type="submit"], button:has-text("確認")'
                    submit_btn = await page.query_selector(submit_sel)
                    if submit_btn:
                        await submit_btn.click()
                        await asyncio.sleep(2)
                return True
            return False

        # 無 captcha
        return True

    except Exception:
        return True  # assume no captcha on error
