# FB Auto Poster — Handover Guide for Claude

## Environment

- **Python**: 3.14.5
- **Project root**: `C:\Users\icemo\Documents\trae_projects\facebook\fb_auto_poster\`
- **Python executable**: `C:\1\.venv\Scripts\python.exe`
- **Working directory**: `C:\Users\icemo\Documents\trae_projects\facebook`
- **Run command**: `C:\1\.venv\Scripts\python.exe fb_auto_poster\main.py`

## Critical Platform Rules

1. **`ttk.LabelFrame` does NOT support `padding=`** in Python 3.14 tkinter.
   - WRONG: `ttk.LabelFrame(parent, text="X", padding=10)`
   - RIGHT: `lf = ttk.LabelFrame(parent, text="X")` → `inner = ttk.Frame(lf, padding=10)` → widgets go in inner

2. **.bat files**: NO Chinese characters at all (not in comments, echo, title). Use `pushd`/`popd`. Save as ANSI encoding. No `chcp 65001`.

3. **Account display**: Accounts should show as `email (nickname)` in dropdowns, NOT as UUID.

---

## All Changes Made So Far (Changelog)

### V2.1 — TikTok: X-Bogus sign → Playwright browser upload

**What changed:**
- `core/tiktok_uploader.py` — Complete rewrite. Was using TikTok internal API + X-Bogus signing (`/api/v1/web/project/create/` + `/api/v1/web/project/post/`). Now uses Playwright browser with persistent context (Chrome profile).
- `core/tiktok_sign.py` — X-Bogus sign module preserved but no longer called (the TikTok internal API has changed, `log_pb` error occurs).
- `gui/tiktok_settings.py` — Simplified. No OAuth fields. Just "add nickname + login via browser". Has "🔑 Login" button that opens Playwright browser for manual login.

**How TikTok upload works now:**
1. User adds account in 檔案 → TikTok 設定 → enters nickname
2. User clicks "🔑 登入" → Playwright opens Chrome → user manually logs into TikTok
3. Login state saved to `data/tiktok_profile/{nickname}/` (full Chrome profile: cookies, localStorage)
4. When uploading: Playwright loads the profile → opens `https://www.tiktok.com/tiktokstudio/upload` → auto-selects MP4 → fills caption → clicks Post

**Known TikTok issues:**
- Page load timeout: TikTok Studio is slow. Uses `domcontentloaded` (not `networkidle`) + 90s timeout
- Login expiration not detected well. Auto-detects if redirected to `passport/` or `login/` URL
- Some websites block Playwright — Chrome flags help: `--disable-web-security`, `--disable-blink-features=AutomationControlled`, `--no-sandbox`
- User cannot use TikTok account while upload is happening (browser opens a real window)

### V2.0 — Property scraper + AI extraction

**Files changed:**
- `core/scraper.py` — Major rewrite. Now scrapes images into `data/temp_images/YYYY-MM-DD_HH/` folders. Priority-based image finding: og:image → data-src → src → background-image. Added `extract_property_info()` and `_extract_with_regex()`.
- `gui/poster_panel.py` — Added "🧠 提取物件" button and `_on_extract_property()` method. Added "🔗" open-in-browser button.
- `core/ai_writer.py` — Improved error handling. Shows "Ollama not running" message instead of silently failing.

**Property extraction fields (11 total):**
```
title, price, location, type, size, rooms, floor, age, parking, orientation, description
```

### V1.9 — FB posting engine selectors

- `core/poster.py` — Rewrote all Playwright selectors for FB posting. Now uses cascading fallbacks: English aria-label → Chinese aria-label → role-based selector. Each action (click status box, find editor, click publish) has 5-8 selector variants.

### V1.8 — AutoCleaner sync fix

- `core/auto_cleaner.py` — `run_clean` was `async def` but did no async work. Changed to sync `def` so APScheduler can call it correctly.
- `gui/app.py` — Registered `auto_clean` callback with scheduler.

---

## Known Bugs / Issues

### FB Posting
- **Selectors may still break** when Facebook updates their DOM. The cascading fallback system helps but is not guaranteed.
- **No retry logic** if post fails mid-way (e.g., network issue during image upload).
- **Cannot post to groups from Marketplace tab** — only personal wall and individual groups.
- **No post scheduling** in the engine itself (scheduling is done via APScheduler which calls the engine).

### TikTok
- **Login expires**: TikTok session may expire after days/weeks. User needs to re-login.
- **TikTok Studio DOM changes**: The selectors for file input and Post button rely on TikTok's current DOM structure.
- **No headless mode**: Must open a visible browser window (TikTok blocks headless).
- **Slow upload**: Large videos (100MB+) could take minutes to process on TikTok's side. Wait_for_function has 120s timeout.
- **Caption fill might fail**: `caption_area.fill()` works most of the time but TikTok sometimes uses a different input mechanism.

