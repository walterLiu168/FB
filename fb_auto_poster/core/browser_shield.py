"""瀏覽器隱身盾 (Browser Identity Shield) — 進階反指紋辨識層

設計哲學：每層防護獨立運作，層層覆蓋 FB 常見 8 大偵測向量。
採用「穩定身份」(Stable Identity) 策略：同一瀏覽器實例保有固定指紋，
避免頻繁變動引起 FB 安全模組警覺。

防護向量：
  Layer 1 — 反 WebDriver 偵測 (navigator.webdriver / chrome 物件)
  Layer 2 — 視窗/螢幕偽裝 (outer/inner dimensions 不一致才像真瀏覽器)
  Layer 3 — 硬體指紋隨機化 (核心數/記憶體/GPU 從常態池中選用)
  Layer 4 — 外掛/字型偽裝 (PDF 外掛陣列 + 標準字型)
  Layer 5 — Canvas 靜態噪點 (每像素 R 通道 ±1，肉眼不可見)
  Layer 6 — WebGL 硬體遮蔽 (遮蓋 renderer/vendor 字串)
  Layer 7 — AudioContext 微量擾動 (±1e-7 偏移)
  Layer 8 — 時區/語言一致性 (Asia/Taipei + zh-TW 鏈)

與 browser.py 的差異：
  - 使用 {tag} 占位符注入隨機值 (compile-time randomization)
  - 穩定性：同實例不變指紋，跨重啟才換
  - 擴增 outerHeight/Width 偽裝 (原版缺乏)
  - WebGL 改為被動遮蓋 (僅軟體渲染時才偽造)
"""

# ── 硬體指紋參數池 (隨選擇一份，同實例穩定不變) ──
_HARDWARE_PROFILES = [
    {"cores": 4,  "memory": 4,  "gpu_vendor": "Google Inc. (Intel)",      "gpu_renderer": "ANGLE (Intel, Intel(R) UHD Graphics 620 Direct3D11 vs_5_0 ps_5_0, D3D11)"},
    {"cores": 4,  "memory": 8,  "gpu_vendor": "Google Inc. (Intel)",      "gpu_renderer": "ANGLE (Intel, Intel(R) Iris Xe Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)"},
    {"cores": 8,  "memory": 8,  "gpu_vendor": "Google Inc. (NVIDIA)",     "gpu_renderer": "ANGLE (NVIDIA, NVIDIA GeForce GTX 1650 Direct3D11 vs_5_0 ps_5_0, D3D11)"},
    {"cores": 8,  "memory": 16, "gpu_vendor": "Google Inc. (NVIDIA)",     "gpu_renderer": "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)"},
    {"cores": 12, "memory": 16, "gpu_vendor": "Google Inc. (AMD)",         "gpu_renderer": "ANGLE (AMD, AMD Radeon RX 6600 Direct3D11 vs_5_0 ps_5_0, D3D11)"},
    {"cores": 16, "memory": 32, "gpu_vendor": "Google Inc. (Intel)",      "gpu_renderer": "ANGLE (Intel, Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0, D3D11)"},
    {"cores": 8,  "memory": 16, "gpu_vendor": "Google Inc. (NVIDIA)",     "gpu_renderer": "ANGLE (NVIDIA, NVIDIA GeForce RTX 4060 Direct3D11 vs_5_0 ps_5_0, D3D11)"},
]

# ── 螢幕解析度池 ──
_DISPLAY_PROFILES = [
    (1920, 1080), (1366, 768), (1536, 864), (1440, 900),
    (1680, 1050), (2560, 1440), (1600, 900),
]

# ── 標準 Chrome PDF 外掛模擬陣列 ──
_PLUGIN_DEFS = [
    ("Chrome PDF Viewer", "internal-pdf-viewer", "Portable Document Format"),
    ("Chromium PDF Viewer", "internal-pdf-viewer", "Portable Document Format"),
    ("Microsoft Edge PDF Viewer", "internal-pdf-viewer", "Portable Document Format"),
    ("WebKit built-in PDF", "internal-pdf-viewer", "Portable Document Format"),
]

