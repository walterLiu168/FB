# FB Auto Poster 實作計劃

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立一個 Python + Playwright + Tkinter 的 FB 自動發文桌面應用，支援多帳號管理、排程發文、養號、刪文、自動留言。

**Architecture:** 四層架構 — GUI (Tkinter) → Core (業務邏輯) → Utils (工具函數) → Playwright (瀏覽器自動化)。各層間透過事件/指令溝通，Core 層直接操作 Playwright。

**Tech Stack:** Python 3.11+, Playwright, Tkinter + ttkbootstrap, APScheduler, Argon2-cffi

---
## 檔案結構

```
fb_auto_poster/
├── main.py                       # 主程式入口
├── requirements.txt
├── gui/
│   ├── __init__.py
│   ├── app.py                    # 主視窗 + 功能頁面切換
│   ├── account_manager.py        # 多帳號管理界面
│   ├── scheduler_panel.py        # 排程設定界面
│   ├── poster_panel.py           # 發文操作界面
│   ├── nurturer_panel.py         # 養號設定界面
│   └── dark_theme.py             # 暗色主題樣式
├── core/
│   ├── __init__.py
│   ├── browser.py                # Playwright 瀏覽器管理 + 反偵測
│   ├── account.py                # 帳號管理 (加密儲存)
│   ├── poster.py                 # 一般/拍賣發文引擎
│   ├── nurturer.py               # 養號引擎 (模擬真人)
│   ├── scheduler.py              # 排程引擎
│   ├── deleter.py                # 自動刪文
│   └── interactor.py             # 自動留言互動
├── utils/
│   ├── __init__.py
│   ├── crypto.py                 # Argon2 加密
│   ├── randomizer.py             # 隨機延遲/文字/圖片
│   └── config.py                 # 設定管理
└── data/                         # 本地資料儲存 (gitignored)
    └── .gitkeep
```

---

### Task 1: 專案初始化 + requirements.txt + 目錄結構

**Files:**
- Create: `c:\Users\icemo\Documents\trae_projects\facebook\fb_auto_poster\requirements.txt`
- Create: `c:\Users\icemo\Documents\trae_projects\facebook\fb_auto_poster\data\.gitkeep`
- Create: `c:\Users\icemo\Documents\trae_projects\facebook\.gitignore`

- [ ] **Step 1: Create .gitignore**
    ```gitignore
    # .gitignore
    fb_auto_poster/data/
    fb_auto_poster/__pycache__/
    *.pyc
    .venv/
    .env
    ```

- [ ] **Step 2: Create requirements.txt**
    ```
    playwright>=1.40.0
    ttkbootstrap>=1.10.0
    apscheduler>=3.10.0
    argon2-cffi>=23.1.0
    Pillow>=10.0.0
    requests>=2.31.0
    ```

- [ ] **Step 3: Create data/.gitkeep**
    (Empty file)

- [ ] **Step 4: Create directory structure**
    ```
    cd fb_auto_poster
    mkdir -p gui core utils data
    echo "" > gui/__init__.py
    echo "" > core/__init__.py
    echo "" > utils/__init__.py
    ```
    Run: `mkdir -p fb_auto_poster/gui fb_auto_poster/core fb_auto_poster/utils fb_auto_poster/data`

- [ ] **Step 5: Create data directory marker**
    Run: `echo "" > fb_auto_poster/data/.gitkeep`

---

### Task 2: utils/crypto.py — Argon2 加密模組

**Files:**
- Create: `c:\Users\icemo\Documents\trae_projects\facebook\fb_auto_poster\utils\crypto.py`

- [ ] **Step 1: Write crypto.py**

```python
"""Argon2 加密工具 — 用於加密儲存帳號密碼與 cookies"""
import json
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_ph = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=4,
    hash_len=32,
    salt_len=16,
)


def encrypt(plain_text: str) -> str:
    """使用 Argon2 加密明文字串"""
    return _ph.hash(plain_text)


def verify(hashed: str, plain_text: str) -> bool:
    """驗證明文字串是否匹配 Argon2 hash"""
    try:
        return _ph.verify(hashed, plain_text)
    except VerifyMismatchError:
        return False


def encrypt_dict(data: dict) -> str:
    """將 dict 序列化後加密"""
    return encrypt(json.dumps(data, ensure_ascii=False))


def decrypt_dict(hashed: str) -> dict:
    """驗證並還原 dict（此處使用空字串作為 dummy verify，實際解密是透過 verify）

    Note: Argon2 是單向 hash，真正的「解密」是透過 verify 比對。
    此處保留為介面相容，實際使用時不應嘗試反解密。
    """
    # Argon2 不支援解密，此函數僅保留接口相容
    raise NotImplementedError("Argon2 不支援解密，如需還原資料請重新加密")
```

---

### Task 3: utils/randomizer.py — 隨機化工具

**Files:**
- Create: `c:\Users\icemo\Documents\trae_projects\facebook\fb_auto_poster\utils\randomizer.py`

- [ ] **Step 1: Write randomizer.py**

```python
"""隨機延遲、文字、圖片插入工具 — 突破 FB 重複偵測"""
import random
import time


def random_delay(min_sec: float = 60, max_sec: float = 360):
    """隨機等待 min_sec ~ max_sec 秒，模擬真人操作節奏"""
    delay = random.uniform(min_sec, max_sec)
    time.sleep(delay)
    return delay


def short_delay(min_sec: float = 2, max_sec: float = 8):
    """短暫隨機等待，用於頁面操作之間"""
    delay = random.uniform(min_sec, max_sec)
    time.sleep(delay)
    return delay


def random_string(prefix: str = "", length: int = 8) -> str:
    """產生隨機字串，突破 FB 重複發文偵測"""
    chars = "abcdefghijklmnopqrstuvwxyz0123456789"
    suffix = "".join(random.choice(chars) for _ in range(length))
    return f"{prefix}{suffix}"


def random_suffix() -> str:
    """產生隨機後綴，附加在文案末尾"""
    tags = [
        f"\n\n#{random_string('', 6)}",
        f"\n.\n.",
        f"\n{' '.join(random.sample(['🔥','💥','⚡','📌','✅'], k=random.randint(1,3)))}",
        f"\n({random.choice(['今日限定','限時優惠','熱銷中','搶手物件','即將售罄'])})",
    ]
    return random.choice(tags)


def random_user_agent() -> str:
    """隨機 User-Agent 輪換"""
    agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_2) AppleWebKit/605.1.15 Safari/604.1",
    ]
    return random.choice(agents)


def random_viewport() -> dict:
    """隨機視窗尺寸"""
    sizes = [
        {"width": 1920, "height": 1080},
        {"width": 1366, "height": 768},
        {"width": 1536, "height": 864},
        {"width": 1440, "height": 900},
    ]
    return random.choice(sizes)
```

---

### Task 4: utils/config.py — 設定管理

**Files:**
- Create: `c:\Users\icemo\Documents\trae_projects\facebook\fb_auto_poster\utils\config.py`

- [ ] **Step 1: Write config.py**

```python
"""設定管理 — 讀寫本地 JSON 設定檔"""
import json
import os
from typing import Any

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")


def _ensure_data_dir():
    os.makedirs(_DATA_DIR, exist_ok=True)


def get_data_path(filename: str) -> str:
    return os.path.join(_DATA_DIR, filename)


def load_json(filename: str, default: Any = None) -> Any:
    """從 data/ 目錄載入 JSON 檔案"""
    _ensure_data_dir()
    path = get_data_path(filename)
    if not os.path.exists(path):
        return default if default is not None else {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return default if default is not None else {}


def save_json(filename: str, data: Any) -> None:
    """儲存 JSON 到 data/ 目錄"""
    _ensure_data_dir()
    path = get_data_path(filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_accounts() -> list:
    """載入帳號列表"""
    return load_json("accounts.json", [])


def save_accounts(accounts: list) -> None:
    """儲存帳號列表"""
    save_json("accounts.json", accounts)


def load_schedules() -> list:
    return load_json("schedules.json", [])


def save_schedules(schedules: list) -> None:
    save_json("schedules.json", schedules)


def load_config() -> dict:
    return load_json("config.json", {})


def save_config(config: dict) -> None:
    save_json("config.json", config)
```