### Scraper
- **591 and similar sites**: SSL verification disabled (`verify=False`). This is intentional.
- **Some pages return 0 images**: Site may use `data-src` attributes we haven't covered, or lazy-load via JavaScript (Playwright scrapers, not BeautifulSoup, would be needed for those).
- **Ollama extraction slow**: 8s timeout on Ollama call. If not running, falls back to regex.

### AI Writer
- **Ollama required for real AI**: Without Ollama, only template-based fallback is used. Templates are simple and generic.
- **No streaming output**: Text appears only after full generation.

### General
- **No persistent log viewer**: Logs are shown in UI but not searchable.
- **No multi-language support**: Everything is in Traditional Chinese.
- **No error reporting**: Failures are printed to console / shown in status bar but not sent anywhere.
- **`data/tiktok_accounts.json` persists stale accounts**: When an account is removed via the GUI, both the JSON entry and the profile directory are deleted.

---

## TODOs

### High Priority

1. **FB posting retry logic** — If a post fails (network error, FB rate limit, etc.), retry 2-3 times with exponential backoff before giving up.

2. **TikTok upload status feedback** — After clicking Post on TikTok Studio, check for success/cancel and report back to the app status bar. Currently it just sleeps 3 seconds and assumes success.

3. **Schedule posting with pictures** — Currently APScheduler jobs can trigger text posts but don't handle image attachments well. The `ScheduleJob.params` dict needs a way to reference saved image paths.

4. **Login status persistence check** — On app startup, verify TikTok profiles are still valid (try loading `state.json`). If missing, mark as "未登入".

### Medium Priority

5. **Marketplace category/tags** — FB Marketplace listing creation currently fills title/price/location/description but doesn't select category (House/Rent/etc.) which FB sometimes requires.

6. **Batch post to multiple FB accounts** — Currently posts one account at a time. Could add "select all accounts and post same content" feature.

7. **Image deduplication** — When scraping images from multiple URLs, same image might be downloaded multiple times. Hash-based dedup would save space.

8. **Ollama model selector in UI** — Currently uses hardcoded `llama3.2`. Should show installed models dropdown.

### Low Priority / Future

9. **Dark mode toggle** — App uses ttkbootstrap "darkly" theme. Could add theme switcher.

10. **Export logs to CSV** — For auditing/analytics.

11. **Post preview** — Before sending, show a preview of how the post will look.

12. **Update spec doc** — `docs/superpowers/specs/2026-06-08-fb-auto-poster-v3-tiktok-design.md` describes the old X-Bogus approach and needs updating to reflect the Playwright-based approach.

---

## File Map

```
fb_auto_poster/
├── main.py                    # Entry point
├── core/
│   ├── engine.py              # SessionManager — bridges GUI ↔ Playwright
│   ├── scheduler.py           # APScheduler wrapper
│   ├── account.py             # Account CRUD
│   ├── poster.py              # FB posting (Playwright selectors)
│   ├── scraper.py             # Image scraping + property extraction
│   ├── ai_writer.py           # Ollama AI + template fallback
│   ├── templates.py           # Header/Footer per account
│   ├── auto_cleaner.py        # Scheduled post cleanup
│   ├── footprint_cleaner.py   # Browser footprint cleaning
│   ├── nurturer.py            # FB account nurturing
│   ├── deleter.py             # FB post deletion
│   ├── interactor.py          # FB comment/interaction
│   ├── browser.py             # Playwright browser management
│   ├── tiktok_slideshow.py    # Images → 1080x1920 MP4
│   ├── tiktok_uploader.py     # TikTok upload (Playwright)
│   └── tiktok_sign.py         # X-Bogus sign (preserved, unused)
├── gui/
│   ├── app.py                 # Main window
│   ├── poster_panel.py        # Post form + TikTok section
│   ├── account_manager.py     # Account management panel
│   ├── scheduler_panel.py     # Schedule management
│   ├── nurturer_panel.py      # Nurturing controls
│   ├── log_panel.py           # Activity log
│   ├── tiktok_settings.py     # TikTok account dialog
│   └── dark_theme.py          # Styled widgets
├── utils/
│   ├── config.py              # Paths, JSON load/save
│   ├── secret_store.py        # Fernet reversible encryption
│   ├── crypto.py              # Argon2 one-way hashing
│   ├── logger.py              # Logging
│   └── randomizer.py          # Random delays
└── data/                      # Runtime data (gitignored)
    ├── tiktok_accounts.json
    ├── tiktok_profile/        # Chrome profiles per account
    ├── temp_images/           # YYYY-MM-DD_HH/ subfolders
    ├── temp_tiktok/           # Generated MP4s
    └── .secret_key            # Fernet key (auto-generated)
```
