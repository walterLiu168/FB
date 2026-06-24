# =============================================================================
# FB POSTER — Universal Configuration
# =============================================================================
# 所有設定統一從這裡讀取。優先序：環境變數 > .env 檔案 > 預設值
# Mock 模式：將任何 API key 設為 "MOCK" 即可離線運行
# =============================================================================
import os
import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ── 專案根目錄 ──
PROJECT_ROOT = Path(__file__).resolve().parent.parent
FB_AUTO_POSTER_DIR = PROJECT_ROOT / "fb_auto_poster"
PROPERTY_SITE_DIR = PROJECT_ROOT / "fb_property_site"
DATA_DIR = FB_AUTO_POSTER_DIR / "data"
TEMP_DIR = DATA_DIR / "temp_images"
PENDING_DIR = DATA_DIR / "pending_posts"

# Ensure directories exist
for d in [DATA_DIR, TEMP_DIR, PENDING_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ── 載入 .env ──
def _load_dotenv():
    """載入 .env 檔案（不依賴 python-dotenv）"""
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        env_path = FB_AUTO_POSTER_DIR / ".env"
    if not env_path.exists():
        return
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = val
        logger.info(f"Loaded .env from {env_path}")
    except Exception as e:
        logger.warning(f"Failed to load .env: {e}")

_load_dotenv()

# ── Config Reader ──
def get(key: str, default: Any = None) -> str:
    """讀取設定值（環境變數優先）"""
    return os.environ.get(key, str(default) if default is not None else "")

def get_bool(key: str, default: bool = False) -> bool:
    val = get(key, str(default)).lower()
    return val in ("1", "true", "yes", "on")

def get_int(key: str, default: int = 0) -> int:
    try:
        return int(get(key, str(default)))
    except (ValueError, TypeError):
        return default

def is_mock(key: str) -> bool:
    """檢查 API key 是否為 mock 模式"""
    return get(key, "").upper() == "MOCK"


# ── 發文設定 ──
POST_INTERVAL_MIN = get_int("POST_INTERVAL_MIN", 60)
POST_INTERVAL_MAX = get_int("POST_INTERVAL_MAX", 360)
DELETE_AFTER_HOURS = get_int("DELETE_AFTER_HOURS", 24)
AUTO_CLEAN_HOUR = get_int("AUTO_CLEAN_HOUR", 3)
AUTO_CLEAN_MINUTE = get_int("AUTO_CLEAN_MINUTE", 0)

# ── Ollama ──
OLLAMA_HOST = get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = get("OLLAMA_MODEL", "llama3.2")

# ── OpenAI ──
OPENAI_API_KEY = get("OPENAI_API_KEY", "MOCK")
OPENAI_MODEL = get("OPENAI_MODEL", "gpt-4.1-mini")
GPT_SERVER_URL = get("GPT_SERVER_URL", "https://ezup.work/api/gpt")
OPENAI_MOCK = is_mock("OPENAI_API_KEY")

# ── Facebook Graph API ──
FB_APP_ID = get("FB_APP_ID", "MOCK")
FB_APP_SECRET = get("FB_APP_SECRET", "MOCK")
FB_PAGE_ACCESS_TOKEN = get("FB_PAGE_ACCESS_TOKEN", "MOCK")

# ── Telegram ──
TELEGRAM_BOT_TOKEN = get("TELEGRAM_BOT_TOKEN", "MOCK")

# ── TikTok ──
TIKTOK_SESSION_ID = get("TIKTOK_SESSION_ID", "MOCK")

# ── Vercel ──
VERCEL_PROJECT_NAME = get("VERCEL_PROJECT_NAME", "fb-property-site")
VERCEL_TOKEN = get("VERCEL_TOKEN", "MOCK")

# ── Security ──
SECRET_KEY = get("SECRET_KEY", "dev-secret-change-in-production")
LICENSE_HMAC_KEY = get("LICENSE_HMAC_KEY", "dev-hmac-key-change-in-production")

# ── Status ──
def status() -> dict:
    """回傳目前所有設定狀態（隱藏敏感值）"""
    return {
        "ollama": {"host": OLLAMA_HOST, "model": OLLAMA_MODEL},
        "openai": "mock" if OPENAI_MOCK else f"key={OPENAI_API_KEY[:8]}...",
        "facebook_api": "mock" if is_mock("FB_APP_ID") else "configured",
        "telegram": "mock" if is_mock("TELEGRAM_BOT_TOKEN") else "configured",
        "tiktok": "mock" if is_mock("TIKTOK_SESSION_ID") else "configured",
        "vercel": "mock" if is_mock("VERCEL_TOKEN") else "configured",
        "post_interval": f"{POST_INTERVAL_MIN}-{POST_INTERVAL_MAX}s",
        "delete_after": f"{DELETE_AFTER_HOURS}h",
        "auto_clean": f"daily at {AUTO_CLEAN_HOUR}:{AUTO_CLEAN_MINUTE:02d}",
    }
