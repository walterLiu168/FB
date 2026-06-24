# Changelog

## v3.2.0 (2026-06-23)

### 🆕 新增

- **個人房屋網站 (`fb_property_site/`)**：一頁式房仲品牌網站，含自我介紹、物件卡片網格、篩選/搜尋、LINE 浮動按鈕
- **Vercel 部署支援**：`vercel.json` 設定，可一鍵部署免費靜態網站
- **營業員資料編輯器**：GUI 內編輯姓名/公司/電話/證號/LINE ID/大頭照
- **社群連結**：YouTube / Facebook / TikTok / LINE 按鈕顯示於網站
- **YouTube 介紹影片嵌入**：網站 Hero 區下方嵌入自我介紹影片
- **發文自動上稿**：點「立即發文」成功後自動加入 `listings.json` + 複製圖片
- **🧠 AI 生成介紹**：介紹欄右側「🧠 AI 生成」按鈕，Ollama 產出 2-3 句亮點文案
- **貼 URL 自動切換模板**：物件含「土地/農地/建地」→ 自動切土地；「廠房/工廠」→ 自動切廠房
- **地圖只顯示市區層級**：location 只保留到「桃園市中壢區」，去掉路名

### 🔧 改善

- **模板欄位重排**：土地 7 欄（新增路寬）、廠房 9 欄（新增土地坪數）
- **預覽即時更新**：Text widget 加入 `<<Modified>>` 事件，程式設定後 50ms 自動刷新
- **可滾動發文面板**：整個「一般發文」tab 包進 Canvas+Scrollbar，防止 Footer 被切
- **描述欄位 3→5 行**，欄位區 200→280px
- **編輯對話框改用 Notebook 雙頁籤**：解決欄位看不見問題

### 🐛 修復

- `agent_profile_dialog.py` 路徑錯誤 (`dirname` 少一層)，導致資料讀不到、欄位空白
- `_add_to_website` 路徑錯誤，發文後無法寫入 listings
- 預覽在 `_set_template_data` 後不刷新
- 模板 404 錯誤（footer_var 在 `_on_template_change` 時尚未初始化）
- Location regex 只抓 `路`，新增支援 `街/巷/弄/段`

---

## v3.1.0 (2026-06-23)

### 🆕 新增

- **Pro 模板系統**：房屋物件/土地/廠房 3 種專業模板
- **模板編輯器**：GUI 內編輯模板文字、欄位定義（新增/刪除/必填/多行）
- **社團組合 (Set 1/2/3)**：選取組合自動勾選對應社團
- **Telegram Bot**：接收 JSON/簡短格式 → 填入模板 → 寫入 pending queue
- **pending 發文佇列**：Telegram → queue → GUI 自動偵測顯示

### 🔧 改善

- 一般發文 tab 改造為動態欄位 + 即時預覽
- Template engine 獨立模組 `core/pro_templates.py`，不依賴 GUI
- Header/Footer 保留在模板外部（不會寫死在模板內）

---

## v2.1 (2026-06-08)

- License 授權系統（MAC 綁定 + HMAC 簽名）

## v2.0 (2026-06-08)

- AI 文案生成（Ollama 整合）
- 網頁圖片爬取
- Header/Footer 範本管理
- 操作日誌系統
- 自動刪文定時器

## v1.0 (2026-06-08)

- 基礎發文功能（一般/拍賣/社團）
- 多帳號管理（Cookie 匯入）
- 自動排程發文（APScheduler）
- 自動養號（瀏覽/按讚/加社團）
- 自動刪文
- 自動留言互動
- 反偵測/防鎖機制
