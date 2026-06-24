# FB Auto Poster 增強功能設計文檔 (V2)

## 新增功能
1. **AI 文案生成** — 串接 Ollama 本地 LLM，自動產生房仲/車仲促銷文案
2. **網頁圖片爬取** — 從物件網址自動抓取圖片，也支援圖片直鏈下載
3. **Header/Footer 範本** — 每篇貼文自動附加頁首頁尾（電話、Line ID、網址等）
4. **操作日誌系統** — 記錄所有發文/刪文/養號操作，附時間戳與結果
5. **自動刪文定時器** — 排程每日定時清理過期貼文

## 新增/修改檔案

### 新增
- `core/ai_writer.py` — Ollama API 呼叫，prompt 模板
- `core/scraper.py` — 網頁圖片爬取 + 圖片直鏈下載
- `core/templates.py` — Header/Footer 範本管理
- `utils/logger.py` — 操作日誌記錄
- `core/auto_cleaner.py` — 自動刪文定時器邏輯

### 修改
- `gui/poster_panel.py` — 新增 AI 生成按鈕、圖片爬取輸入、Header/Footer 欄位、自動刪除勾選
- `gui/app.py` — 新增「日誌」分頁、設定選單加入 Header/Footer 設定
- `utils/config.py` — 新增日誌相關儲存函數
- `requirements.txt` — 新增 beautifulsoup4, markdownify

## 技術細節

### AI 文案 (Ollama)
- API: `POST http://localhost:11434/api/generate`
- Model: 預設 `llama3.2` 或使用者自選
- Prompt 模板包含角色設定（房仲/車仲）+ 商品資訊 + 風格指示
- 離線或 Ollama 未安裝時自動 fallback 到模板文案

### 圖片爬取
- 輸入為網址 → 自動判斷：
  - HTML 頁面 → 使用 BeautifulSoup 解析，找 `<img>` 標籤，過濾小圖示/廣告
  - 直接圖片網址 (.jpg/.png/.webp) → 直接下載
- 圖片暫存到 `data/temp_images/`，發文後可選擇清理

### Header/Footer 範本
- 每個帳號可設定獨立的 Header/Footer（儲存在 config.json）
- Header 預設: 商品類型 Emoji + 標題
- Footer 預設: 電話 + Line ID + 網址
- 發文時可臨時覆蓋

### 操作日誌
- 檔案: `data/operations.log` (純文字)
- 格式: `[時間] 類別 | 帳號 | 動作 | 結果 | 詳細資訊`
- GUI 面板可即時查看最近 100 筆日誌

### 自動刪文定時器
- 排程任務類型: `auto_clean`
- 設定: 每天固定時間執行 (預設 03:00 AM)
- 邏輯: 掃描日誌中「已發送且超過 N 小時」的貼文，逐一刪除
- 可設定保留時間（預設 24 小時）
