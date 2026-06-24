# Macro + Micro Training Implementation Todo

> For Codex or other LLMs: This is a step-by-step implementation checklist. After completing each item, report the output file and key decisions. Do not write summaries — produce code.

---

## Phase 0 — Project Initialization

- [ ] 0.1 Create project directory structure (output tree + `__init__.py` in each module / usage comments)
- [ ] 0.2 Create `config.yaml`: all paths, date cutoff, GPU/CPU settings, risk params, FinMind API token
- [ ] 0.3 Create `requirements.txt` or `environment.yml` (include `finmind`, `pandas`, `numpy`, `xgboost`, `lightgbm`, `plotly`, `pyyaml`)
- [ ] 0.4 Create `README.md`: one-line description of what the system does + how to run the 14-step pipeline

---

## Phase 1 — FinMind Data Download

- [ ] 1.1 Implement `data_downloader.py`
  - Read FinMind API token from `config.yaml`
  - Support rate limiting (FinMind free tier limit: ~10 calls per minute)
  - Check local cache before downloading; skip if exists and fresh
  - Store all raw data in `data/raw/`
- [ ] 1.2 Download the following FinMind datasets, covering Train ~ Playback range (2024-01-01 ~ 2026-06-22):
  | FinMind dataset | Purpose | Output file |
  |---|---|---|
  | `TaiwanStockPrice` | Daily OHLCV, volume | `daily_price.parquet` |
  | `TaiwanStockPerMinute` | 5-min K-bars (main data for Micro features) | `5min_kbars.parquet` |
  | `TaiwanStockInstitutionalInvestors` | Foreign / investment trust buy/sell | `institutional.parquet` |
  | `TaiwanStockMarginPurchaseShortSale` | Margin trading / short selling balances | `margin.parquet` |
  | `TaiwanStockInfo` | Ticker metadata (industry, listed/OTC) | `stock_info.parquet` |
  | `TaiwanStockTotalInstitutionalInvestors` | Aggregated institutional investors | `total_insti.parquet` |
  | `TaiwanStockNews` (if access granted) | News sentiment | `news.parquet` |
- [ ] 1.3 Download Holdout data (2026-06-23+) separately to `data/raw/holdout/`, do not mix into training
- [ ] 1.4 Implement `data_loader.py`: unified read interface — all modules fetch data only through the loader, never directly from raw files
- [ ] 1.5 Implement data integrity checks:
  - Check date range continuity for each ticker
  - Log missing dates to `data/missing_dates.json`
  - Output listed/OTC ticker list to `data/ticker_registry.json` (include industry classification)

---

## Phase 2 — Data Splitting

- [ ] 2.1 Implement `data_split.py`
  - Baseline cutoff = 2026-06-22
  - Train: 2024-01-01 ~ 2025-12-31
  - Validation: 2026-01-01 ~ 2026-03-31
  - Playback: 2026-04-01 ~ 2026-06-22
  - Holdout: 2026-06-23+ (download only, no training)
- [ ] 2.2 Output `ticker_list.json` and `date_range.json` for each date range to `data/splits/`

---

## Phase 3 — Feature Firewall (No Lookahead)

- [ ] 3.1 Implement `feature_firewall.py`
  - Define `FORBIDDEN_FEATURES`: intraday high/low, future ROI, future exit price, realized PnL, playback results, same-day post-market institutional data
  - Define `ALLOWED_TIMESTAMP_LOGIC`: T-day post-market data → usable only on T+1; 5-min K only at or before current timestamp; news `published_at` ≤ signal timestamp
- [ ] 3.2 All feature outputs must pass `firewall.validate(df)` before use; halt on failure
- [ ] 3.3 Implement `verify_pipeline.py` script: accept a feature CSV, report PASS/FAIL + violating columns

---

## Phase 4 — Macro Training