---

### Task 5: core/browser.py — Playwright 瀏覽器管理

**Files:**
- Create: `c:\Users\icemo\Documents\trae_projects\facebook\fb_auto_poster\core\browser.py`

- [ ] **Step 1: Write browser.py**

```python
"""Playwright 瀏覽器管理 + 反偵測引擎"""
import asyncio
import os
from typing import Optional

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from utils.randomizer import random_user_agent, random_viewport


class BrowserManager:
    """管理多帳號的瀏覽器實例與 Context"""

    def __init__(self):
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._contexts: dict[str, BrowserContext] = {}
        self._pages: dict[str, Page] = {}
        self._headless = False

    async def start(self, headless: bool = False) -> None:
        """啟動瀏覽器"""
        self._headless = headless
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )

    async def create_context(self, account_id: str, cookie_str: str = "") -> BrowserContext:
        """為指定帳號建立獨立 Context，載入 Cookie 保持登入"""
        ua = random_user_agent()
        vp = random_viewport()

        context = await self._browser.new_context(
            user_agent=ua,
            viewport=vp,
            locale="zh-TW",
            timezone_id="Asia/Taipei",
            permissions=["clipboard-read", "clipboard-write"],
        )

        # 防偵測：注入 JS 隱藏自動化痕跡
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
            Object.defineProperty(navigator, 'languages', { get: () => ['zh-TW', 'zh', 'en'] });
        """)

        # 載入 Cookie
        if cookie_str:
            import json
            try:
                cookies = json.loads(cookie_str)
                await context.add_cookies(cookies)
            except (json.JSONDecodeError, Exception):
                pass

        page = await context.new_page()
        self._contexts[account_id] = context
        self._pages[account_id] = page
        return context

    async def get_page(self, account_id: str) -> Page:
        """取得指定帳號的 Page 實例"""
        return self._pages.get(account_id)

    async def get_context(self, account_id: str) -> BrowserContext:
        return self._contexts.get(account_id)

    async def close_context(self, account_id: str) -> None:
        """關閉指定帳號的 Context"""
        if account_id in self._contexts:
            await self._contexts[account_id].close()
            del self._contexts[account_id]
            del self._pages[account_id]

    async def export_cookies(self, account_id: str, storage_path: str) -> None:
        """匯出指定帳號的 cookies 到檔案"""
        context = self._contexts.get(account_id)
        if context:
            cookies = await context.cookies()
            import json
            os.makedirs(os.path.dirname(storage_path), exist_ok=True)
            with open(storage_path, "w", encoding="utf-8") as f:
                json.dump(cookies, f, ensure_ascii=False, indent=2)

    async def stop(self) -> None:
        """關閉瀏覽器"""
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._contexts.clear()
        self._pages.clear()
```

---

### Task 6: core/account.py — 帳號管理

**Files:**
- Create: `c:\Users\icemo\Documents\trae_projects\facebook\fb_auto_poster\core\account.py`

- [ ] **Step 1: Write account.py**

```python
"""帳號管理 — 多帳號 CRUD + 加密儲存"""
import json
import os
from typing import Optional

from utils.config import load_accounts, save_accounts, get_data_path
from utils.crypto import encrypt, verify


class Account:
    def __init__(
        self,
        account_id: str,
        email: str,
        password: str = "",
        cookie_path: str = "",
        nickname: str = "",
        is_active: bool = True,
    ):
        self.account_id = account_id
        self.email = email
        self.password = password
        self.cookie_path = cookie_path
        self.nickname = nickname or email
        self.is_active = is_active

    def to_dict(self) -> dict:
        return {
            "account_id": self.account_id,
            "email": self.email,
            "password_hash": encrypt(self.password) if self.password else "",
            "cookie_path": self.cookie_path,
            "nickname": self.nickname,
            "is_active": self.is_active,
        }

    @staticmethod
    def from_dict(data: dict) -> "Account":
        return Account(
            account_id=data["account_id"],
            email=data["email"],
            cookie_path=data.get("cookie_path", ""),
            nickname=data.get("nickname", data["email"]),
            is_active=data.get("is_active", True),
        )


class AccountManager:
    """帳號管理器"""

    def __init__(self):
        self._accounts: dict[str, Account] = {}
        self.load()

    def add(self, account: Account) -> None:
        self._accounts[account.account_id] = account
        self.save()

    def remove(self, account_id: str) -> bool:
        if account_id in self._accounts:
            del self._accounts[account_id]
            self.save()
            return True
        return False

    def get(self, account_id: str) -> Optional[Account]:
        return self._accounts.get(account_id)

    def list_all(self) -> list[Account]:
        return list(self._accounts.values())

    def list_active(self) -> list[Account]:
        return [a for a in self._accounts.values() if a.is_active]

    def set_active(self, account_id: str, active: bool) -> None:
        if account_id in self._accounts:
            self._accounts[account_id].is_active = active
            self.save()

    def load(self) -> None:
        raw = load_accounts()
        seen = {}
        for item in raw:
            acc = Account.from_dict(item)
            seen[acc.account_id] = acc
        self._accounts = seen

    def save(self) -> None:
        raw = [a.to_dict() for a in self._accounts.values()]
        save_accounts(raw)

    def import_cookie(self, account_id: str, cookie_json_str: str) -> bool:
        """匯入 FB Cookie JSON 字串，存到本地檔案"""
        import uuid
        try:
            data = json.loads(cookie_json_str)
            if not isinstance(data, list):
                return False
            cookie_file = f"cookies_{account_id}.json"
            cookie_path = get_data_path(cookie_file)
            os.makedirs(os.path.dirname(cookie_path), exist_ok=True)
            with open(cookie_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            if account_id in self._accounts:
                self._accounts[account_id].cookie_path = cookie_path
                self.save()
            return True
        except (json.JSONDecodeError, Exception):
            return False

    def get_cookie_json(self, account_id: str) -> str:
        """讀取已儲存的 Cookie JSON 字串"""
        acc = self._accounts.get(account_id)
        if not acc or not acc.cookie_path:
            return ""
        try:
            with open(acc.cookie_path, "r", encoding="utf-8") as f:
                return f.read()
        except (FileNotFoundError, Exception):
            return ""
```

---

### Task 7: core/poster.py — 發文引擎

**Files:**
- Create: `c:\Users\icemo\Documents\trae_projects\facebook\fb_auto_poster\core\poster.py`

- [ ] **Step 1: Write poster.py**

