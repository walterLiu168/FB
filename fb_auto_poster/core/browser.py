"""Playwright 瀏覽器管理 + 進階反偵測引擎

指紋防護層級:
1. Chromium launch args — 關閉自動化標記
2. JS init script — 補丁 20+ 個 navigator/window 屬性
3. Canvas/WebGL 噪點 — 防止 canvas fingerprinting
4. 獨立 persistent profile — 每個帳號擁有獨立瀏覽器資料夾
5. 真實 Plugin/MimeType 清單 — 模擬真實 Chrome 外掛列表
6. 隨機螢幕解析度/色深/hardwareConcurrency
"""
import asyncio
import json
import os
import random
from typing import Optional

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from utils.randomizer import random_user_agent, random_viewport

# 註冊到足跡清理系統
from core.footprint_cleaner import register_browser_manager


# ── Chromium 反偵測啟動參數 ──
_LAUNCH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-features=IsolateOrigins,site-per-process,OptimizationHints",
    "--disable-site-isolation-trials",
    "--no-sandbox",
    "--disable-infobars",
    "--disable-dev-shm-usage",
    "--disable-setuid-sandbox",
    "--no-first-run",
    "--no-zygote",
    "--disable-gpu",
    "--disable-extensions",
    "--disable-component-extensions-with-background-pages",
    "--disable-default-apps",
    "--disable-sync",
    "--disable-background-networking",
    "--disable-client-side-phishing-detection",
    "--disable-component-update",
    "--disable-domain-reliability",
    "--disable-breakpad",
    "--disable-hang-monitor",
    "--disable-prompt-on-repost",
    "--disable-ipc-flooding-protection",
    "--password-store=basic",
    "--use-mock-keychain",
    "--enable-features=NetworkService,NetworkServiceInProcess",
    "--force-color-profile=srgb",
    "--metrics-recording-only",
    "--mute-audio",
]