- [ ] 4.1 Implement `macro_features.py`
  - Produce the following columns (per ticker, per date):
    - Market regime
    - Industry heat ranking
    - Intra-industry lead-lag
    - Foreign investor 1/3/5/10-day net buy/sell and change
    - Investment trust 1/3/5/10-day net buy/sell and change
    - Institutional consecutive buy/sell days
    - News heat and persistence
    - Hot themes
    - AI / Semiconductor / Optoelectronics / Memory / Electronics / Computer industry tags
    - Price bucket
    - Volume and turnover rate
    - Limit-up/limit-down / disposition / split-trading risk
    - ETF impact (observe only, no weighting yet)
- [ ] 4.2 Produce Macro labels: ACCUMULATION / MARKUP_RIDE / DISTRIBUTION / CAPITULATION_BUY / AVOID
- [ ] 4.3 Implement `macro_train.py`
  - XGBoost / LightGBM GPU
  - Output columns: ai_action / macro_score / win_prob / loss_risk / expected_roi / macro_reason_code
- [ ] 4.4 Implement `macro_playback.py`: run Macro inference on playback range → output `macro_signals.csv`
- [ ] 4.5 Implement `macro_eval.py`: Macro-only trades / ROI / win rate / MDD / vs buy-hold delta

---

## Phase 5 — Micro Training

- [ ] 5.1 Implement `micro_features.py`
  - At 5-min K-bar level, produce the following columns (every 5 minutes, per ticker):
    - session VWAP
    - Distance from VWAP %
    - Distance from daily high / daily low %
    - Opening range high / low
    - Prior 5/15/30/60/90-minute return
    - Prior 5/15/30/60/90-minute volume concentration
    - Volume velocity
    - A-shape rollover (bool)
    - V-shape reclaim (bool)
    - VWAP reclaim (bool)
    - VWAP loss (bool)
    - High-price volume spike without price advance (bool)
    - Low-price heavy volume without further decline (bool)
    - Intraday high-low spread
    - Amihud illiquidity proxy
    - DDE/API freshness (timestamp delta)
    - Large order > 500 lots alert (bool)
- [ ] 5.2 Produce Micro labels: SELL_HIGH / BUY_BACK / FORCED_BUY_BACK / ADD_LOW / NO_TRADE / RISK_EXIT
  - See Phase 6 for detailed logic
- [ ] 5.3 Implement `micro_train.py`
  - XGBoost / LightGBM GPU
  - Train only on Macro candidate stocks or held positions
- [ ] 5.4 Output `micro_signals.csv`

---

## Phase 6 — Trade Rule Engine

- [ ] 6.1 Implement `trade_engine.py`
  - Each trade fixed at 1 lot
  - Independent ledger per stock
  - No portfolio max-position cap (single-stock testing)
  - Max 1 SELL_HIGH + 1 BUY_BACK per stock per day
  - Apply all costs and slippage; fallback round-trip cost = 0.78%
  - Expected spread must exceed 0.78% to trade → otherwise NO_TRADE
- [ ] 6.2 Implement signal decision logic:
  ```
  Macro Strong + Holding Position:
    A-shape / far above VWAP / volume spike without price rise → SELL_HIGH
    Return to VWAP / V-shape / low-level absorption → BUY_BACK
    Price keeps rising after sell, not retraced by 10:30 → FORCED_BUY_BACK
    Macro turns weak → do not buy back, switch to REDUCE / EXIT
  Macro Strong + No Position:
    Wait for good Micro entry (BUY_BACK / ADD_LOW)
  DDE/API stale → NO_TRADE (keep only Macro judgment)
  Limit-up/limit-down / disposition / split trading → downgrade Micro
  ```
- [ ] 6.3 Implement sell-high confirmation signals:
  - Current price > VWAP +0.8% ~ +1.5%
  - Near daily high + price advance slowing
  - 5-min K A-shape (new high then 2 consecutive bars fail to make new high + retraces below prior bar low)
  - Volume spike without price advance (volume expanding + spread narrowing)
  - Large sell orders / OFI weakness
  - Industry leader diverging, sector heat fading
- [ ] 6.4 Implement buy-back confirmation signals:
  - Price returns near VWAP / reclaims VWAP after breaking below
  - V-shape (breaks low then rapidly recovers + next 5-min K does not break lower)
  - Drops to opening range low / prior close / POC / HVN with absorption
  - Volume-shrinking decline (selling pressure fading) / heavy volume but price no longer falling (absorption)
  - Macro still strong, institutional/news/sector not turning weak