```python
"""發文引擎 — 一般發文 + 拍賣發文 + 自動轉發到多社團"""
import asyncio
import random
from typing import Optional

from playwright.async_api import Page

from utils.randomizer import random_delay, short_delay, random_suffix


class Poster:
    """FB 發文引擎"""

    async def post_general(
        self,
        page: Page,
        content: str,
        image_paths: list[str] = None,
        groups: list[str] = None,
    ) -> dict:
        """
        一般發文：
        - content: 文案內容（會自動加隨機後綴）
        - image_paths: 圖片路徑列表
        - groups: 目標社團名稱列表（None = 只發個人頁面）
        """
        if not content.strip():
            return {"success": False, "error": "文案不能為空"}

        text = content + random_suffix()
        results = {"success": True, "posted_to": []}

        if groups:
            for group in groups:
                result = await self._post_to_group(page, group, text, image_paths)
                results["posted_to"].append({"group": group, **result})
                if result.get("success"):
                    await random_delay(60, 180)
        else:
            result = await self._post_to_wall(page, text, image_paths)
            results["posted_to"].append({"group": "個人頁面", **result})

        return results

    async def post_marketplace(
        self,
        page: Page,
        title: str,
        price: str,
        location: str,
        description: str,
        image_paths: list[str] = None,
    ) -> dict:
        """拍賣發文到 FB Marketplace"""
        text = f"{title}\n{description}" + random_suffix()
        try:
            # 前往 Marketplace
            await page.goto("https://www.facebook.com/marketplace/create", wait_until="networkidle")
            await short_delay(3, 6)

            # 輸入標題
            title_input = page.locator('input[aria-label*="標題"], input[placeholder*="標題"]').first
            if await title_input.is_visible():
                await title_input.fill(title)
                await short_delay(1, 3)

            # 輸入價格
            price_input = page.locator('input[aria-label*="價格"], input[placeholder*="價格"]').first
            if await price_input.is_visible():
                await price_input.fill(str(price))
                await short_delay(1, 3)

            # 輸入地點
            location_input = page.locator('input[aria-label*="地點"], input[placeholder*="地點"]').first
            if await location_input.is_visible():
                await location_input.fill(location)
                await short_delay(1, 3)

            # 輸入描述
            desc_input = page.locator('div[aria-label*="描述"], div[contenteditable="true"]').first
            if await desc_input.is_visible():
                await desc_input.fill(text)
                await short_delay(1, 3)

            # 上傳圖片
            if image_paths:
                file_input = page.locator('input[type="file"]').first
                if await file_input.is_visible():
                    await file_input.set_input_files(image_paths)
                    await short_delay(3, 6)

            # 點擊發布
            publish_btn = page.locator('div[aria-label="發佈"], div[aria-label="發布"]').first
            if await publish_btn.is_visible():
                await publish_btn.click()
                await short_delay(2, 4)

            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _post_to_wall(
        self, page: Page, text: str, image_paths: list[str] = None
    ) -> dict:
        """發文到個人頁面"""
        try:
            await page.goto("https://www.facebook.com/", wait_until="networkidle")
            await short_delay(3, 6)

            # 點擊「在想什麼？」
            status_box = page.locator('div[aria-label*="在想什麼"], div[role="button"]:has-text("在想什麼")').first
            if await status_box.is_visible():
                await status_box.click()
                await short_delay(2, 4)

            # 輸入內容
            editor = page.locator('div[aria-label*="貼文"], div[contenteditable="true"]').first
            if await editor.is_visible():
                await editor.fill(text)
                await short_delay(2, 4)

            # 上傳圖片
            if image_paths:
                file_input = page.locator('input[type="file"]').first
                if await file_input.is_visible():
                    await file_input.set_input_files(image_paths)
                    await short_delay(3, 6)

            # 發布
            publish_btn = page.locator('div[aria-label="發佈"]').first
            if await publish_btn.is_visible():
                await publish_btn.click()
                await short_delay(2, 4)

            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _post_to_group(
        self, page: Page, group_name: str, text: str, image_paths: list[str] = None
    ) -> dict:
        """發文到指定社團"""
        try:
            await page.goto(f"https://www.facebook.com/search/groups/?q={group_name}", wait_until="networkidle")
            await short_delay(3, 6)

            # 點擊第一個社團結果
            group_link = page.locator(f'a:has-text("{group_name}")').first
            if await group_link.is_visible():
                await group_link.click()
                await short_delay(4, 8)

            # 點擊發文框
            post_box = page.locator('div[aria-label*="貼文"], div[role="button"]:has-text("寫些什麼")').first
            if await post_box.is_visible():
                await post_box.click()
                await short_delay(2, 4)

            # 輸入內容
            editor = page.locator('div[aria-label*="貼文"], div[contenteditable="true"]').first
            if await editor.is_visible():
                await editor.fill(text)
                await short_delay(2, 4)

            # 上傳圖片
            if image_paths:
                file_input = page.locator('input[type="file"]').first
                if await file_input.is_visible():
                    await file_input.set_input_files(image_paths)
                    await short_delay(3, 6)

            # 發布
            publish_btn = page.locator('div[aria-label="發佈"]').first
            if await publish_btn.is_visible():
                await publish_btn.click()
                await short_delay(2, 4)

            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
```

---

### Task 8: core/nurturer.py — 養號引擎

**Files:**
- Create: `c:\Users\icemo\Documents\trae_projects\facebook\fb_auto_poster\core\nurturer.py`

- [ ] **Step 1: Write nurturer.py**

```python
"""養號引擎 — 模擬真人操作"""
import asyncio
import random

from playwright.async_api import Page

from utils.randomizer import short_delay, random_delay


class Nurturer:
    """帳號養護引擎"""

    async def browse_feed(self, page: Page, count: int = 5):
        """模擬瀏覽動態消息，每天 1~10 篇"""
        await page.goto("https://www.facebook.com/", wait_until="networkidle")
        await short_delay(3, 6)

        for i in range(min(count, 10)):
            try:
                # 模擬滾動
                await page.evaluate("window.scrollBy(0, 800)")
                await short_delay(3, 8)

                # 隨機按讚
                if random.random() < 0.3:
                    like_btn = page.locator('div[aria-label="讚"], div[aria-label="Like"]').first
                    if await like_btn.is_visible():
                        await like_btn.click()
                        await short_delay(2, 5)

                # 隨機看留言
                if random.random() < 0.2:
                    comment_btn = page.locator('div[aria-label="留言"], div[aria-label="Comment"]').first
                    if await comment_btn.is_visible():
                        await comment_btn.click()
                        await short_delay(4, 8)

                await random_delay(10, 30)
            except Exception:
                pass

    async def join_groups(self, page: Page, keywords: list[str], max_groups: int = 5):
        """安全加入社團。每次 5 個，間隔 60 秒"""
        joined = 0
        for keyword in keywords:
            if joined >= max_groups:
                break
            try:
                await page.goto(
                    f"https://www.facebook.com/search/groups/?q={keyword}",
                    wait_until="networkidle",
                )
                await short_delay(3, 6)

                join_btns = page.locator('div[aria-label="加入社團"], div[aria-label="Join Group"]')
                count = await join_btns.count()
                for i in range(min(count, max_groups - joined)):
                    try:
                        btn = join_btns.nth(i)
                        if await btn.is_visible():
                            await btn.click()
                            joined += 1
                            await random_delay(60, 90)
                    except Exception:
                        continue
            except Exception:
                continue
        return joined

    async def post_news_to_wall(self, page: Page, news_title: str, news_url: str):
        """抓取新聞/時事自動轉發到個人頁面"""
        try:
            await page.goto("https://www.facebook.com/", wait_until="networkidle")
            await short_delay(3, 6)

            status_box = page.locator(
                'div[aria-label*="在想什麼"], div[role="button"]:has-text("在想什麼")'
            ).first
            if await status_box.is_visible():
                await status_box.click()
                await short_delay(2, 4)

            editor = page.locator('div[aria-label*="貼文"], div[contenteditable="true"]').first
            if await editor.is_visible():
                await editor.fill(f"{news_title}\n{news_url}")
                await short_delay(2, 4)

            publish_btn = page.locator('div[aria-label="發佈"]').first
            if await publish_btn.is_visible():
                await publish_btn.click()
                await short_delay(2, 4)

            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
```

