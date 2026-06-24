# FB POSTER — Facebook 自動發文工具

專為房仲、車仲、電商賣家打造的 Facebook 自動發文桌面應用程式。支援多帳號管理、排程發文、AI 文案生成、網頁圖片爬取、自動養號、自動刪文、操作日誌追蹤、License 授權控管，以及**個人房屋網站一鍵上稿**。

---

## 目錄

- [系統需求](#系統需求)
- [快速安裝](#快速安裝)
- [專案結構](#專案結構)
- [功能總覽](#功能總覽)
- [Pro 模板系統](#pro-模板系統)
- [個人網站 (Vercel)](#個人網站-vercel)
- [Telegram Bot](#telegram-bot)
- [操作說明](#操作說明)
- [授權管理（管理員用）](#授權管理管理員用)
- [佈署給員工](#佈署給員工)
- [常見問題](#常見問題)
- [開發筆記](#開發筆記)

---

## 系統需求

| 項目 | 需求 |
|------|------|
| 作業系統 | Windows 10 / 11 (64-bit) |
| Python | 3.11 ~ 3.14 |
| 硬碟空間 | 約 500 MB（含 Playwright Chromium 瀏覽器） |
| 網路 | 需要連線到 Facebook |
| 可選 | [Ollama](https://ollama.ai/) — 本地 AI 文案生成 |

---

## 快速安裝

### 1. 安裝 Python 虛擬環境

```powershell
# 建立虛擬環境
python -m venv C:\1\.venv

# 啟動虛擬環境
C:\1\.venv\Scripts\activate
```

### 2. 安裝依賴套件

```powershell
pip install -r fb_auto_poster/requirements.txt
```

### 3. 安裝 Playwright 瀏覽器

```powershell
python -m playwright install chromium
```

### 4. 啟動程式

雙擊 `launch.bat` 或執行：

```powershell
python -c "import sys; sys.path.insert(0, r'fb_auto_poster'); from gui.app import FBPosterApp; app = FBPosterApp(); app.mainloop()"
```

### 5. 放入授權檔案

首次啟動會顯示「找不到授權檔案」，請向管理員取得 `license.lic`，放到 `fb_auto_poster/data/` 目錄下，重開程式即可使用。

---

## 專案結構

```
facebook/                          ← 專案根目錄
├── launch.bat                     # Windows 啟動批次檔
├── .gitignore
│
├── fb_auto_poster/                # 主程式
│   ├── main.py                    # 主程式入口（含 License 檢查）
│   ├── telegram_bot.py            # Telegram Bot（獨立入口）
│   ├── license_generator.py       # License 授權產生器（管理員用）
│   ├── requirements.txt           # Python 依賴清單
│   │
│   ├── core/                      # 核心業務邏輯
│   │   ├── account.py             # 多帳號管理（Argon2 加密）
│   │   ├── ai_writer.py           # AI 文案生成（Ollama 在地端 LLM）
│   │   ├── auto_cleaner.py        # 自動刪文定時器
│   │   ├── browser.py             # Playwright 瀏覽器引擎（反偵測）
│   │   ├── deleter.py             # 自動刪文引擎
│   │   ├── fb_graph_poster.py     # Facebook Graph API 發文
│   │   ├── interactor.py          # 自動留言互動引擎
│   │   ├── license.py             # License 授權驗證（MAC 綁定）
│   │   ├── nurturer.py            # 養號引擎（模擬真人操作）
│   │   ├── poster.py              # 發文引擎
│   │   ├── pro_templates.py       # ★ Pro 模板引擎（房屋/土地/廠房）
│   │   ├── scheduler.py           # 排程引擎（APScheduler）
│   │   ├── scraper.py             # 網頁圖片爬取
│   │   ├── templates.py           # Header/Footer 範本管理
│   │   ├── tiktok_sign.py         # TikTok 簽名
│   │   ├── tiktok_slideshow.py    # TikTok 幻燈片
│   │   └── tiktok_uploader.py     # TikTok 上傳
│   │
│   ├── gui/                       # 圖形使用者介面（Tkinter 暗色主題）
│   │   ├── app.py                 # 主視窗應用程式
│   │   ├── account_manager.py     # 帳號管理面板
│   │   ├── agent_profile_dialog.py # ★ 營業員資料編輯器
│   │   ├── dark_theme.py          # 暗色主題設定
│   │   ├── fb_token_dialog.py     # FB Token 對話框
│   │   ├── log_panel.py           # 操作日誌檢視面板
│   │   ├── nurturer_panel.py      # 養號操作面板
│   │   ├── poster_panel.py        # ★ 發文操作面板（Pro 模板整合）
│   │   ├── pro_template_dialog.py # ★ Pro 模板編輯對話框
│   │   ├── scheduler_panel.py     # 排程設定面板
│   │   └── tiktok_settings.py     # TikTok 設定
│   │
│   ├── utils/                     # 通用工具
│   │   ├── config.py              # JSON 設定讀寫
│   │   ├── crypto.py              # Argon2 加密
│   │   ├── logger.py              # 操作日誌系統
│   │   ├── randomizer.py          # 隨機延遲/文字/指紋
│   │   └── secret_store.py        # 機密儲存
│   │
│   └── data/                      # 本地資料儲存
│       ├── accounts.json          # 帳號資料（加密）
│       ├── global_settings.json   # 應用程式設定
│       ├── pro_templates.json     # Pro 模板資料
│       ├── group_post_sets.json   # 社團組合設定
│       ├── templates.json         # Header/Footer 範本
│       ├── schedules.json         # 排程設定
│       ├── operations.log         # 操作日誌
│       ├── license.lic            # License 授權檔案
│       ├── pending_posts/         # Telegram 待發佇列
│       ├── pending_deletes.json   # 待刪除貼文
│       └── temp_images/           # 暫存爬取圖片
│
├── fb_property_site/              # ★ 個人房屋網站（Vercel 部署）
│   ├── index.html                 # 網站首頁（含 CSS/JS 一頁式）
│   ├── vercel.json                # Vercel 部署設定
│   ├── data/
│   │   ├── agent.json             # 營業員資料
│   │   └── listings.json          # 物件清單
│   └── images/                    # 物件照片
│
└── docs/
    └── superpowers/
        ├── specs/                 # 設計規格
        └── plans/                 # 實作計劃
```

---

## 功能總覽

### 1. 多帳號管理
- 新增/刪除/啟用停用 FB 帳號
- 支援 Cookie 匯入（從瀏覽器匯出 JSON）
- 密碼使用 Argon2 加密儲存
- 各帳號獨立設定（Header/Footer）

### 2. Pro 模板發文系統

| 模板 | 適用 | 欄位數 |
|------|------|--------|
| 🏠 房屋物件 | 住宅、公寓、大樓 | 11 欄（含格局/樓層/車位/朝向） |
| 🌍 土地 | 農地、建地、山坡地 | 7 欄（含使用分區/路寬） |
| 🏭 廠房 | 工廠、廠辦 | 9 欄（含建物坪數/土地坪數） |

- **一鍵生成**：貼 rakuya 等網址 → 自動提取 10+ 項資訊填入模板
- **自動切換模板**：根據物件標題關鍵字自動選擇房屋/土地/廠房
- **🧠 AI 生成介紹**：Ollama 根據已填欄位自動產出吸引人的文案
- **即時預覽**：所有欄位變更 → 預覽面板即時更新
- **模板編輯器**：可自訂模板文字、新增/刪除欄位、設定必填

### 3. 社團發文組合
- 儲存 3 組社團清單（Set 1 / Set 2 / Set 3）
- 選取組合 → 自動勾選對應社團
- 一鍵發送到多個社團

### 4. 營業員個人資料
- 編輯姓名、公司、電話、證號、LINE ID
- 上傳大頭照
- 設定社群連結（YouTube / Facebook / TikTok）
- 嵌入 YouTube 自我介紹影片

### 5. 個人網站 (Vercel)
- 房仲品牌頁面：自我介紹 + 社群按鈕 + 介紹影片
- 物件卡片網格：篩選房屋/土地/廠房 + 文字搜尋
- 點卡片展開詳細資料 + LINE 洽詢按鈕
- **發文自動上稿**：點立即發文 → FB 貼文 + 網站同步更新
- 免費託管於 Vercel

### 6. Telegram Bot
- 接收 JSON / 簡短格式的物件資訊
- 自動填入模板 → 寫入 pending queue
- 支援 `/templates`、`/pending`、`/post` 指令

### 7. AI 文案生成
- 串接在地端 [Ollama](https://ollama.ai/) LLM（如 Llama 3.2）
- Ollama 離線時自動使用模板文案 fallback
- 🧠 AI 生成介紹：根據物件欄位產出 2-3 句亮點文案

### 8. 圖片管理
- **本機選圖**：從電腦選取圖片
- **網址爬圖**：貼上物件網址自動抓取網頁圖片
- **圖片直鏈**：直接貼上 .jpg/.png 網址下載

### 9. Header/Footer 範本
- 每篇貼文自動附加頁首/頁尾（電話、LINE ID、網址等）
- 支援全域預設 + 各帳號獨立設定

### 10. 自動排程發文
- 使用 Cron 表達式設定時間
- 支援暫停/恢復/刪除排程
- 多帳號獨立排程

### 11. 自動養號
- 模擬瀏覽貼文（每天 1~10 篇）
- 隨機按讚、瀏覽留言
- 安全加入社團（每次 5 個，間隔 60 秒）
- 轉發新聞到個人頁面

### 12. 自動刪文
- 發文時設定倒數計時器（預設 24 小時後自動刪除）
- 支援排程每日定時清理過期貼文

### 13. 操作日誌
- 記錄所有發文/刪文/養號操作
- 日誌面板即時顯示（每 10 秒自動重新整理）

### 14. 反偵測/防鎖機制

| 機制 | 說明 |
|------|------|
| 隨機 User-Agent | 每次啟動隨機更換瀏覽器指紋 |
| 隨機 Viewport | 每次啟動隨機視窗尺寸 |
| WebDriver 隱藏 | 注入 JavaScript 隱藏自動化痕跡 |
| 隨機延遲 | 操作間隔 60~360 秒隨機等待 |
| 文案去重 | 每篇貼文附加隨機後綴/標籤 |
| 隨機圖片 | 圖片順序每次打亂 |
| 漸進式發文 | 社團分散時段發送，非一次性 |
| Cookie 登入 | 使用真實瀏覽器 Cookie，減少驗證 |

---

## Pro 模板系統

### 使用流程

```
① 選擇模板 → [🏠 房屋物件 ▼] [🌍 土地] [🏭 廠房]
② 貼網址 → 點「🤖 一鍵生成」
   → 自動提取欄位 + 自動切換模板 + 自動抓圖片
③ 精修介紹 → 點「🧠 AI 生成」
   → Ollama 根據已填欄位產出亮點文案
④ 檢查預覽 → 調整 Header/Footer
⑤ 選擇社團組合 → Set 1 / Set 2 / Set 3
⑥ 點「🚀 立即發文」
```

### 模板欄位

| 房屋物件 | 土地 | 廠房 |
|----------|------|------|
| 標題*、價格* | 標題*、價格* | 標題*、價格* |
| 地點、坪數 | 地點、土地坪數 | 地點、建物坪數 |
| 格局、類型 | 使用分區、路寬 | 土地坪數、類型 |
| 樓層、屋齡 | 介紹 (多行) | 樓層、屋齡 |
| 車位、朝向 | | 介紹 (多行) |
| 介紹 (多行) | | |

*標註 * 為必填

---

## 個人網站 (Vercel)

### 網站功能

| 區塊 | 內容 |
|------|------|
| 🏠 Hero | 公司名 + 姓名 + 電話 + 證號 + 自我介紹 |
| 📱 社群連結 | YouTube / Facebook / TikTok / LINE 彩色按鈕列 |
| 🎬 介紹影片 | YouTube 嵌入播放器 |
| 🔍 篩選/搜尋 | 全部 / 房屋 / 土地 / 廠房 + 標題地點搜尋 |
| 📇 卡片網格 | 物件圖片、價格、格局、地點、日期 |
| 🖼️ 詳細 Modal | 點卡片展開所有欄位 + LINE 洽詢按鈕 |
| 📱 LINE 浮動按鈕 | 右下常駐，點擊直接對話 |

### 部署到 Vercel

```bash
# 1. 安裝 Vercel CLI（一次性）
npm i -g vercel

# 2. 部署
cd fb_property_site
vercel

# 3. 以後更新
vercel --prod
```

### 自動上稿機制

點 `🚀 立即發文` 成功後自動：
1. 將物件寫入 `data/listings.json`
2. 複製第一張圖片到 `images/`

不需要手動操作，網站立即更新。

### 自訂營業員資料

在 FB Poster GUI 中點 `👤 個人資料` 按鈕，或直接編輯 `data/agent.json`：

```json
{
  "name": "大雄",
  "company": "住商內壢",
  "phone": "0976-335-651",
  "line_id": "0976335651",
  "intro": "專營桃園中壢房屋買賣...",
  "youtube": "https://youtube.com/@...",
  "facebook": "https://facebook.com/..."
}
```

---

## Telegram Bot

### 啟動

```bash
set TELEGRAM_BOT_TOKEN=12345:ABCDEF...
python telegram_bot.py
```

### 訊息格式

**JSON 格式：**
```json
{
  "template": "房屋物件",
  "title": "元生國小大3房車",
  "price": "988 萬",
  "location": "桃園市中壢區",
  "size": "50.37坪",
  "rooms": "3房2廳2衛",
  "intro": "近學區機能好有大露臺"
}
```

**簡短格式：**
```
房屋物件 | 元生國小大3房車 | 988萬 | 桃園市中壢區
```

**指令：**
- `/templates` — 列出可用模板
- `/pending` — 檢視待發貼文
- `/post` — 模擬發文

---

## 操作說明

### 首次使用

1. 從管理員取得 `license.lic`，放入 `data/` 目錄
2. 雙擊 `launch.bat` 啟動程式
3. 切換到「帳號管理」分頁 → 新增 FB 帳號
4. 匯入 FB Cookie（從瀏覽器匯出 JSON）
5. 點 `👤 個人資料` 設定營業員資料
6. 切換到「發文」分頁開始使用 Pro 模板

### 一般發文流程

```
① 選擇帳號 → 自動載入 Header/Footer
② 選擇模板類型（房屋/土地/廠房）
③ 貼上物件網址 → 點「🤖 一鍵生成」→ 欄位自動填入 + 圖片自動抓取
④ 點「🧠 AI 生成」精修介紹文案
⑤ 選擇社團組合（Set 1/2/3）
⑥ 檢查預覽面板
⑦ 點「🚀 立即發文」或「🕐 排程發文」
```

### Header/Footer 設定

**選單 → 檔案 → Header/Footer 設定**
- 全域預設：所有帳號通用
- 各帳號設定：每個帳號可設定獨立的 Header/Footer

---

## 授權管理（管理員用）

### License 機制

本程式使用 **MAC 地址綁定 + HMAC-SHA256 簽名** 的授權驗證系統：

- 每個 `license.lic` 綁定一台電腦的 MAC 地址
- 無法複製到其他電腦使用
- 可設定到期日，過期自動鎖住
- 簽名密鑰內嵌於程式碼，偽造無效

### 管理員操作

```powershell
# 查看本機 MAC
python license_generator.py --mac

# 產生授權（互動模式）
python license_generator.py --generate

# 驗證授權
python license_generator.py --verify license.lic
```

---

## 常見問題

### Q: 程式打不開，顯示「找不到授權」
A: 請向管理員取得 `license.lic`，放入 `fb_auto_poster/data/`。

### Q: AI 文案生成沒反應？
A: 需要安裝 [Ollama](https://ollama.ai/) 並下載模型（`ollama pull llama3.2`）。若未安裝，會自動使用模板文案。

### Q: 爬取圖片失敗？
A: 部分網站的圖片有防盜連機制，建議使用圖片直鏈網址（以 .jpg/.png 結尾）。

### Q: 網站如何更新？
A: 每次發文成功後自動更新 `listings.json`，執行 `vercel --prod` 即可部署最新版本。

### Q: 如何避免 FB 鎖帳號？
A: 新帳號前 2 週每天只發 1-2 篇，不要一次發 20+ 社團，每篇間隔至少 60 秒，每天定時養號。

---

## 開發筆記

### 技術棧

| 面向 | 技術 | 版本 |
|------|------|------|
| 瀏覽器自動化 | Playwright | ≥1.40 |
| GUI 框架 | Tkinter + ttkbootstrap | ≥1.10 |
| 排程器 | APScheduler | ≥3.10 |
| 加密 | Argon2-cffi | ≥23.1 |
| 網頁爬取 | BeautifulSoup4 | ≥4.12 |
| 圖片處理 | Pillow | ≥10.0 |
| HTTP | requests | ≥2.31 |

### 設計文檔

- [V1 設計規格](docs/superpowers/specs/2026-06-08-fb-auto-poster-design.md)
- [V2 增強功能設計](docs/superpowers/specs/2026-06-08-fb-auto-poster-v2-design.md)
- [V3 TikTok 設計](docs/superpowers/specs/2026-06-08-fb-auto-poster-v3-tiktok-design.md)
- [交班手冊](docs/superpowers/CLAUDE_HANDOVER.md)