- [ ] 6.5 Implement forced buy-back discipline:
  - After sell: if not retraced by 10:30 → buy back on first pullback or at ≤ sell price +0.5%
  - Buy-back is mandatory (accept small loss to avoid losing long-term rally position)

---

## Phase 7 — Playback & Metrics

- [ ] 7.1 Implement `playback_runner.py`
  - Run trade_engine day-by-day, 5-min-K by 5-min-K for each stock in playback range
  - Output `ledger_{ticker}.csv`
- [ ] 7.2 Implement `metrics.py`, output per ticker:
  - trades, BUY/ADD/SELL_HIGH/BUY_BACK/FORCED_BUY_BACK/EXIT counts
  - win rate, ROI, cost-adjusted ROI
  - avg trade ROI, rolling ROI
  - max drawdown, max lots held
  - best trade, worst trade
  - vs buy-and-hold delta
  - missed-rally cost, cost-basis reduction amount
  - tradable / watch-only / rejected
- [ ] 7.3 Implement 8 strategy comparisons:
  1. Macro only
  2. Micro only
  3. Macro + Micro
  4. Macro + Micro cost-basis overlay
  5. Buy-and-hold
  6. Reverse signal
  7. No-trade cash
  8. Risk-control version
- [ ] 7.4 Implement No-risk-control bull version (reference only, do not overwrite official risk-controlled model)
- [ ] 7.5 Output `ticker_summary.csv` + `industry_summary.csv`

---

## Phase 8 — Model Registry (Three-Tier Architecture)

- [ ] 8.1 Implement `model_registry.py`
  - Loading priority:
    1. Ticker-specific model (if exists)
    2. Industry model
    3. Universal model (fallback)
  - Micro follows the same three tiers
- [ ] 8.2 Output `model_registry.json`: date, metrics, status for each model
- [ ] 8.3 Implement model versioning: baseline date + train date + metrics snapshot

---

## Phase 9 — GUI / Web GUI Visualization

- [ ] 9.1 Implement GUI that reads from the latest registry
- [ ] 9.2 Single-stock chart must display:
  - Price line
  - VWAP
  - Opening range
  - Macro signals
  - SELL_HIGH orange down-triangle
  - BUY_BACK red up-triangle
  - FORCED_BUY_BACK hollow red up-triangle
  - HOLD white dot
  - Cost line
  - Rolling ROI
  - vs hold ROI
  - Trade reason per entry (tooltip / label)
- [ ] 9.3 Support switching ticker / date range / strategy version

---

## Phase 10 — Batch Training Pipeline

- [ ] 10.1 Implement `run_pipeline.py`, running 14 steps:
  1. FinMind download all required data
  2. Freeze data cutoff = 2026-06-22
  3. verify_pipeline (feature firewall on existing data)
  4. Feature firewall (on new features)
  5. Generate Macro features
  6. Train Macro GPU batch
  7. Playback Macro
  8. Generate Micro 5m features
  9. Train Micro GPU batch
  10. Playback Micro cost-basis overlay
  11. Output ticker_summary / industry_summary / model_registry
  12. GUI reads latest registry
  13. verify_pipeline run once more
- [ ] 10.2 GPU/CPU division:
  - XGBoost/LightGBM → GPU
  - Data splitting / DB read/write / CSV → CPU
  - Batch write (no per-row DB writes)
  - Max GPU jobs: start with 1, scale to 2 once stable
  - Do not spawn too many workers with 32GB RAM
  - Output JSON/CSV artifacts first, write to DB only after verification

---

## Phase 11 — Final Verification

- [ ] 11.1 `verify_pipeline` final PASS
- [ ] 11.2 Complete comparison table for all model variants
- [ ] 11.3 Every ticker_summary is explainable and traceable
- [ ] 11.4 No-lookahead audit: ALL PASS
- [ ] 11.5 Confirm: cost-adjusted ROI > buy-and-hold, MDD under control, missed-rally cost acceptable