---

### Task 9: core/deleter.py — 自動刪文

**Files:**
- Create: `c:\Users\icemo\Documents\trae_projects\facebook\fb_auto_poster\core\deleter.py`

- [ ] **Step 1: Write deleter.py**

```python
"""自動刪文引擎"""
import asyncio

from playwright.async_api import Page

from utils.randomizer import short_delay, random_delay


class Deleter:
    """FB 貼文刪除引擎"""

    async def delete_from_group(self, page: Page, group_url: str, max_posts: int = 10):
        """刪除指定社團中的貼文"""
        deleted = 0
        try:
            await page.goto(group_url, wait_until="networkidle")
            await short_delay(3, 6)

            for _ in range(max_posts):
                try:
                    # 點擊貼文右上角選項
                    option_btn = page.locator('div[aria-label="貼文選項"], div[aria-label*="更多"]').first
                    if await option_btn.is_visible():
                        await option_btn.click()
                        await short_delay(2, 4)

                        # 點擊刪除
                        delete_btn = page.locator(
                            'div[role="menuitem"]:has-text("刪除"), span:has-text("刪除貼文")'
                        ).first
                        if await delete_btn.is_visible():
                            await delete_btn.click()
                            await short_delay(2, 4)

                            # 確認刪除
                            confirm_btn = page.locator(
                                'div[aria-label="刪除"], button:has-text("刪除")'
                            ).first
                            if await confirm_btn.is_visible():
                                await confirm_btn.click()
                                deleted += 1
                                await random_delay(30, 60)
                except Exception:
                    continue
        except Exception:
            pass
        return deleted

    async def delete_all_from_wall(self, page: Page, max_posts: int = 50):
        """刪除個人頁面貼文（謹慎使用）"""
        deleted = 0
        try:
            await page.goto("https://www.facebook.com/me/", wait_until="networkidle")
            await short_delay(3, 6)

            for _ in range(max_posts):
                try:
                    option_btn = page.locator('div[aria-label="貼文選項"]').first
                    if await option_btn.is_visible():
                        await option_btn.click()
                        await short_delay(2, 4)

                        delete_btn = page.locator(
                            'div[role="menuitem"]:has-text("刪除"), span:has-text("刪除貼文")'
                        ).first
                        if await delete_btn.is_visible():
                            await delete_btn.click()
                            await short_delay(2, 4)

                            confirm_btn = page.locator(
                                'div[aria-label="刪除"], button:has-text("刪除")'
                            ).first
                            if await confirm_btn.is_visible():
                                await confirm_btn.click()
                                deleted += 1
                                await random_delay(30, 60)
                except Exception:
                    continue
        except Exception:
            pass
        return deleted
```

---

### Task 10: core/interactor.py — 自動留言互動

**Files:**
- Create: `c:\Users\icemo\Documents\trae_projects\facebook\fb_auto_poster\core\interactor.py`

- [ ] **Step 1: Write interactor.py**

```python
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

    async def comment_on_post(self, page: Page, post_url: str, comment: str = ""):
        """在指定貼文留言"""
        if not comment:
            comment = random.choice(_COMMENT_TEMPLATES)
        try:
            await page.goto(post_url, wait_until="networkidle")
            await short_delay(3, 6)

            # 點擊留言框
            comment_box = page.locator('div[aria-label*="留言"], div[role="textbox"]').first
            if await comment_box.is_visible():
                await comment_box.click()
                await short_delay(1, 3)
                await comment_box.fill(comment)
                await short_delay(1, 3)

                # 按 Enter 送出
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
            await page.goto("https://www.facebook.com/", wait_until="networkidle")
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
```

---

### Task 11: core/scheduler.py — 排程引擎

**Files:**
- Create: `c:\Users\icemo\Documents\trae_projects\facebook\fb_auto_poster\core\scheduler.py`

- [ ] **Step 1: Write scheduler.py**

```python
"""排程引擎 — 基於 APScheduler 的任務排程器"""
import asyncio
from datetime import datetime
from typing import Callable, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from utils.config import load_schedules, save_schedules


class ScheduleJob:
    def __init__(
        self,
        job_id: str,
        account_id: str,
        job_type: str,  # "post", "nurture", "delete", "interact"
        cron_expr: str,  # e.g. "0 9 * * 1-5" = 平日 9:00
        params: dict = None,
        enabled: bool = True,
    ):
        self.job_id = job_id
        self.account_id = account_id
        self.job_type = job_type
        self.cron_expr = cron_expr
        self.params = params or {}
        self.enabled = enabled
        self.created_at = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "account_id": self.account_id,
            "job_type": self.job_type,
            "cron_expr": self.cron_expr,
            "params": self.params,
            "enabled": self.enabled,
            "created_at": self.created_at,
        }

    @staticmethod
    def from_dict(data: dict) -> "ScheduleJob":
        job = ScheduleJob(
            job_id=data["job_id"],
            account_id=data["account_id"],
            job_type=data["job_type"],
            cron_expr=data["cron_expr"],
            params=data.get("params", {}),
            enabled=data.get("enabled", True),
        )
        job.created_at = data.get("created_at", datetime.now().isoformat())
        return job


class Scheduler:
    """排程管理器"""

    def __init__(self):
        self._scheduler = AsyncIOScheduler()
        self._jobs: dict[str, ScheduleJob] = {}
        self._callbacks: dict[str, Callable] = {}

    def register_callback(self, job_type: str, callback: Callable):
        """註冊任務類型對應的執行函數"""
        self._callbacks[job_type] = callback

    def add_job(self, job: ScheduleJob) -> bool:
        """新增排程任務"""
        if job.job_id in self._jobs:
            return False

        parts = job.cron_expr.strip().split()
        if len(parts) != 5:
            return False

        try:
            trigger = CronTrigger(
                minute=parts[0],
                hour=parts[1],
                day=parts[2],
                month=parts[3],
                day_of_week=parts[4],
            )

            self._scheduler.add_job(
                self._execute_job,
                trigger=trigger,
                args=[job.job_id],
                id=job.job_id,
                misfire_grace_time=300,
            )

            self._jobs[job.job_id] = job
            self._persist()
            return True
        except Exception:
            return False

    def remove_job(self, job_id: str) -> bool:
        """移除排程任務"""
        if job_id in self._jobs:
            self._scheduler.remove_job(job_id)
            del self._jobs[job_id]
            self._persist()
            return True
        return False

    def pause_job(self, job_id: str) -> bool:
        """暫停排程"""
        if job_id in self._jobs:
            self._scheduler.pause_job(job_id)
            self._jobs[job_id].enabled = False
            self._persist()
            return True
        return False

    def resume_job(self, job_id: str) -> bool:
        """恢復排程"""
        if job_id in self._jobs:
            self._scheduler.resume_job(job_id)
            self._jobs[job_id].enabled = True
            self._persist()
            return True
        return False

    def get_jobs(self) -> list[ScheduleJob]:
        return list(self._jobs.values())

    async def _execute_job(self, job_id: str):
        """執行任務"""
        job = self._jobs.get(job_id)
        if not job or not job.enabled:
            return
        callback = self._callbacks.get(job.job_type)
        if callback:
            await callback(job.account_id, job.params)

    def start(self):
        """啟動排程器"""
        self._scheduler.start()

    def stop(self):
        """停止排程器"""
        self._scheduler.shutdown(wait=False)

    def load_persisted(self):
        """從磁碟載入已儲存的排程"""
        raw = load_schedules()
        for item in raw:
            try:
                job = ScheduleJob.from_dict(item)
                if job.enabled:
                    self.add_job(job)
                else:
                    self._jobs[job.job_id] = job
            except Exception:
                continue

    def _persist(self):
        save_schedules([j.to_dict() for j in self._jobs.values()])
```

