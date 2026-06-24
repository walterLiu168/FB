# Codex `/goal` 完整執行命令清單

> 打開 Codex CLI → 貼上命令 → 讓它跑到完 → 檢查 → 下一條

---

## 前置設定（做一次就好）

```bash
# 1. 進專案目錄
cd c:\Users\icemo\Documents\trae_projects\facebook

# 2. 開新分支（安全網）
git init
git checkout -b codex/build

# 3. 啟動 Codex（full-auto 模式）
codex --approval-mode full-auto
```

進到 Codex TUI 後，先啟用 goal：
```
/experimental
```
選 goal 啟用，然後開始：

---

## Session 1：Phase 0-1（環境 + 資料下載）

```
/goal 完成以下任務：

## Phase 0 — 專案初始化
1. 建立專案目錄結構，產出 tree，每個目錄要有 __init__.py
2. 建立 config/config.yaml，內容包含：
   - data 路徑
   - 日期 cutoff: 2026-06-22
   - GPU/CPU 設定
   - risk params
   - FinMind API token 佔位符（使用者自己填）
3. 建立 requirements.txt，含：finmind, pandas, numpy, xgboost, lightgbm, plotly, pyyaml
4. 建立 README.md，一句話說明系統做什麼

## Phase 1 — FinMind 資料下載
5. 建立 src/data_downloader.py：
   - 讀 config.yaml 拿 FinMind token
   - 支援 rate limiting（免費版每分鐘 ~10 次）
   - 下載前檢查本地 cache，有就跳過
   - raw data 存到 data/raw/
6. 下載這 7 個 FinMind 資料集（2024-01-01 ~ 2026-06-22）：
   - TaiwanStockPrice → data/raw/daily_price.parquet
   - TaiwanStockPerMinute → data/raw/5min_kbars.parquet
   - TaiwanStockInstitutionalInvestors → data/raw/institutional.parquet
   - TaiwanStockMarginPurchaseShortSale → data/raw/margin.parquet
   - TaiwanStockInfo → data/raw/stock_info.parquet
   - TaiwanStockTotalInstitutionalInvestors → data/raw/total_insti.parquet
   - TaiwanStockNews（若有權限）→ data/raw/news.parquet
7. 建立 src/data_loader.py：統一讀取介面，所有模組只透過它拿資料
8. 資料完整性檢查：產出 data/missing_dates.json + data/ticker_registry.json

## 停止條件
所有 7 個 parquet 檔案存在且非空。ticker_registry.json 有內容。
下載失敗就 retry（最多 3 次），超過就跳過並記錄。

## 不要做的事
不要改動任何不在以上清單的檔案。
```

---

## Session 2：Phase 2-3（資料切分 + Firewall）

```
/goal 繼續在上次 codebase 上完成：

## Phase 2 — 資料切分
1. 建立 src/data_split.py：
   - Baseline cutoff = 2026-06-22
   - Train: 2024-01-01 ~ 2025-12-31
   - Validation: 2026-01-01 ~ 2026-03-31
   - Playback: 2026-04-01 ~ 2026-06-22
   - Holdout: 2026-06-23+
2. 產出 data/splits/ticker_list.json + data/splits/date_range.json

## Phase 3 — Feature Firewall
3. 建立 src/feature_firewall.py：
   - FORBIDDEN_FEATURES 黑名單：當日 high/low、未來 ROI、未來 exit price、realized pnl、playback 結果
   - ALLOWED_TIMESTAMP_LOGIC：T 日盤後資料 → T+1 才能用；5分K 只能看當下以前；新聞 published_at ≤ signal timestamp
   - firewall.validate(df) 方法：fail 就 halt
4. 建立 src/verify_pipeline.py：接受 feature CSV，回報 PASS/FAIL + 違規欄位

## 停止條件
跑 verify_pipeline.py 對測試資料輸出 PASS（可以先用空資料測結構）。
data/splits/ 下有 json 檔案。

## 不要做的事
不要碰 data/raw/ 裡的原始資料。
```

---

## Session 3：Phase 4（Macro 訓練）