def _build_shield_script(tag: dict = None) -> str:
    """組建反偵測盾 JS 腳本。

    {tag} 占位符會在啟動時填入隨機值，同實例保持固定。
    """
    import random as _random
    hw = _random.choice(_HARDWARE_PROFILES)
    display = _random.choice(_DISPLAY_PROFILES)
    cores = tag.get("cores", hw["cores"]) if tag else hw["cores"]
    memory = tag.get("memory", hw["memory"]) if tag else hw["memory"]
    gpu_vendor = tag.get("gpu_vendor", hw["gpu_vendor"]) if tag else hw["gpu_vendor"]
    gpu_renderer = tag.get("gpu_renderer", hw["gpu_renderer"]) if tag else hw["gpu_renderer"]
    scr_w = tag.get("scr_w", display[0]) if tag else display[0]
    scr_h = tag.get("scr_h", display[1]) if tag else display[1]

    return f'''// Browser Identity Shield — 8-Layer Anti-Fingerprint
(function(){{
"use strict";
// ======== Layer 1: WebDriver 痕跡清除 ========
try {{ delete Object.getPrototypeOf(navigator).webdriver; }} catch(e){{}}
try {{
    Object.defineProperty(navigator, "webdriver", {{
        get: function(){{ return undefined; }},
        configurable: true
    }});
}} catch(e){{}}

// ======== Layer 2: Chrome Runtime 結構 ========
try {{
    if (!window.chrome) {{ window.chrome = {{}}; }}
    if (!window.chrome.runtime) {{
        window.chrome.runtime = {{
            OnInstalledReason: {{
                CHROME_UPDATE: "chrome_update",
                INSTALL: "install",
                SHARED_MODULE_UPDATE: "shared_module_update",
                UPDATE: "update"
            }},
            OnRestartRequiredReason: {{
                APP_UPDATE: "app_update",
                OS_UPDATE: "os_update",
                PERIODIC: "periodic"
            }},
            PlatformOs: {{
                ANDROID: "android", CROS: "cros", LINUX: "linux",
                MAC: "mac", OPENBSD: "openbsd", WIN: "win"
            }},
            connect: function(){{ return undefined; }},
            sendMessage: function(){{ return undefined; }}
        }};
    }}
    if (!window.chrome.app) {{
        window.chrome.app = {{
            isInstalled: false,
            InstallState: {{ DISABLED: "disabled", INSTALLED: "installed", NOT_INSTALLED: "not_installed" }},
            RunningState: {{ CANNOT_RUN: "cannot_run", READY_TO_RUN: "ready_to_run", RUNNING: "running" }},
            getDetails: function(){{ return null; }},
            getIsInstalled: function(){{ return false; }}
        }};
    }}
}} catch(e){{}}

// ======== Layer 3: 視窗與螢幕尺寸偽裝 ========
try {{
    var _iw = window.innerWidth || {scr_w};
    var _ih = window.innerHeight || {scr_h};
    Object.defineProperty(window, "outerWidth", {{ get: function(){{ return _iw + 16; }} }});
    Object.defineProperty(window, "outerHeight", {{ get: function(){{ return _ih + 87; }} }});
    Object.defineProperty(screen, "width", {{ get: function(){{ return {scr_w}; }} }});
    Object.defineProperty(screen, "height", {{ get: function(){{ return {scr_h}; }} }});
    Object.defineProperty(screen, "availWidth", {{ get: function(){{ return {scr_w}; }} }});
    Object.defineProperty(screen, "availHeight", {{ get: function(){{ return {scr_h} - 40; }} }});
    Object.defineProperty(screen, "colorDepth", {{ get: function(){{ return 24; }} }});
    Object.defineProperty(screen, "pixelDepth", {{ get: function(){{ return 24; }} }});
}} catch(e){{}}

// ======== Layer 4: 硬體參數 ========
try {{
    Object.defineProperty(navigator, "hardwareConcurrency", {{ get: function(){{ return {cores}; }} }});
    Object.defineProperty(navigator, "deviceMemory", {{ get: function(){{ return {memory}; }} }});
    Object.defineProperty(navigator, "platform", {{ get: function(){{ return "Win32"; }} }});
    Object.defineProperty(navigator, "maxTouchPoints", {{ get: function(){{ return 0; }} }});
}} catch(e){{}}

// ======== Layer 5: 語言鏈 ========
try {{
    Object.defineProperty(navigator, "language", {{ get: function(){{ return "zh-TW"; }} }});
    Object.defineProperty(navigator, "languages", {{ get: function(){{ return ["zh-TW","zh","en-US","en"]; }} }});
}} catch(e){{}}

// ======== Layer 6: PDF 外掛陣列 ========
try {{
    var _pdfItems = [
        {{ name: "Chrome PDF Viewer", filename: "internal-pdf-viewer", description: "Portable Document Format", length: 1 }},
        {{ name: "Chromium PDF Viewer", filename: "internal-pdf-viewer", description: "Portable Document Format", length: 1 }},
        {{ name: "Microsoft Edge PDF Viewer", filename: "internal-pdf-viewer", description: "Portable Document Format", length: 1 }},
        {{ name: "WebKit built-in PDF", filename: "internal-pdf-viewer", description: "Portable Document Format", length: 1 }}
    ];
    Object.defineProperty(navigator, "plugins", {{
        get: function(){{
            var p = Object.create(PluginArray.prototype);
            _pdfItems.forEach(function(d,i){{
                var pl = Object.create(Plugin.prototype);
                pl.name = d.name;
                pl.filename = d.filename;
                pl.description = d.description;
                pl.length = 1;
                p[i] = pl;
                p[d.name] = pl;
            }});
            Object.defineProperty(p, "length", {{ value: _pdfItems.length }});
            p.item = function(i){{ return _pdfItems[i] ? p : null; }};
            p.namedItem = function(n){{ return p[n] || null; }};
            p.refresh = function(){{}};
            return p;
        }},
        configurable: true
    }});
}} catch(e){{}}

// ======== Layer 7: Canvas / WebGL / Audio 噪點 ========
try {{
    var _noiseCanvas = false;
}} catch(e){{}}
// ... (見下方完整函式)

// ======== Layer 8: 時區與權限 ========
try {{
    if (window.Intl && Intl.DateTimeFormat) {{
        var _orig = Intl.DateTimeFormat.prototype.resolvedOptions;
        Intl.DateTimeFormat.prototype.resolvedOptions = function(){{
            var r = _orig.call(this);
            r.timeZone = "Asia/Taipei";
            return r;
        }};
    }}
    if (navigator.permissions && navigator.permissions.query) {{
        var _pq = navigator.permissions.query.bind(navigator.permissions);
        navigator.permissions.query = function(p){{
            if (p && p.name === "notifications") {{
                return Promise.resolve({{ state: Notification.permission || "default", onchange: null }});
            }}
            return _pq(p);
        }};
    }}
}} catch(e){{}}

// ======== 隱藏痕跡 ========
try {{
    document.hidden = false;
    Object.defineProperty(document, "visibilityState", {{ get: function(){{ return "visible"; }} }});
    delete window.__nightmare;
    delete window._phantom;
    delete window.callPhantom;
    delete window.Buffer;
    delete window.emit;
    delete window.spawn;
}} catch(e){{}}
}})();'''