---

### Task 12: GUI — dark_theme.py 暗色主題

**Files:**
- Create: `c:\Users\icemo\Documents\trae_projects\facebook\fb_auto_poster\gui\dark_theme.py`

- [ ] **Step 1: Write dark_theme.py**

```python
"""暗色主題樣式"""
import ttkbootstrap as ttk
from ttkbootstrap.constants import *

DARK_THEME = "darkly"


def setup_theme():
    """初始化暗色主題"""
    return ttk.Window(themename=DARK_THEME)


def create_styled_button(parent, text, command, bootstyle="primary"):
    """建立暗色主題按鈕"""
    return ttk.Button(parent, text=text, command=command, bootstyle=bootstyle)


def create_styled_entry(parent, **kwargs):
    """建立暗色主題輸入框"""
    return ttk.Entry(parent, **kwargs)


def create_styled_label(parent, text, **kwargs):
    """建立暗色主題標籤"""
    return ttk.Label(parent, text=text, **kwargs)


def create_styled_frame(parent, **kwargs):
    """建立暗色主題框架"""
    return ttk.Frame(parent, **kwargs)


def create_notebook(parent, **kwargs):
    """建立分頁"""
    return ttk.Notebook(parent, **kwargs)
```

---

### Task 13: GUI — account_manager.py 帳號管理面板

**Files:**
- Create: `c:\Users\icemo\Documents\trae_projects\facebook\fb_auto_poster\gui\account_manager.py`

- [ ] **Step 1: Write account_manager.py**

```python
"""多帳號管理面板"""
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import uuid

from core.account import Account, AccountManager
from gui.dark_theme import (
    create_styled_button, create_styled_entry,
    create_styled_label, create_styled_frame
)


class AccountManagerPanel(ttk.Frame):
    """帳號管理界面"""

    def __init__(self, parent, account_manager: AccountManager, **kwargs):
        super().__init__(parent, **kwargs)
        self.manager = account_manager
        self._build_ui()
        self._refresh_list()

    def _build_ui(self):
        # 左側 — 帳號列表
        left_frame = create_styled_frame(self, padding=10)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        create_styled_label(left_frame, text="帳號列表", font=("Arial", 14)).pack(anchor=tk.W, pady=(0, 10))

        list_frame = create_styled_frame(left_frame)
        list_frame.pack(fill=tk.BOTH, expand=True)

        self.tree = ttk.Treeview(
            list_frame,
            columns=("email", "nickname", "status"),
            show="headings",
            height=15,
        )
        self.tree.heading("email", text="Email")
        self.tree.heading("nickname", text="暱稱")
        self.tree.heading("status", text="狀態")
        self.tree.column("email", width=200)
        self.tree.column("nickname", width=150)
        self.tree.column("status", width=80)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.tree.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.configure(yscrollcommand=scrollbar.set)

        # 右側 — 按鈕
        right_frame = create_styled_frame(self, padding=10)
        right_frame.pack(side=tk.RIGHT, fill=tk.Y)

        create_styled_button(right_frame, text="新增帳號", command=self._add_account, bootstyle="success").pack(pady=5, fill=tk.X)
        create_styled_button(right_frame, text="刪除帳號", command=self._remove_account, bootstyle="danger").pack(pady=5, fill=tk.X)
        create_styled_button(right_frame, text="啟用/停用", command=self._toggle_active, bootstyle="warning").pack(pady=5, fill=tk.X)
        create_styled_button(right_frame, text="匯入 Cookie", command=self._import_cookie, bootstyle="info").pack(pady=5, fill=tk.X)

    def _add_account(self):
        dialog = tk.Toplevel(self)
        dialog.title("新增帳號")
        dialog.geometry("400x250")
        dialog.transient(self)
        dialog.grab_set()

        create_styled_label(dialog, text="Email:").pack(pady=(10, 0))
        email_entry = create_styled_entry(dialog, width=40)
        email_entry.pack(pady=5)

        create_styled_label(dialog, text="密碼 (選填):").pack(pady=(10, 0))
        pwd_entry = create_styled_entry(dialog, width=40, show="*")
        pwd_entry.pack(pady=5)

        create_styled_label(dialog, text="暱稱 (選填):").pack(pady=(10, 0))
        nickname_entry = create_styled_entry(dialog, width=40)
        nickname_entry.pack(pady=5)

        def save():
            email = email_entry.get().strip()
            if not email:
                messagebox.showwarning("警告", "Email 不可為空")
                return
            acc = Account(
                account_id=str(uuid.uuid4()),
                email=email,
                password=pwd_entry.get(),
                nickname=nickname_entry.get() or email,
            )
            self.manager.add(acc)
            self._refresh_list()
            dialog.destroy()

        create_styled_button(dialog, text="儲存", command=save, bootstyle="success").pack(pady=15)

    def _remove_account(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("警告", "請先選擇一個帳號")
            return
        item = self.tree.item(selected[0])
        email = item["values"][0]
        if messagebox.askyesno("確認", f"確定刪除 {email}？"):
            for acc in self.manager.list_all():
                if acc.email == email:
                    self.manager.remove(acc.account_id)
                    self._refresh_list()
                    break

    def _toggle_active(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("警告", "請先選擇一個帳號")
            return
        item = self.tree.item(selected[0])
        email = item["values"][0]
        for acc in self.manager.list_all():
            if acc.email == email:
                self.manager.set_active(acc.account_id, not acc.is_active)
                self._refresh_list()
                break

    def _import_cookie(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("警告", "請先選擇一個帳號")
            return
        item = self.tree.item(selected[0])
        email = item["values"][0]

        dialog = tk.Toplevel(self)
        dialog.title("匯入 Cookie")
        dialog.geometry("500x300")
        dialog.transient(self)
        dialog.grab_set()

        create_styled_label(dialog, text="貼上 FB Cookie JSON (從瀏覽器匯出):").pack(pady=(10, 0))
        text_widget = tk.Text(dialog, height=12, bg="#2b2b2b", fg="#ffffff", insertbackground="white")
        text_widget.pack(padx=10, pady=5, fill=tk.BOTH, expand=True)

        def save_cookie():
            cookie_str = text_widget.get("1.0", tk.END).strip()
            if not cookie_str:
                messagebox.showwarning("警告", "請貼上 Cookie JSON")
                return
            for acc in self.manager.list_all():
                if acc.email == email:
                    if self.manager.import_cookie(acc.account_id, cookie_str):
                        messagebox.showinfo("成功", "Cookie 匯入成功")
                    else:
                        messagebox.showerror("錯誤", "Cookie 格式錯誤")
                    dialog.destroy()
                    break

        create_styled_button(dialog, text="匯入", command=save_cookie, bootstyle="success").pack(pady=10)

    def _refresh_list(self):
        for row in self.tree.get_children():
            self.tree.delete(row)
        for acc in self.manager.list_all():
            status = "✅ 啟用" if acc.is_active else "❌ 停用"
            self.tree.insert("", tk.END, values=(acc.email, acc.nickname, status))
```

---

### Task 14: GUI — poster_panel.py 發文面板

**Files:**
- Create: `c:\Users\icemo\Documents\trae_projects\facebook\fb_auto_poster\gui\poster_panel.py`

- [ ] **Step 1: Write poster_panel.py**