```
/goal 繼續在上次 codebase 上完成：

## Phase 4 — Macro 訓練

1. 建立 src/macro_features.py，產出以下欄位（每個 ticker 每個日期）：
   - 大盤 regime
   - 產業熱度 ranking
   - 同產業 lead-lag
   - 外資 1/3/5/10 日買賣超與變化
   - 投信 1/3/5/10 日買賣超與變化
   - 法人連買/連賣天數
   - 新聞熱度與延續性
   - 熱門題材
   - AI/半導體/光電/記憶體/電子/電腦 族群標籤
   - 價格區間 bucket
   - 成交量與週轉率
   - 漲跌停/處置/分盤風險
   - ETF 影響（先觀察）

2. 產出 Macro labels：ACCUMULATION / MARKUP_RIDE / DISTRIBUTION / CAPITULATION_BUY / AVOID

3. 建立 src/macro_train.py：
   - XGBoost / LightGBM GPU
   - 輸出：ai_action / macro_score / win_prob / loss_risk / expected_roi / macro_reason_code

4. 建立 src/macro_playback.py：跑 playback 區間 → data/output/macro_signals.csv

5. 建立 src/macro_eval.py：產出 trades / ROI / win rate / MDD / vs buy-hold delta

## 停止條件
macro_signals.csv 產生且 non-empty。
macro_eval.py 可以跑完不報錯。

## 不要做的事
不要使用未來資料作為 feature（全部過 firewall）。
feature 產出前跑 firewall.validate()。
```

---

## Session 4：Phase 5-6（Micro 訓練 + 交易引擎）

```
/goal 繼續在上次 codebase 上完成：

## Phase 5 — Micro 訓練

1. 建立 src/micro_features.py，產出以下 5 分 K 級別欄位：
   - session VWAP、距 VWAP %、距日高/日低 %
   - opening range high/low
   - 前 5/15/30/60/90 分鐘 return
   - 前 5/15/30/60/90 分鐘 volume concentration
   - 量速
   - A-shape rollover (bool)、V-shape reclaim (bool)
   - VWAP reclaim (bool)、VWAP loss (bool)
   - 高檔爆量但不漲 (bool)、低檔大量不跌 (bool)
   - 日內 high-low spread
   - Amihud illiquidity proxy
   - DDE/API freshness (timestamp delta)
   - 大單 > 500 張 alert (bool)

2. 產出 Micro labels：SELL_HIGH / BUY_BACK / FORCED_BUY_BACK / ADD_LOW / NO_TRADE / RISK_EXIT

3. 建立 src/micro_train.py：XGBoost/LightGBM GPU，只在 Macro 候選股上訓練

## Phase 6 — 交易規則引擎

4. 建立 src/trade_engine.py：
   - 每筆交易固定 1 張
   - 每檔股票獨立 ledger
   - 不設 portfolio max cap
   - 每股每天最多 1 次 SELL_HIGH + 1 次 BUY_BACK
   - round-trip cost = 0.78%，價差 > 0.78% 才交易
   - 訊號邏輯：
     Macro 強+持股 → A-shape/高於VWAP → SELL_HIGH
     Macro 強+持股 → 回VWAP/V-shape → BUY_BACK
     賣出後續漲+10:30前沒回 → FORCED_BUY_BACK
     Macro 轉弱 → 不買回，REDUCE/EXIT
     DDE/API 不新鮮 → NO_TRADE
     漲跌停/處置/分盤 → Micro 降級

## 停止條件
micro_signals.csv 產生。
trade_engine.py 可以 import 不報錯。

## 不要做的事
Micro 只處理 Macro 候選股，不要重新選股。
feature 產出前跑 firewall.validate()。
```

---

## Session 5：Phase 7（Playback + 指標）