# ── 核心反偵測 JS 注入腳本 ──
# 在每個頁面載入前執行，補丁 navigator/window/screen 等物件
_FINGERPRINT_PATCH = r"""
// ====== 反偵測指紋補丁 ======

// 1. 隱藏 webdriver 標記
Object.defineProperty(navigator, 'webdriver', { get: () => false });

// 2. 偽造 chrome 物件結構 (真實 Chrome 才有的屬性)
window.chrome = {
    app: { isInstalled: false },
    webstore: { onInstallStageChanged: {}, onDownloadProgress: {} },
    runtime: { platformOs: 'win', PlatformOs: {}, onConnect: {}, onMessage: {}, onConnectExternal: {}, onMessageExternal: {}, id: undefined }
};

// 3. 修復 plugins 陣列 — 模擬真實 Chrome 外掛
Object.defineProperty(navigator, 'plugins', {
    get: () => {
        const arr = [1, 2, 3, 4, 5];
        arr.item = i => arr[i];
        arr.namedItem = name => arr[0];
        arr.refresh = () => {};
        Object.setPrototypeOf(arr, PluginArray.prototype);
        return arr;
    }
});

// 4. 修復 mimeTypes
Object.defineProperty(navigator, 'mimeTypes', {
    get: () => {
        const arr = [
            { type: 'application/pdf', suffixes: 'pdf', description: '' },
            { type: 'text/pdf', suffixes: 'pdf', description: '' },
        ];
        arr.item = i => arr[i];
        arr.namedItem = name => arr[0];
        Object.setPrototypeOf(arr, MimeTypeArray.prototype);
        return arr;
    }
});

// 5. 修復 platform
Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });

// 6. 修復 hardwareConcurrency (真實電腦的 CPU 核心數)
const cores = [4, 8, 12, 16];
const hw = cores[Math.floor(Math.random() * cores.length)];
Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => hw });

// 7. 修復 deviceMemory
const mems = [4, 8, 16];
Object.defineProperty(navigator, 'deviceMemory', { get: () => mems[Math.floor(Math.random() * mems.length)] });

// 8. 修復 languages
Object.defineProperty(navigator, 'languages', { get: () => ['zh-TW', 'zh', 'en-US', 'en'] });

// 9. 修復 permissions
if (navigator.permissions && navigator.permissions.query) {
    const origQuery = navigator.permissions.query.bind(navigator.permissions);
    navigator.permissions.query = (parameters) => (
        parameters.name === 'notifications' ?
            Promise.resolve({ state: Notification.permission, onchange: null }) :
            origQuery(parameters)
    );
}

// 10. 修復 screen 物件 (防止透過螢幕解析度偵測)
const scrW = [1920, 1366, 1536, 1440][Math.floor(Math.random() * 4)];
const scrH = [1080, 768, 864, 900][Math.floor(Math.random() * 4)];
Object.defineProperty(screen, 'colorDepth', { get: () => 24 });
Object.defineProperty(screen, 'pixelDepth', { get: () => 24 });
Object.defineProperty(screen, 'width', { get: () => scrW });
Object.defineProperty(screen, 'height', { get: () => scrH });
Object.defineProperty(screen, 'availWidth', { get: () => scrW });
Object.defineProperty(screen, 'availHeight', { get: () => scrH - 40 });

// 11. 隱藏 automation 相關屬性
delete window.__nightmare;
delete window._phantom;
delete window.callPhantom;
delete window.Buffer;
delete window.emit;
delete window.spawn;

// 12. 修復 document 隱藏屬性
Object.defineProperty(document, 'hidden', { get: () => false });
Object.defineProperty(document, 'visibilityState', { get: () => 'visible' });

// 13. Canvas fingerprint 噪點注入
const origToDataURL = HTMLCanvasElement.prototype.toDataURL;
HTMLCanvasElement.prototype.toDataURL = function(type, ...args) {
    const ctx = this.getContext('2d');
    if (ctx) {
        const imageData = ctx.getImageData(0, 0, this.width, this.height);
        // 隨機微小噪點（肉眼不可見）
        for (let i = 0; i < imageData.data.length; i += 16) {
            imageData.data[i] = imageData.data[i] ^ (Math.random() * 2 | 0);
        }
        ctx.putImageData(imageData, 0, 0);
    }
    return origToDataURL.apply(this, [type, ...args]);
};

const origToBlob = HTMLCanvasElement.prototype.toBlob;
HTMLCanvasElement.prototype.toBlob = function(callback, type, ...args) {
    const ctx = this.getContext('2d');
    if (ctx) {
        const imageData = ctx.getImageData(0, 0, this.width, this.height);
        for (let i = 0; i < imageData.data.length; i += 16) {
            imageData.data[i] = imageData.data[i] ^ (Math.random() * 2 | 0);
        }
        ctx.putImageData(imageData, 0, 0);
    }
    return origToBlob.apply(this, [callback, type, ...args]);
};

// 14. WebGL 指紋噪點
const origGetParameter = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function(parameter) {
    // UNMASKED_VENDOR_WEBGL / UNMASKED_RENDERER_WEBGL → 偽造為常見 GPU
    if (parameter === 37445) {
        return 'Google Inc. (Intel)';
    }
    if (parameter === 37446) {
        const gpus = [
            'ANGLE (Intel, Intel(R) UHD Graphics 620 Direct3D11 vs_5_0 ps_5_0, D3D11)',
            'ANGLE (Intel, Intel(R) Iris Xe Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)',
            'ANGLE (NVIDIA, NVIDIA GeForce GTX 1650 Direct3D11 vs_5_0 ps_5_0, D3D11)',
        ];
        return gpus[Math.floor(Math.random() * gpus.length)];
    }
    return origGetParameter.call(this, parameter);
};

const origGetParameter2 = WebGL2RenderingContext.prototype.getParameter;
WebGL2RenderingContext.prototype.getParameter = function(parameter) {
    if (parameter === 37445) {
        return 'Google Inc. (Intel)';
    }
    if (parameter === 37446) {
        const gpus = [
            'ANGLE (Intel, Intel(R) UHD Graphics 620 Direct3D11 vs_5_0 ps_5_0, D3D11)',
            'ANGLE (Intel, Intel(R) Iris Xe Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)',
        ];
        return gpus[Math.floor(Math.random() * gpus.length)];
    }
    return origGetParameter2.call(this, parameter);
};

// 15. 修復 Intl 時區（已透過 context 設定，雙重確認）
if (window.Intl && Intl.DateTimeFormat) {
    const origResolved = Intl.DateTimeFormat.prototype.resolvedOptions;
    Intl.DateTimeFormat.prototype.resolvedOptions = function() {
        const opts = origResolved.call(this);
        opts.timeZone = 'Asia/Taipei';
        return opts;
    };
}

// 16. 修復 audioContext fingerprint
const origCreateAnalyser = AudioContext.prototype.createAnalyser;
if (origCreateAnalyser) {
    AudioContext.prototype.createAnalyser = function(...args) {
        const analyser = origCreateAnalyser.apply(this, args);
        const origGetFloatFrequencyData = analyser.getFloatFrequencyData;
        analyser.getFloatFrequencyData = function(array) {
            origGetFloatFrequencyData.call(this, array);
            // 注入微量噪點
            for (let i = 0; i < array.length; i++) {
                array[i] += (Math.random() - 0.5) * 1e-8;
            }
        };
        return analyser;
    };
}
"""