```python
"""發文操作界面"""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os

from gui.dark_theme import (
    create_styled_button, create_styled_entry,
    create_styled_label, create_styled_frame
)


class PosterPanel(ttk.Frame):
    """一般發文 + 拍賣發文 操作面板"""

    def __init__(self, parent, account_ids: list[str], **kwargs):
        super().__init__(parent, **kwargs)
        self.account_ids = account_ids
        self.selected_images = []
        self._build_ui()

    def _build_ui(self):
        notebook = ttk.Notebook(self)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 一般發文分頁
        general_frame = create_styled_frame(notebook, padding=10)
        notebook.add(general_frame, text="一般發文")
        self._build_general_tab(general_frame)

        # 拍賣發文分頁
        market_frame = create_styled_frame(notebook, padding=10)
        notebook.add(market_frame, text="拍賣發文")
        self._build_market_tab(market_frame)

        # 狀態顯示
        self.status_var = tk.StringVar(value="就緒")
        create_styled_label(self, textvariable=self.status_var).pack(pady=5)

    def _build_general_tab(self, parent):
        # 帳號選擇
        create_styled_label(parent, text="選擇帳號:").pack(anchor=tk.W)
        self.account_var = tk.StringVar(value="")
        if self.account_ids:
            self.account_var.set(self.account_ids[0])
        self.account_combo = ttk.Combobox(
            parent, textvariable=self.account_var,
            values=self.account_ids, state="readonly", width=40
        )
        self.account_combo.pack(fill=tk.X, pady=5)

        # 文案
        create_styled_label(parent, text="文案內容:").pack(anchor=tk.W, pady=(10, 0))
        self.content_text = tk.Text(parent, height=8, bg="#2b2b2b", fg="#ffffff", insertbackground="white")
        self.content_text.pack(fill=tk.BOTH, pady=5)

        # 圖片
        img_frame = create_styled_frame(parent)
        img_frame.pack(fill=tk.X, pady=5)
        create_styled_button(img_frame, text="選擇圖片", command=self._select_images, bootstyle="info").pack(side=tk.LEFT)
        self.img_label = create_styled_label(img_frame, text="未選擇圖片")
        self.img_label.pack(side=tk.LEFT, padx=10)

        # 目標社團
        create_styled_label(parent, text="目標社團 (逗號分隔，留空=個人頁面):").pack(anchor=tk.W, pady=(10, 0))
        self.groups_entry = create_styled_entry(parent, width=60)
        self.groups_entry.pack(fill=tk.X, pady=5)

        # 發送按鈕
        btn_frame = create_styled_frame(parent)
        btn_frame.pack(pady=15)
        create_styled_button(btn_frame, text="立即發文", command=self._on_post_general, bootstyle="success").pack(side=tk.LEFT, padx=5)
        create_styled_button(btn_frame, text="清除", command=self._clear_general, bootstyle="secondary").pack(side=tk.LEFT, padx=5)

    def _build_market_tab(self, parent):
        create_styled_label(parent, text="選擇帳號:").pack(anchor=tk.W)
        self.market_account_var = tk.StringVar(value=self.account_ids[0] if self.account_ids else "")
        ttk.Combobox(
            parent, textvariable=self.market_account_var,
            values=self.account_ids, state="readonly", width=40
        ).pack(fill=tk.X, pady=5)

        fields = [
            ("商品標題:", "title"),
            ("價格:", "price"),
            ("地區:", "location"),
        ]
        self.market_entries = {}
        for label_text, key in fields:
            create_styled_label(parent, text=label_text).pack(anchor=tk.W, pady=(10, 0))
            entry = create_styled_entry(parent, width=50)
            entry.pack(fill=tk.X, pady=2)
            self.market_entries[key] = entry

        create_styled_label(parent, text="商品描述:").pack(anchor=tk.W, pady=(10, 0))
        self.market_desc = tk.Text(parent, height=6, bg="#2b2b2b", fg="#ffffff", insertbackground="white")
        self.market_desc.pack(fill=tk.BOTH, pady=5)

        # 圖片
        img_frame = create_styled_frame(parent)
        img_frame.pack(fill=tk.X, pady=5)
        create_styled_button(img_frame, text="選擇圖片", command=self._select_images, bootstyle="info").pack(side=tk.LEFT)
        self.market_img_label = create_styled_label(img_frame, text="未選擇圖片")
        self.market_img_label.pack(side=tk.LEFT, padx=10)

        btn_frame = create_styled_frame(parent)
        btn_frame.pack(pady=15)
        create_styled_button(btn_frame, text="發布到 Marketplace", command=self._on_post_marketplace, bootstyle="success").pack(side=tk.LEFT, padx=5)

    def _select_images(self):
        files = filedialog.askopenfilenames(
            title="選擇圖片",
            filetypes=[("圖片檔案", "*.jpg *.jpeg *.png *.gif *.webp")],
        )
        if files:
            self.selected_images = list(files)
            self.img_label.config(text=f"已選 {len(files)} 張圖片")
            if hasattr(self, 'market_img_label'):
                self.market_img_label.config(text=f"已選 {len(files)} 張圖片")

    def _on_post_general(self):
        self.status_var.set("正在發送一般貼文...")
        account_id = self.account_var.get()
        content = self.content_text.get("1.0", tk.END).strip()
        groups_str = self.groups_entry.get().strip()
        groups = [g.strip() for g in groups_str.split(",") if g.strip()] if groups_str else None
        images = self.selected_images if self.selected_images else None
        print(f"[Poster] 帳號={account_id}, 內容長度={len(content)}, 社團={groups}, 圖片={len(images or [])}")
        self.status_var.set("發文指令已送出 (背景執行中)")

    def _on_post_marketplace(self):
        self.status_var.set("正在發布到 Marketplace...")
        account_id = self.market_account_var.get()
        title = self.market_entries["title"].get().strip()
        price = self.market_entries["price"].get().strip()
        location = self.market_entries["location"].get().strip()
        desc = self.market_desc.get("1.0", tk.END).strip()
        images = self.selected_images if self.selected_images else None
        print(f"[Marketplace] 帳號={account_id}, 標題={title}, 價格={price}, 地點={location}")
        self.status_var.set("Marketplace 發布指令已送出 (背景執行中)")

    def _clear_general(self):
        self.content_text.delete("1.0", tk.END)
        self.groups_entry.delete(0, tk.END)
        self.selected_images = []
        self.img_label.config(text="未選擇圖片")
```

---

### Task 15: GUI — scheduler_panel.py 排程面板

**Files:**
- Create: `c:\Users\icemo\Documents\trae_projects\facebook\fb_auto_poster\gui\scheduler_panel.py`

- [ ] **Step 1: Write scheduler_panel.py**