# ── Canvas / WebGL / Audio 噪點注入 (獨立段落，Playwright addInitScript 會自動擷取) ──
_JS_CANVAS_NOISE = '''
// ===== Shield: Canvas Noise Layer =====
(function(){
    var _noisePixels = false;
    var _applyNoise = function(canvas){
        if (canvas.width < 2 || canvas.height < 2) return;
        try {
            var ctx = canvas.getContext("2d");
            if (!ctx) return;
            var area = canvas.width * canvas.height;
            if (area > 4000000) return; // 大圖跳過，避免效能問題
            var img = ctx.getImageData(0, 0, canvas.width, canvas.height);
            var d = img.data;
            for (var i = 0; i < d.length; i += 16) {
                d[i] = (d[i] + (1 - ((i >> 4) & 2))) & 255;
            }
            ctx.putImageData(img, 0, 0);
        } catch(e) {}
    };

    var _origToDataURL = HTMLCanvasElement.prototype.toDataURL;
    HTMLCanvasElement.prototype.toDataURL = function(){
        _applyNoise(this);
        return _origToDataURL.apply(this, arguments);
    };

    var _origToBlob = HTMLCanvasElement.prototype.toBlob;
    if (_origToBlob) {
        HTMLCanvasElement.prototype.toBlob = function(){
            _applyNoise(this);
            return _origToBlob.apply(this, arguments);
        };
    }

    // WebGL: 僅軟體渲染偽裝
    try {
        var _origGL = WebGLRenderingContext.prototype.getParameter;
        var _gpu_v = "REPLACE_GPU_VENDOR";
        var _gpu_r = "REPLACE_GPU_RENDERER";
        WebGLRenderingContext.prototype.getParameter = function(p){
            var raw = _origGL.call(this, p);
            if (p === 37445) { // UNMASKED_VENDOR_WEBGL
                return /swiftshader|software|llvmpipe/i.test(String(raw)) ? _gpu_v : raw;
            }
            if (p === 37446) { // UNMASKED_RENDERER_WEBGL
                return /swiftshader|software|llvmpipe/i.test(String(raw)) ? _gpu_r : raw;
            }
            return raw;
        };
        if (window.WebGL2RenderingContext) {
            var _origGL2 = WebGL2RenderingContext.prototype.getParameter;
            WebGL2RenderingContext.prototype.getParameter = function(p){
                var raw = _origGL2.call(this, p);
                if (p === 37445) return /swiftshader|software|llvmpipe/i.test(String(raw)) ? _gpu_v : raw;
                if (p === 37446) return /swiftshader|software|llvmpipe/i.test(String(raw)) ? _gpu_r : raw;
                return raw;
            };
        }
    } catch(e) {}

    // Audio: 微量偏移 (不影響聽感)
    try {
        var _origGCDC = AudioBuffer.prototype.getChannelData;
        AudioBuffer.prototype.getChannelData = function(){
            var arr = _origGCDC.apply(this, arguments);
            try {
                if (arr && arr.length > 0 && !arr._shielded) {
                    var _offset = 1.3e-7;
                    for (var j = 0; j < arr.length; j += 500) {
                        arr[j] = arr[j] + _offset;
                    }
                    Object.defineProperty(arr, "_shielded", { value: true });
                }
            } catch(e) {}
            return arr;
        };
    } catch(e) {}
})();
'''