class BrowserManager:
    """管理多帳號的瀏覽器實例與 Context — 進階反偵測版"""

    def __init__(self):
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._contexts: dict[str, BrowserContext] = {}
        self._pages: dict[str, Page] = {}
        self._profile_dirs: dict[str, str] = {}  # account_id → user_data_dir
        self._headless = False
        self._data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

    async def start(self, headless: bool = False) -> None:
        """啟動瀏覽器"""
        self._headless = headless
        self._playwright = await async_playwright().start()

        if headless:
            # headless 模式需要額外參數來隱藏 headless 特徵
            extra_args = [
                "--headless=new",  # 新版 headless 更難偵測
                "--window-size=1920,1080",
            ]
        else:
            extra_args = []

        self._browser = await self._playwright.chromium.launch(
            headless=False,  # 不跑 headless，FB 對 headless 偵測非常嚴格
            args=_LAUNCH_ARGS + extra_args,
        )

        # 註冊到足跡清理系統
        register_browser_manager(self)

    async def create_context(self, account_id: str, cookie_str: str = "") -> BrowserContext:
        """為指定帳號建立獨立 Context — 含完整指紋偽裝

        每個帳號使用獨立的 persistent profile (user_data_dir)，
        模擬真實瀏覽器的持久化狀態，避免因「全新環境」被標記。
        """
        ua = random_user_agent()
        vp = random_viewport()

        # 建立帳號專屬的 persistent profile 目錄
        profile_dir = os.path.join(self._data_dir, "browser_profiles", account_id)
        os.makedirs(profile_dir, exist_ok=True)
        self._profile_dirs[account_id] = profile_dir

        # 建立 context（每個帳號獨立儲存 localStorage/sessionStorage/cookies）
        context = await self._browser.new_context(
            user_agent=ua,
            viewport=vp,
            locale="zh-TW",
            timezone_id="Asia/Taipei",
            permissions=["clipboard-read", "clipboard-write"],
            geolocation={"latitude": 25.0330, "longitude": 121.5654},  # 台北座標
            color_scheme="light",
            device_scale_factor=1,
            is_mobile=False,
            has_touch=False,
            java_script_enabled=True,
            bypass_csp=True,
            ignore_https_errors=True,
        )

        # 注入進階反偵測盾 (8-layer browser identity shield)
        # 每個帳號獨立指紋 — 同帳永遠相同，跨帳互異 (防農場偵測)
        from core.browser_shield import build_shield_script
        shield_script = build_shield_script(account_seed=account_id)
        await context.add_init_script(shield_script)

        # 載入已儲存的 Cookie 維持登入狀態
        if cookie_str:
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
        # 如果 context 不存在，自動嘗試恢復
        if account_id not in self._pages and account_id in self._contexts:
            page = await self._contexts[account_id].new_page()
            self._pages[account_id] = page
        return self._pages.get(account_id)

    async def get_context(self, account_id: str) -> BrowserContext:
        return self._contexts.get(account_id)

    async def new_page(self) -> Optional[Page]:
        """創建一個乾淨的臨時 Page（不綁定任何帳號）。

        適用於拜訪非 FB 網站（如 rakuya），共享瀏覽器的 stealth 已生效。
        """
        if not self._browser:
            return None
        try:
            ctx = await self._browser.new_context(
                user_agent=random_user_agent(),
                viewport=random_viewport(),
                locale="zh-TW",
                timezone_id="Asia/Taipei",
                bypass_csp=True,
            )
            # 注入反偵測腳本
            await ctx.add_init_script(_FINGERPRINT_PATCH)
            page = await ctx.new_page()
            # 把 ctx 存到 page 身上以便之後關閉
            page._temp_context = ctx
            return page
        except Exception:
            return None

    async def close_page(self, page: Page):
        """關閉臨時 page 及其 context"""
        try:
            ctx = getattr(page, '_temp_context', None)
            if ctx:
                await ctx.close()
        except Exception:
            pass

    async def close_context(self, account_id: str) -> None:
        """關閉指定帳號的 Context"""
        if account_id in self._contexts:
            # 先儲存 cookies
            await self._save_session(account_id)
            await self._contexts[account_id].close()
            del self._contexts[account_id]
            del self._pages[account_id]

    async def _save_session(self, account_id: str):
        """儲存 account context 的 cookies 到 profile 目錄"""
        context = self._contexts.get(account_id)
        if not context:
            return
        profile_dir = self._profile_dirs.get(account_id)
        if not profile_dir:
            return
        try:
            cookies = await context.cookies()
            cookie_path = os.path.join(profile_dir, "cookies.json")
            with open(cookie_path, "w", encoding="utf-8") as f:
                json.dump(cookies, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    async def _load_session(self, account_id: str) -> Optional[list]:
        """從 profile 目錄載入 cookies"""
        profile_dir = self._profile_dirs.get(account_id)
        if not profile_dir:
            return None
        cookie_path = os.path.join(profile_dir, "cookies.json")
        try:
            if os.path.exists(cookie_path):
                with open(cookie_path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return None

    async def export_cookies(self, account_id: str, storage_path: str) -> None:
        """匯出指定帳號的 cookies 到檔案"""
        context = self._contexts.get(account_id)
        if context:
            cookies = await context.cookies()
            os.makedirs(os.path.dirname(storage_path), exist_ok=True)
            with open(storage_path, "w", encoding="utf-8") as f:
                json.dump(cookies, f, ensure_ascii=False, indent=2)

    def get_profile_dir(self, account_id: str) -> str:
        """取得帳號的 profile 目錄路徑"""
        return self._profile_dirs.get(account_id, "")

    # ── 足跡輪換：每小時清除追蹤資料 ──

    # Facebook 登入相關的關鍵 cookie（必須保留才能維持登入）
    _LOGIN_COOKIES = {"c_user", "xs", "fr", "datr", "sb", "wd", "presence"}

    async def rotate_footprint(self, account_id: str) -> dict:
        """每小時輪換足跡 — 清除追蹤資料 + 更換指紋

        保留登入 cookies，清除：
        - 非登入 cookies（tracking pixels、_fbp、_fbc 等）
        - localStorage / sessionStorage
        - 快取（Cache API、Service Worker）
        - IndexedDB
        - 更換 User-Agent 和 Viewport

        Returns: {"cleared_cookies": int, "storage_cleared": bool}
        """
        result = {"cleared_cookies": 0, "storage_cleared": False}

        context = self._contexts.get(account_id)
        if not context:
            return result

        page = self._pages.get(account_id)

        try:
            # 1. 清除 localStorage + sessionStorage
            if page:
                await page.evaluate("""
                    try { localStorage.clear(); } catch(e) {}
                    try { sessionStorage.clear(); } catch(e) {}
                """)
                result["storage_cleared"] = True

            # 2. 清除 Cache API / IndexedDB / Service Worker
            if page:
                await page.evaluate("""
                    try {
                        caches.keys().then(keys => keys.forEach(k => caches.delete(k)));
                    } catch(e) {}
                    try {
                        indexedDB.databases().then(dbs => dbs.forEach(db => indexedDB.deleteDatabase(db.name)));
                    } catch(e) {}
                    try {
                        navigator.serviceWorker.getRegistrations().then(regs =>
                            regs.forEach(r => r.unregister())
                        );
                    } catch(e) {}
                """)

            # 3. 取得現有 cookies，只保留登入相關的
            all_cookies = await context.cookies()
            kept = []
            cleared = 0
            for c in all_cookies:
                if c["name"] in self._LOGIN_COOKIES:
                    kept.append(c)
                else:
                    cleared += 1

            result["cleared_cookies"] = cleared

            # 4. 儲存登入 cookies
            if account_id in self._profile_dirs:
                cookie_path = os.path.join(self._profile_dirs[account_id], "cookies.json")
                with open(cookie_path, "w", encoding="utf-8") as f:
                    json.dump(kept, f, ensure_ascii=False, indent=2)

            # 5. 關閉舊 context
            if page:
                await page.close()
            await context.close()

            # 6. 建立全新 context（新 UA、新 viewport、新 fingerprint）
            cookies_json = json.dumps(kept)
            await self.create_context(account_id, cookie_str=cookies_json)

            # 7. 開啟 FB 首頁，讓新 context 載入登入 cookies
            new_page = self._pages.get(account_id)
            if new_page:
                await new_page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=60000)
                await asyncio.sleep(3)

            result["footprint_rotated"] = True

        except Exception as e:
            result["error"] = str(e)

        return result

    async def stop(self) -> None:
        """關閉瀏覽器（會自動儲存所有 session）"""
        for account_id in list(self._contexts.keys()):
            await self._save_session(account_id)
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._contexts.clear()
        self._pages.clear()