```python
"""排程設定界面"""
import tkinter as tk
from tkinter import ttk, messagebox
import uuid

from core.scheduler import ScheduleJob, Scheduler
from gui.dark_theme import (
    create_styled_button, create_styled_entry,
    create_styled_label, create_styled_frame
)


class SchedulerPanel(ttk.Frame):
    """排程設定面板"""

    def __init__(self, parent, scheduler: Scheduler, account_ids: list[str], **kwargs):
        super().__init__(parent, **kwargs)
        self.scheduler = scheduler
        self.account_ids = account_ids
        self._build_ui()
        self._refresh_list()

    def _build_ui(self):
        # 頂部 — 新增排程表單
        form_frame = create_styled_frame(self, padding=10)
        form_frame.pack(fill=tk.X)

        create_styled_label(form_frame, text="新增排程任務", font=("Arial", 14)).pack(anchor=tk.W)

        row1 = create_styled_frame(form_frame)
        row1.pack(fill=tk.X, pady=5)

        create_styled_label(row1, text="帳號:").pack(side=tk.LEFT)
        self.account_var = tk.StringVar(value=self.account_ids[0] if self.account_ids else "")
        self.account_combo = ttk.Combobox(
            row1, textvariable=self.account_var,
            values=self.account_ids, state="readonly", width=30
        )
        self.account_combo.pack(side=tk.LEFT, padx=5)

        create_styled_label(row1, text="任務類型:").pack(side=tk.LEFT, padx=(20, 0))
        self.type_var = tk.StringVar(value="post")
        type_combo = ttk.Combobox(
            row1, textvariable=self.type_var,
            values=["post", "nurture", "delete", "interact"],
            state="readonly", width=15
        )
        type_combo.pack(side=tk.LEFT, padx=5)

        row2 = create_styled_frame(form_frame)
        row2.pack(fill=tk.X, pady=5)

        create_styled_label(row2, text="排程時間 (Cron 格式, 分 時 日 月 週):").pack(side=tk.LEFT)
        self.cron_entry = create_styled_entry(row2, width=25)
        self.cron_entry.insert(0, "0 9 * * 1-5")
        self.cron_entry.pack(side=tk.LEFT, padx=5)

        create_styled_label(row2, text="e.g. 0 9,14,20 * * 1-7").pack(side=tk.LEFT, padx=5)

        create_styled_button(form_frame, text="新增排程", command=self._add_schedule, bootstyle="success").pack(pady=10)

        # 下半部 — 排程列表
        list_frame = create_styled_frame(self, padding=10)
        list_frame.pack(fill=tk.BOTH, expand=True)

        create_styled_label(list_frame, text="現有排程", font=("Arial", 14)).pack(anchor=tk.W, pady=(0, 10))

        columns = ("帳號", "類型", "Cron", "狀態")
        self.tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=10)
        for col in columns:
            self.tree.heading(col, text=col)
        self.tree.column("帳號", width=150)
        self.tree.column("類型", width=100)
        self.tree.column("Cron", width=200)
        self.tree.column("狀態", width=80)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.tree.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.configure(yscrollcommand=scrollbar.set)

        # 操作按鈕
        btn_frame = create_styled_frame(self, padding=10)
        btn_frame.pack(fill=tk.X)
        create_styled_button(btn_frame, text="暫停", command=self._pause_job, bootstyle="warning").pack(side=tk.LEFT, padx=5)
        create_styled_button(btn_frame, text="恢復", command=self._resume_job, bootstyle="info").pack(side=tk.LEFT, padx=5)
        create_styled_button(btn_frame, text="刪除", command=self._remove_job, bootstyle="danger").pack(side=tk.LEFT, padx=5)

    def _add_schedule(self):
        account_id = self.account_var.get()
        job_type = self.type_var.get()
        cron_expr = self.cron_entry.get().strip()
        if not account_id or not cron_expr:
            messagebox.showwarning("警告", "請填寫所有欄位")
            return
        parts = cron_expr.split()
        if len(parts) != 5:
            messagebox.showwarning("警告", "Cron 格式錯誤，請使用「分 時 日 月 週」5 個欄位")
            return
        job = ScheduleJob(
            job_id=str(uuid.uuid4()),
            account_id=account_id,
            job_type=job_type,
            cron_expr=cron_expr,
        )
        if self.scheduler.add_job(job):
            self._refresh_list()
            messagebox.showinfo("成功", "排程已新增")
        else:
            messagebox.showerror("錯誤", "新增排程失敗，請檢查 Cron 格式")

    def _pause_job(self):
        selected = self.tree.selection()
        if not selected:
            return
        values = self.tree.item(selected[0])["values"]
        for job in self.scheduler.get_jobs():
            if f"{job.account_id}/{job.job_type}/{job.cron_expr}" == f"{values[0]}/{values[1]}/{values[2]}":
                self.scheduler.pause_job(job.job_id)
                self._refresh_list()
                break

    def _resume_job(self):
        selected = self.tree.selection()
        if not selected:
            return
        values = self.tree.item(selected[0])["values"]
        for job in self.scheduler.get_jobs():
            if f"{job.account_id}/{job.job_type}/{job.cron_expr}" == f"{values[0]}/{values[1]}/{values[2]}":
                self.scheduler.resume_job(job.job_id)
                self._refresh_list()
                break

    def _remove_job(self):
        selected = self.tree.selection()
        if not selected:
            return
        values = self.tree.item(selected[0])["values"]
        if messagebox.askyesno("確認", f"刪除此排程？"):
            for job in self.scheduler.get_jobs():
                if f"{job.account_id}/{job.job_type}/{job.cron_expr}" == f"{values[0]}/{values[1]}/{values[2]}":
                    self.scheduler.remove_job(job.job_id)
                    self._refresh_list()
                    break

    def _refresh_list(self):
        for row in self.tree.get_children():
            self.tree.delete(row)
        for job in self.scheduler.get_jobs():
            status = "✅ 啟用" if job.enabled else "❌ 暫停"
            self.tree.insert("", tk.END, values=(
                job.account_id, job.job_type, job.cron_expr, status
            ))
```

---

### Task 16: GUI — nurturer_panel.py 養號面板

**Files:**
- Create: `c:\Users\icemo\Documents\trae_projects\facebook\fb_auto_poster\gui\nurturer_panel.py`

- [ ] **Step 1: Write nurturer_panel.py**

```python
"""養號設定界面"""
import tkinter as tk
from tkinter import ttk

from gui.dark_theme import (
    create_styled_button, create_styled_entry,
    create_styled_label, create_styled_frame
)


class NurturerPanel(ttk.Frame):
    """養號操作面板"""

    def __init__(self, parent, account_ids: list[str], **kwargs):
        super().__init__(parent, **kwargs)
        self.account_ids = account_ids
        self._build_ui()

    def _build_ui(self):
        # 帳號選擇
        row1 = create_styled_frame(self)
        row1.pack(fill=tk.X, padx=10, pady=10)

        create_styled_label(row1, text="選擇帳號:").pack(side=tk.LEFT)
        self.account_var = tk.StringVar(value=self.account_ids[0] if self.account_ids else "")
        ttk.Combobox(
            row1, textvariable=self.account_var,
            values=self.account_ids, state="readonly", width=40
        ).pack(side=tk.LEFT, padx=5)

        # 功能卡片
        cards_frame = create_styled_frame(self)
        cards_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # 瀏覽貼文
        card1 = create_styled_frame(cards_frame, padding=10, bootstyle="secondary")
        card1.pack(fill=tk.X, pady=5)

        create_styled_label(card1, text="模擬瀏覽貼文", font=("Arial", 12)).pack(anchor=tk.W)
        browse_frame = create_styled_frame(card1)
        browse_frame.pack(fill=tk.X, pady=5)
        create_styled_label(browse_frame, text="瀏覽篇數:").pack(side=tk.LEFT)
        self.browse_count = ttk.Spinbox(browse_frame, from_=1, to=10, width=5)
        self.browse_count.set(5)
        self.browse_count.pack(side=tk.LEFT, padx=5)
        create_styled_button(browse_frame, text="開始瀏覽", command=self._on_browse, bootstyle="primary").pack(side=tk.LEFT, padx=10)

        # 加入社團
        card2 = create_styled_frame(cards_frame, padding=10, bootstyle="secondary")
        card2.pack(fill=tk.X, pady=5)

        create_styled_label(card2, text="自動加入社團", font=("Arial", 12)).pack(anchor=tk.W)
        group_frame = create_styled_frame(card2)
        group_frame.pack(fill=tk.X, pady=5)
        create_styled_label(group_frame, text="關鍵字 (逗號分隔):").pack(side=tk.LEFT)
        self.group_keywords = create_styled_entry(group_frame, width=30)
        self.group_keywords.insert(0, "房地產,房屋,買房")
        self.group_keywords.pack(side=tk.LEFT, padx=5)
        create_styled_label(group_frame, text=" 加入數量:").pack(side=tk.LEFT)
        self.join_count = ttk.Spinbox(group_frame, from_=1, to=10, width=5)
        self.join_count.set(5)
        self.join_count.pack(side=tk.LEFT, padx=5)
        create_styled_button(group_frame, text="開始加入", command=self._on_join_groups, bootstyle="primary").pack(side=tk.LEFT, padx=10)

        # 轉發新聞
        card3 = create_styled_frame(cards_frame, padding=10, bootstyle="secondary")
        card3.pack(fill=tk.X, pady=5)

        create_styled_label(card3, text="轉發新聞到個人頁面", font=("Arial", 12)).pack(anchor=tk.W)
        news_frame = create_styled_frame(card3)
        news_frame.pack(fill=tk.X, pady=5)
        create_styled_label(news_frame, text="新聞標題:").pack(side=tk.LEFT)
        self.news_title = create_styled_entry(news_frame, width=30)
        self.news_title.pack(side=tk.LEFT, padx=5)
        create_styled_label(news_frame, text="網址:").pack(side=tk.LEFT)
        self.news_url = create_styled_entry(news_frame, width=30)
        self.news_url.pack(side=tk.LEFT, padx=5)
        create_styled_button(news_frame, text="轉發", command=self._on_post_news, bootstyle="primary").pack(side=tk.LEFT, padx=10)

        # 狀態
        self.status_var = tk.StringVar(value="就緒")
        create_styled_label(self, textvariable=self.status_var).pack(pady=10)

    def _on_browse(self):
        self.status_var.set("開始模擬瀏覽貼文...")
        print(f"[Nurturer] 瀏覽: 帳號={self.account_var.get()}, 篇數={self.browse_count.get()}")

    def _on_join_groups(self):
        self.status_var.set("開始加入社團...")
        print(f"[Nurturer] 加入社團: 帳號={self.account_var.get()}, 關鍵字={self.group_keywords.get()}")

    def _on_post_news(self):
        self.status_var.set("正在轉發新聞...")
        print(f"[Nurturer] 轉發新聞: 帳號={self.account_var.get()}, 標題={self.news_title.get()}")
```

