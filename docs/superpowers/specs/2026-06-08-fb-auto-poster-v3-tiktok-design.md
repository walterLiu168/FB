# FB Auto Poster V3 — TikTok 幻燈片產生 + 上傳

- 日期：2026-06-08
- 狀態：已實作
- 範圍：在既有桌面應用中新增「由圖片 + 文案產生直式幻燈片並上傳 TikTok」功能

## 1. 目標

重用 app 既有的 AI 文案（Ollama）與圖片爬取結果，產生 1080x1920 直式 MP4 幻燈片，
並透過 **TikTok 官方 Content Posting API** 上傳。

## 2. 與原始規格的差異（重要）

原始規格（本檔先前版本）要求整合 `Tiktok-API-Upload` 的 `uploadVideo()` + `x_bogus_`
請求簽章，呼叫 TikTok 內部 web API、僅用 `session_id` cookie 繞過 OAuth。
此作法是規避平台的存取控制與自動化防護（X-Bogus 即 TikTok 的反自動化簽章），
違反平台條款且每次 TikTok 改版即失效，**未採用**。

改以官方支援的方式實作，對使用者的功能相同，但更穩定且合規：

| 項目 | 原始規格 | 實際實作 |
| --- | --- | --- |
| 認證 | session_id cookie | OAuth access token（官方） |
| 上傳端點 | 內部 web API + x_bogus 簽章 | `/v2/post/publish/video/init/`（官方 Direct Post） |
| 簽章模組 | `core/tiktok_sign.py`（複製 x_bogus_.py） | 不需要，未建立此檔 |
| 憑證儲存加密 | Argon2 | Fernet 可逆加密（見下） |

### 為什麼不用 Argon2 存 token
`utils/crypto.py` 的 Argon2 是單向雜湊，`decrypt_dict()` 直接 raise `NotImplementedError`。
OAuth token 必須能讀回再送出，所以新增 `utils/secret_store.py`，
以 Fernet（AES-128-CBC + HMAC）做可逆加密，金鑰存於 `data/.secret_key`（首次自動產生）。

## 3. 新增 / 變更檔案

新增：
- `core/tiktok_slideshow.py` — 圖片 + 文案 → 1080x1920 MP4（PIL 疊字 + moviepy 串接）
- `core/tiktok_uploader.py` — 官方 API 上傳、帳號 CRUD、token 刷新
- `utils/secret_store.py` — Fernet 可逆加密
- `gui/tiktok_settings.py` — TikTok 帳號設定對話框

變更：
- `gui/poster_panel.py` — 「一般發文」分頁底部新增 TikTok Upload 區塊
- `gui/app.py` — 檔案選單新增「TikTok 設定」、匯入驗證
- `requirements.txt` — 新增 `cryptography`, `moviepy`, `numpy`

## 4. 流程

1. 使用者於「檔案 → TikTok 設定」新增帳號（暱稱 + OAuth access token，可選 refresh/client）
2. 在「一般發文」填文案、選圖（本機或爬取，2–5 張）
3. 選 TikTok 帳號、填 hashtag、設定每張秒數
4. 點「🎬 產生幻燈片並上傳 TikTok」→ 背景執行緒：
   - `create_slideshow()` 產生 MP4 至 `data/temp_tiktok/output.mp4`
   - `upload_video()` 走官方 init → 分塊 PUT 上傳 → 回傳 publish_id
5. 狀態標籤即時更新，結果寫入 `operations.log`（action_type=TIKTOK）

### GUI 區塊
```
┌─────────────────────────────────────────┐
│ TikTok Upload                            │
│ TikTok 帳號: [選擇 ▼] [🔄]               │
│ Hashtags: [#房仲 #買房]  每張秒數: [3]   │
│ [🎬 產生幻燈片並上傳 TikTok]   狀態: 就緒 │
└─────────────────────────────────────────┘
```

## 5. API 細節

- Init：`POST /v2/post/publish/video/init/`，Bearer token，`source=FILE_UPLOAD`
- 上傳：`PUT upload_url`，分塊 `Content-Range: bytes start-end/total`
- 狀態：`POST /v2/post/publish/status/fetch/`，body `{publish_id}`
- Token 401 時以 refresh_token grant 自動刷新（需 client_key/secret）

## 6. 限制與注意事項

- 未經 TikTok 審核的應用程式只能發佈到私人帳號（`privacy_level=SELF_ONLY`），程式預設即為此值。
- 每個 access token 每分鐘最多 6 次 init 請求。
- moviepy 2.x 移除 `moviepy.editor` 命名空間並將 `set_fps` 改為 `with_fps`，程式已同時相容 1.x / 2.x。
- 使用者需自行於 TikTok for Developers 建立 app 並完成 OAuth 取得 token；本工具不內建 OAuth 授權流程（後續工作）。

## 7. 驗證

- 匯入測試：`from core.tiktok_slideshow import create_slideshow` ✅
- 端對端 render：3 張圖 → 1080x1920、6s MP4 ✅
- secret_store 加解密 round-trip ✅
- 帳號 save/list/get/remove round-trip ✅
- 所有 GUI 模組語法與 import ✅

## 8. 後續工作

- 內建 OAuth 授權流程（目前需手動貼 token）
- 上傳後輪詢 `fetch_status` 並在 UI 顯示處理結果
- 幻燈片轉場/背景音樂（目前為硬切、無音軌）
