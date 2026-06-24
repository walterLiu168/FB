"""隨機延遲、文字、圖片插入工具 — 突破 FB 重複偵測"""
import random
import time


def random_delay(min_sec: float = 60, max_sec: float = 360):
    """隨機等待 min_sec ~ max_sec 秒，模擬真人操作節奏"""
    delay = random.uniform(min_sec, max_sec)
    time.sleep(delay)
    return delay


def short_delay(min_sec: float = 2, max_sec: float = 8):
    """短暫隨機等待，用於頁面操作之間"""
    delay = random.uniform(min_sec, max_sec)
    time.sleep(delay)
    return delay


def human_typing_delay():
    """模擬真人打字節奏的微小延遲 (50~200ms)"""
    time.sleep(random.uniform(0.05, 0.2))


def random_string(prefix: str = "", length: int = 8) -> str:
    """產生隨機字串，突破 FB 重複發文偵測"""
    chars = "abcdefghijklmnopqrstuvwxyz0123456789"
    suffix = "".join(random.choice(chars) for _ in range(length))
    return f"{prefix}{suffix}"


def random_suffix() -> str:
    """產生隨機後綴，附加在文案末尾"""
    tags = [
        f"\n\n#{random_string('', 6)}",
        f"\n.\n.",
        f"\n{' '.join(random.sample(['🔥','💥','⚡','📌','✅'], k=random.randint(1,3)))}",
        f"\n({random.choice(['今日限定','限時優惠','熱銷中','搶手物件','即將售罄'])})",
    ]
    return random.choice(tags)


def random_user_agent() -> str:
    """隨機 User-Agent 輪換（版本號對齊 Playwright 內建 Chromium）"""
    major = random.choice([126, 127, 128, 129, 130])
    minor = random.randint(0, 99)
    build = random.randint(4000, 6999)

    agents = [
        f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{major}.0.{build}.{minor} Safari/537.36",
        f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{major}.0.{build}.{minor} Safari/537.36",
        f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{major}.0.{build}.{minor} Safari/537.36 Edg/{major}.0.{build}.{minor}",
        f"Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
        f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{major}.0.{build}.{minor} Safari/537.36",
    ]
    return random.choice(agents)


def random_viewport() -> dict:
    """隨機視窗尺寸（台灣常見螢幕解析度）"""
    sizes = [
        {"width": 1920, "height": 1040},
        {"width": 1920, "height": 1080},
        {"width": 1536, "height": 864},
        {"width": 1440, "height": 900},
        {"width": 1366, "height": 768},
        {"width": 1600, "height": 900},
    ]
    return random.choice(sizes)


def random_accept_language() -> str:
    """隨機 Accept-Language header"""
    variants = [
        "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        "zh-TW,zh;q=0.9,en;q=0.8,ja;q=0.7",
        "zh-TW,zh;q=0.9",
    ]
    return random.choice(variants)


def random_sec_ch_ua() -> str:
    """隨機 Sec-CH-UA header（Chrome 版本標記）"""
    major = random.choice([126, 127, 128, 129, 130])
    return f'"Chromium";v="{major}", "Not-A.Brand";v="24", "Google Chrome";v="{major}"'


def random_sec_ch_ua_platform() -> str:
    return '"Windows"'
