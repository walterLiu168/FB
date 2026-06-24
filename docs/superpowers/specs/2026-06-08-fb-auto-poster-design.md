# FB Auto Poster (FB POSTER) 設計文檔

## 概述
一款專為房仲、車仲設計的 Facebook 自動發文 + 養號 + 排程桌面應用程式。使用 Python + Playwright + Tkinter 開發，支援多帳號管理，資料僅存於本地設備。

## 技術棧
| 面向       | 選擇                             | 原因                             |
|------------|----------------------------------|----------------------------------|
| 瀏覽器自動化 | Playwright                     | 更快、更穩定、反偵測更好           |
| GUI        | Tkinter + ttkbootstrap (暗色主題) | 輕量無依賴，符合用戶偏好           |
| 資料儲存   | 本地 JSON + Argon2 加密          | 資料僅存設備端                     |
| 排程器     | APScheduler                     | 輕量級，支援 cron 表達式           |

## 專案結構
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
```

## 核心功能

### 1. 多帳號管理
- Cookie/Session 匯入（從瀏覽器導出）
- 帳號密碼 Argon2 加密儲存
- 帳號列表 CRUD
- 各帳號獨立設定

### 2. 一般/拍賣發文
- 支援純文字 + 圖片 + 影片
- 拍賣模式包含：地區、價格、名稱
- 隨機文字/圖片插入，突破重複偵測
- 隨機延遲 60~360 秒

### 3. 自動轉發
- 多社團批量發送
- 可選特定社團白名單

### 4. 自動排程 (APScheduler)
- 每日多時段設定 (如 09:00, 14:00, 20:00)
- 每週重複模式
- 各帳號獨立排程

### 5. 自動養號
- 模擬瀏覽貼文 (每天 1~10 篇)
- 自動按讚
- 安全加入社團 (每次 5 個，間隔 60 秒)
- 抓取新聞/時事自動發文到個人頁面

### 6. 自動刪文
- 指定社團批量刪文
- 全刪模式 (謹慎使用)

### 7. 自動留言互動
- 指定貼文留言 (貼文網址)
- 熱門貼文自動留言
- 多帳號操作

### 8. 反偵測/防鎖
- Argon2 加密通訊
- 真人操作指紋模擬
- 隨機延遲 60~360 秒
- 隨機圖片/文字字串
- 漸進式發文量

## 架構設計

### 資料流
```
GUI Layer (Tkinter) 
    ↕ 事件/指令
Core Layer (business logic)
    ↕ 操作
Playwright Browser (持續會話)
    ↕ HTTP
Facebook.com
```

### 瀏覽器管理
- 每個帳號獨立 Browser Context
- 持久化 Cookie/Storage 保持登入狀態
- 隨機 User-Agent、Viewport、指紋參數

### 資料儲存
- `data/accounts.json` — 加密後帳號資料
- `data/config.json` — 各帳號設定 (純文字)
- `data/schedules.json` — 排程設定

## 安全設計
- 密碼使用 Argon2 加密後儲存
- Cookies 加密儲存
- 所有資料僅存於本地設備
- 無雲端同步或後端伺服器

## 錯誤處理
- 每個自動化操作有重試機制 (最多 3 次)
- 操作失敗時記錄 log
- GUI 顯示即時狀態
- 緊急停止按鈕中斷所有自動化

## 開發順序
1. 專案初始化 + utils 工具函數
2. core/browser.py — Playwright 瀏覽器引擎
3. core/account.py — 帳號管理
4. core/poster.py — 發文引擎
5. core/scheduler.py — 排程引擎
6. core/nurturer.py — 養號引擎
7. core/deleter.py + interactor.py — 刪文/留言
8. GUI 所有面板
9. main.py 整合 + 測試