def build_shield_script(profile_index: int = None, account_seed: str = None) -> str:
    """生成完整的反偵測 JS 腳本

    Args:
        profile_index: 硬體指紋編號 (None = 隨機)
        account_seed: 帳號種子 (字串) — 同帳號永遠得到相同指紋，不同帳號互異

    Returns:
        可直接傳入 page.add_init_script() 的 JS 字串
    """
    import random as _random
    if profile_index is None:
        if account_seed:
            # deterministic from account seed
            import hashlib
            h = hashlib.md5(account_seed.encode()).hexdigest()
            profile_index = int(h[:4], 16) % len(_HARDWARE_PROFILES)
        else:
            profile_index = _random.randint(0, len(_HARDWARE_PROFILES) - 1)
    
    hw = _HARDWARE_PROFILES[profile_index % len(_HARDWARE_PROFILES)]
    
    # display also deterministic from seed
    if account_seed:
        import hashlib
        h = hashlib.md5((account_seed + "disp").encode()).hexdigest()
        display = _DISPLAY_PROFILES[int(h[:4], 16) % len(_DISPLAY_PROFILES)]
    else:
        display = _random.choice(_DISPLAY_PROFILES)

    tag = {
        "cores": hw["cores"],
        "memory": hw["memory"],
        "gpu_vendor": hw["gpu_vendor"],
        "gpu_renderer": hw["gpu_renderer"],
        "scr_w": display[0],
        "scr_h": display[1],
    }

    shield = _build_shield_script(tag)
    
    # Per-seed canvas noise offset
    if account_seed:
        import hashlib
        noise_seed = int(hashlib.md5((account_seed + "noise").encode()).hexdigest()[:4], 16)
        # Replace canvas noise with seed-based variant
        canvas = _JS_CANVAS_NOISE.replace(
            "REPLACE_GPU_VENDOR", hw["gpu_vendor"]
        ).replace(
            "REPLACE_GPU_RENDERER", hw["gpu_renderer"]
        ).replace(
            "1.3e-7", f"{(1.0 + (noise_seed % 7)) * 1e-7:.2e}"  # per-seed audio offset
        ).replace(
            "16)", f"{16 + (noise_seed % 5)})"  # per-seed canvas stride
        )
    else:
        canvas = _JS_CANVAS_NOISE.replace("REPLACE_GPU_VENDOR", hw["gpu_vendor"]).replace("REPLACE_GPU_RENDERER", hw["gpu_renderer"])

    return shield + '\n' + canvas


async def apply_shield(page, profile_index: int = None) -> dict:
    """將反偵測盾注入 Playwright Page

    Args:
        page: Playwright Page 物件
        profile_index: 硬體指紋編號

    Returns:
        {"profile": int, "gpu": str, "display": str, "cores": int, "memory": int}
    """
    import random as _random
    idx = profile_index if profile_index is not None else _random.randint(0, len(_HARDWARE_PROFILES) - 1)
    hw = _HARDWARE_PROFILES[idx % len(_HARDWARE_PROFILES)]
    display = _random.choice(_DISPLAY_PROFILES)

    script = build_shield_script(idx)
    await page.add_init_script(script)

    return {
        "profile": idx,
        "gpu": hw["gpu_renderer"][:50],
        "display": f"{display[0]}x{display[1]}",
        "cores": hw["cores"],
        "memory": hw["memory"],
    }


def get_profile_count() -> int:
    """取得可用硬體指紋數量"""
    return len(_HARDWARE_PROFILES)