```
/goal 繼續在上次 codebase 上完成：

## Phase 7 — Playback 與指標

1. 建立 src/playback_runner.py：
   - 對 playback 區間每檔 stock 逐日、逐 5 分 K 跑 trade_engine
   - 產出 data/output/ledger_{ticker}.csv

2. 建立 src/metrics.py，每檔產出：
   - trades, BUY/ADD/SELL_HIGH/BUY_BACK/FORCED_BUY_BACK/EXIT 次數
   - win rate, ROI, cost-adjusted ROI
   - avg trade ROI, rolling ROI
   - max drawdown, max lots held
   - best trade, worst trade
   - vs buy-and-hold delta
   - 賣飛成本, 降成本金額
   - tradable / watch-only / rejected

3. 產出 8 種策略比較：
   - Macro only
   - Micro only
   - Macro + Micro
   - Macro + Micro cost-basis overlay
   - Buy-and-hold
   - Reverse signal
   - No-trade cash
   - Risk-control version

4. 產出 data/output/ticker_summary.csv + data/output/industry_summary.csv

## 停止條件
至少產出 1 個 ticker 的 ledger + metrics + 8 種策略對照表。
所有 CSV 可讀且 non-empty。

## 不要做的事
不要跳過 cost 計算。
No-risk-control bull version 只標記參考，不覆蓋正式模型。
```

---

## Session 6：Phase 8-9（Registry + GUI）

```
/goal 繼續在上次 codebase 上完成：

## Phase 8 — 模型註冊表

1. 建立 src/model_registry.py：
   - 載入優先序：ticker model → industry model → universal model
   - Micro 同樣三層
2. 產出 data/output/model_registry.json
3. 版本管理：baseline date + train date + metrics snapshot

## Phase 9 — GUI

4. 建立 gui/app.py（用 plotly dash 或 streamlit）：
   - 讀取最新 registry
   - 單股圖表顯示：
     價格線 + VWAP + opening range
     SELL_HIGH 橘色下三角
     BUY_BACK 紅色上三角
     FORCED_BUY_BACK 空心紅三角
     HOLD 白點
     成本線 + rolling ROI + vs hold ROI
     每筆交易原因（tooltip）
   - 支援切換 ticker / date range / 策略版本

## 停止條件
GUI 可以啟動（python gui/app.py 不報錯）。
至少可以載入一個 ticker 的圖表。

## 不要做的事
不要硬編碼 ticker 或路徑，全部從 registry 讀。
```

---

## Session 7：Phase 10-11（Pipeline + 最終驗證）

```
/goal 繼續在上次 codebase 上完成：

## Phase 10 — 批次訓練 Pipeline

1. 建立 run_pipeline.py，跑 14 步：
   1. FinMind 下載
   2. freeze data cutoff
   3. verify_pipeline (existing data)
   4. feature firewall (new features)
   5. 產生 Macro features
   6. train Macro GPU
   7. playback Macro
   8. 產生 Micro 5m features
   9. train Micro GPU
   10. playback Micro cost-basis overlay
   11. 產出 ticker_summary / industry_summary / model_registry
   12. GUI 讀取最新 registry
   13. verify_pipeline 再跑一次

2. GPU/CPU 分工註解：
   - GPU: XGBoost/LightGBM
   - CPU: 資料切分、DB read/write、CSV
   - batch write，不逐筆寫 DB
   - max GPU jobs 先 1

## Phase 11 — 最終驗證

3. verify_pipeline 最終 PASS
4. 產出所有 model comparison 對照表
5. 每檔 ticker_summary 可追溯
6. no-lookahead audit 全 PASS

## 停止條件
run_pipeline.py 從頭跑到尾不報錯。
verify_pipeline 回報 PASS。

## 不要做的事
不要跳過任何 verify 步驟。
跑失敗不要覆蓋舊 artifact。
```

---

## 常用監控指令

```bash
# 看目前 goal 狀態
/goal

# 暫停
/goal pause

# 繼續
/goal resume

# 清除（重新來）
/goal clear

# 叫 Codex 覆審目前產出
/review 檢查目前所有產出是否符合 spec，列出任何不一致

# 看改了什麼
/diff

# 回上一分支（如果搞砸）
git checkout .
git checkout main
```

---

## 規則總結

| 做 | 不做 |
|----|------|
| 每次只餵一條 `/goal` | 不要一次丟整個 todo file |
| 等它跑完 + 檢查產出再下一條 | 不要跳 phase |
| 用 `git branch` 隔離 | 不要在 main 上跑 full-auto |
| 失敗就 `/goal clear` 重來 | 不要手動修 code 再叫它繼續 |
| 每條 goal 都有停止條件 | 不要留 open-ended goal |