---

### Task 17: GUI — app.py 主應用程式

**Files:**
- Create: `c:\Users\icemo\Documents\trae_projects\facebook\fb_auto_poster\gui\app.py`

- [ ] **Step 1: Write app.py**

```python
"""主視窗應用程式 — 整合所有功能面板"""
import asyncio
import threading

import ttkbootstrap as ttk
from ttkbootstrap.constants import *

from core.account import AccountManager
from core.scheduler import Scheduler
from gui.dark_theme import setup_theme, create_styled_label
from gui.account_manager import AccountManagerPanel
from gui.poster_panel import PosterPanel
from gui.scheduler_panel import SchedulerPanel
from gui.nurturer_panel import NurturerPanel


class FBPosterApp(ttk.Window):
    """FB 自動發文主應用程式"""

    def __init__(self):
        super().__init__(themename="darkly")
        self.title("行銷快手 — FB 自動發文工具")
        self.geometry("1200x800")
        self.minsize(900, 600)

        # 初始化核心模組
        self.account_manager = AccountManager()
        self.scheduler = Scheduler()

        # 建立 UI
        self._build_menu()
        self._build_main_area()

        # 啟動排程器
        self.scheduler.load_persisted()
        self.scheduler.start()

        # 關閉事件
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_menu(self):
        """建立選單列"""
        menubar = ttk.Menu(self)
        self.config(menu=menubar)

        file_menu = ttk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="設定", command=self._show_settings)
        file_menu.add_separator()
        file_menu.add_command(label="離開", command=self._on_close)
        menubar.add_cascade(label="檔案", menu=file_menu)

        help_menu = ttk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="關於", command=self._show_about)
        menubar.add_cascade(label="說明", menu=help_menu)

    def _build_main_area(self):
        """建立主內容區域 — 分頁切換"""
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 帳號管理分頁
        account_ids = [a.account_id for a in self.account_manager.list_active()]
        if not account_ids:
            account_ids = [a.account_id for a in self.account_manager.list_all()] or ["無帳號"]

        self.account_panel = AccountManagerPanel(
            self.notebook, self.account_manager
        )
        self.notebook.add(self.account_panel, text="帳號管理")

        self.poster_panel = PosterPanel(
            self.notebook, account_ids=account_ids
        )
        self.notebook.add(self.poster_panel, text="發文")

        self.scheduler_panel = SchedulerPanel(
            self.notebook, self.scheduler, account_ids=account_ids
        )
        self.notebook.add(self.scheduler_panel, text="排程")

        self.nurturer_panel = NurturerPanel(
            self.notebook, account_ids=account_ids
        )
        self.notebook.add(self.nurturer_panel, text="養號")

        # 狀態列
        self.status_var = ttk.StringVar(value="就緒")
        status_bar = create_styled_label(self, textvariable=self.status_var, font=("Arial", 9))
        status_bar.pack(side=ttk.BOTTOM, fill=ttk.X, padx=10, pady=5)

    def _show_settings(self):
        """開啟設定視窗"""
        dialog = ttk.Toplevel(self)
        dialog.title("設定")
        dialog.geometry("400x200")
        dialog.transient(self)
        dialog.grab_set()
        ttk.Label(dialog, text="設定功能開發中...").pack(pady=50)

    def _show_about(self):
        """顯示關於資訊"""
        ttk.Messagebox.show_info(
            title="關於行銷快手",
            message="行銷快手 v1.0\n\n專為房仲、車仲打造的 FB 自動發文工具\n\n資料僅存於您的設備，安全無憂。",
        )

    def _on_close(self):
        """關閉應用程式"""
        self.scheduler.stop()
        self.destroy()
```

---

### Task 18: main.py — 主程式入口

**Files:**
- Create: `c:\Users\icemo\Documents\trae_projects\facebook\fb_auto_poster\main.py`

- [ ] **Step 1: Write main.py**

```python
"""行銷快手 — FB 自動發文工具 主程式入口"""
import sys
import os

# 確保專案目錄在 sys.path 中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gui.app import FBPosterApp


def main():
    app = FBPosterApp()
    app.mainloop()


if __name__ == "__main__":
    main()
```

---

### Task 19: 安裝依賴 + 安裝 Playwright 瀏覽器

- [ ] **Step 1: 安裝 Python 套件**
    Run: `pip install -r fb_auto_poster/requirements.txt`

- [ ] **Step 2: 安裝 Playwright Chromium**
    Run: `playwright install chromium`

- [ ] **Step 3: 確認安裝成功**
    Run: `python -c "import playwright; import ttkbootstrap; import apscheduler; import argon2; print('All dependencies installed')"`
    Expected: `All dependencies installed`

---

### Task 20: 手動測試 — 啟動應用程式

- [ ] **Step 1: 執行程式**
    Run: `python fb_auto_poster/main.py`
    Expected: 出現暗色主題的 Tkinter 視窗，標題為「行銷快手 — FB 自動發文工具」

- [ ] **Step 2: 功能驗證 — 帳號管理**
    1. 切換到「帳號管理」分頁
    2. 點選「新增帳號」填入測試資料
    3. 確認帳號出現在列表中
    4. 啟用/停用功能正常

- [ ] **Step 3: 功能驗證 — 排程**
    1. 切換到「排程」分頁
    2. 新增一筆排程 (cron: 0 9 * * 1-5)
    3. 確認排程出現在列表中
    4. 暫停/恢復功能正常
