"""多站物件資料提取器 (Multi-Site Property Extractor)

支援網站：
  - 591 房屋交易網 (租/售/商辦/土地)
  - 永慶房屋
  - 信義房屋
  - 樂屋網 (rakuya)
  - 住商不動產

架構：每個網站一個 extractor 函式，註冊到路由器自動分派。
無需外部設定，貼上 URL 自動辨識並提取。
"""

import re
import json
import logging
from typing import Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ── 網站辨識路由表 ──
_SITE_ROUTER = {}

def register_site(domains: list[str]):
    """裝飾器：將函式註冊為特定網站的提取器"""
    def decorator(func):
        for domain in domains:
            _SITE_ROUTER[domain] = func
        return func
    return decorator


def identify_site(url: str) -> Optional[str]:
    """從 URL 辨識來源網站"""
    domain = urlparse(url).netloc.lower()
    for key in _SITE_ROUTER:
        if key in domain:
            return key
    return None


def extract_from_url(url: str, timeout: int = 15) -> dict:
    """主入口：從 URL 提取物件資訊

    Args:
        url: 物件網址
        timeout: HTTP 請求超時秒數

    Returns:
        {
            "title": str, "price": str, "location": str,
            "size": str, "rooms": str, "type": str,
            "floor": str, "age": str, "parking": str,
            "orientation": str, "intro": str,
            "images": [str, ...], "site": str, "raw_url": str
        }
        若無法辨識網站或提取失敗，回傳空 dict
    """
    site = identify_site(url)
    if not site:
        logger.warning(f"未支援的網站: {url}")
        return {"site": "unknown", "raw_url": url}

    extractor = _SITE_ROUTER.get(site)
    if not extractor:
        return {"site": site, "raw_url": url}

    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
        }
        resp = requests.get(url, headers=headers, timeout=timeout)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        text = soup.get_text(separator="\n")

        result = extractor(soup, text, url)
        result["site"] = site
        result["raw_url"] = url

        # 提取圖片
        images = _extract_images(soup, url)
        if images:
            result["images"] = images[:20]  # 最多 20 張

        return result

    except requests.Timeout:
        logger.error(f"提取逾時: {url}")
        return {"site": site, "raw_url": url, "error": "timeout"}
    except Exception as e:
        logger.error(f"提取失敗 {url}: {e}")
        return {"site": site, "raw_url": url, "error": str(e)[:100]}


def _extract_images(soup: BeautifulSoup, base_url: str) -> list[str]:
    """從頁面提取圖片 URL 列表"""
    images = []
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or img.get("data-original")
        if not src:
            continue
        if src.startswith("//"):
            src = "https:" + src
        elif src.startswith("/"):
            from urllib.parse import urljoin
            src = urljoin(base_url, src)
        if src.startswith("http") and any(ext in src.lower() for ext in [".jpg", ".jpeg", ".png", ".webp"]):
            images.append(src)
    return list(dict.fromkeys(images))  # 去重保持順序


# ═══════════════════════════════════════════
#  591 房屋交易網
# ═══════════════════════════════════════════

@register_site(["591.com.tw", "rent.591.com.tw", "sale.591.com.tw", "business.591.com.tw", "land.591.com.tw"])
def _extract_591(soup: BeautifulSoup, text: str, url: str) -> dict:
    result = {}

    # 標題
    title_el = soup.select_one("h1.detail-title-content, .infoTitle, h1.infoTitle")
    if title_el:
        result["title"] = title_el.get_text(strip=True)
    else:
        # fallback: meta og:title
        meta_title = soup.select_one('meta[property="og:title"]')
        if meta_title:
            result["title"] = meta_title.get("content", "").strip()

    # 價格 — 從 .price 或 meta
    price_el = soup.select_one(".price, .price-tag, .detail-price, .info-price")
    if price_el:
        price_text = price_el.get_text(strip=True)
        # 清理: "988 萬" or "1,280萬"
        m = re.search(r"([\d,\.]+\s*萬)", price_text)
        if m:
            result["price"] = m.group(1).replace(",", "") + " 萬"
        else:
            result["price"] = re.sub(r"\s+", " ", price_text)

    # 從文字中提取結構化資訊
    # 地點：XX市XX區
    m_loc = re.search(r"([\u4e00-\u9fff]+(?:市|縣)[\u4e00-\u9fff]+(?:區|鎮|鄉))", text)
    if m_loc:
        result["location"] = m_loc.group(1)

    # 坪數
    m_size = re.search(r"((?:[\d,\.]+)\s*坪)", text)
    if m_size:
        result["size"] = m_size.group(1).replace(",", "")

    # 格局：X房X廳X衛
    m_rooms = re.search(r"((?:\d+)\s*房\s*(?:\d+)\s*廳\s*(?:\d+)\s*衛)", text)
    if m_rooms:
        result["rooms"] = re.sub(r"\s+", "", m_rooms.group(1))
    else:
        # 純數字: 房/廳/衛 從 broup-attribute
        rooms_parts = []
        for label in ["房", "廳", "衛"]:
            m = re.search(rf"(\d+)\s*{label}", text)
            if m:
                rooms_parts.append(m.group(0).replace(" ", ""))
        if rooms_parts:
            result["rooms"] = "".join(rooms_parts)

    # 類型 (華廈/大樓/透天...)
    m_type = re.search(r"(華廈|大樓|公寓|透天|電梯大樓|別墅|套房)", text)
    if m_type:
        result["type"] = m_type.group(1)

    # 樓層 (X/Y樓 或 第X層)
    m_floor = re.search(r"([\d]+/[\d]+\s*樓|[總全]樓.*?[\d]+層)", text)
    if m_floor:
        result["floor"] = re.sub(r"\s+", "", m_floor.group(1))

    # 屋齡
    m_age = re.search(r"([\d\.]+\s*年)\s*(屋齡|建物|建築)", text)
    if m_age:
        result["age"] = m_age.group(1) + "屋齡"

    # 車位
    if re.search(r"(車位|停車位|平面車位|機械車位)", text):
        m_parking = re.search(r"((?:平面|機械|坡道)?\s*(?:車位|停車位))", text)
        if m_parking:
            result["parking"] = m_parking.group(1)

    # 朝向
    m_dir = re.search(r"(坐[東西南北]朝[東西南北])", text)
    if m_dir:
        result["orientation"] = m_dir.group(1)

    # 介紹 — 取描述區塊
    desc_el = soup.select_one(".detail-description, .description-content, .house-description, .info-desc")
    if desc_el:
        result["intro"] = desc_el.get_text("\n", strip=True)[:500]
    else:
        # fallback: meta description
        meta_desc = soup.select_one('meta[name="description"]')
        if meta_desc:
            result["intro"] = meta_desc.get("content", "")[:500]

    return _clean_result(result)


# ═══════════════════════════════════════════
#  永慶房屋
# ═══════════════════════════════════════════

@register_site(["yungching.com.tw", "yungching.house"])
def _extract_yungching(soup: BeautifulSoup, text: str, url: str) -> dict:
    result = {}

    # og:title 通常包含完整資訊
    meta_title = soup.select_one('meta[property="og:title"]')
    if meta_title:
        result["title"] = meta_title.get("content", "").strip()

    # 地點
    m_loc = re.search(r"([\u4e00-\u9fff]+(?:市|縣)[\u4e00-\u9fff]+(?:區|鎮|鄉))", text)
    if m_loc:
        result["location"] = m_loc.group(1)

    m_price = re.search(r"([\d,\.]+\s*萬)", text)
    if m_price:
        result["price"] = m_price.group(1).replace(",", "") + " 萬"

    m_size = re.search(r"((?:[\d,\.]+)\s*坪)", text)
    if m_size:
        result["size"] = m_size.group(1).replace(",", "")

    m_rooms = re.search(r"((?:\d+)\s*房\s*(?:\d+)\s*廳\s*(?:\d+)\s*衛)", text)
    if m_rooms:
        result["rooms"] = re.sub(r"\s+", "", m_rooms.group(1))

    m_type = re.search(r"(華廈|大樓|公寓|透天|電梯大樓)", text)
    if m_type:
        result["type"] = m_type.group(1)

    m_floor = re.search(r"([\d]+/[\d]+\s*樓)", text)
    if m_floor:
        result["floor"] = re.sub(r"\s+", "", m_floor.group(1))

    m_age = re.search(r"([\d\.]+\s*年)", text)
    if m_age:
        result["age"] = m_age.group(1) + "屋齡"

    desc_el = soup.select_one(".house-description, .obj-description, [class*='description']")
    if desc_el:
        result["intro"] = desc_el.get_text("\n", strip=True)[:500]

    return _clean_result(result)


# ═══════════════════════════════════════════
#  信義房屋
# ═══════════════════════════════════════════

@register_site(["sinyi.com.tw", "sinyi.house"])
def _extract_sinyi(soup: BeautifulSoup, text: str, url: str) -> dict:
    result = {}

    meta_title = soup.select_one('meta[property="og:title"]')
    if meta_title:
        result["title"] = meta_title.get("content", "").strip()

    m_loc = re.search(r"([\u4e00-\u9fff]+(?:市|縣)[\u4e00-\u9fff]+(?:區|鎮|鄉))", text)
    if m_loc:
        result["location"] = m_loc.group(1)

    m_price = re.search(r"([\d,\.]+\s*萬)", text)
    if m_price:
        result["price"] = m_price.group(1).replace(",", "") + " 萬"

    m_size = re.search(r"((?:[\d,\.]+)\s*坪)", text)
    if m_size:
        result["size"] = m_size.group(1).replace(",", "")

    m_rooms = re.search(r"((?:\d+)\s*房\s*(?:\d+)\s*廳\s*(?:\d+)\s*衛)", text)
    if m_rooms:
        result["rooms"] = re.sub(r"\s+", "", m_rooms.group(1))

    m_type = re.search(r"(華廈|大樓|公寓|透天|電梯大樓|別墅)", text)
    if m_type:
        result["type"] = m_type.group(1)

    desc_el = soup.select_one("[class*='description'], [class*='desc']")
    if desc_el:
        result["intro"] = desc_el.get_text("\n", strip=True)[:500]

    return _clean_result(result)


# ═══════════════════════════════════════════
#  樂屋網 (rakuya)
# ═══════════════════════════════════════════

@register_site(["rakuya.com.tw"])
def _extract_rakuya(soup: BeautifulSoup, text: str, url: str) -> dict:
    result = {}

    meta_title = soup.select_one('meta[property="og:title"]')
    if meta_title:
        result["title"] = meta_title.get("content", "").strip()

    m_loc = re.search(r"([\u4e00-\u9fff]+(?:市|縣)[\u4e00-\u9fff]+(?:區|鎮|鄉))", text)
    if m_loc:
        result["location"] = m_loc.group(1)

    m_price = re.search(r"([\d,\.]+\s*萬)", text)
    if m_price:
        result["price"] = m_price.group(1).replace(",", "") + " 萬"

    m_size = re.search(r"((?:[\d,\.]+)\s*坪)", text)
    if m_size:
        result["size"] = m_size.group(1).replace(",", "")

    m_rooms = re.search(r"((?:\d+)\s*房\s*(?:\d+)\s*廳\s*(?:\d+)\s*衛)", text)
    if m_rooms:
        result["rooms"] = re.sub(r"\s+", "", m_rooms.group(1))

    m_type = re.search(r"(華廈|大樓|公寓|透天|電梯大樓|別墅|套房)", text)
    if m_type:
        result["type"] = m_type.group(1)

    m_building = re.search(r"([\d]+/[\d]+\s*樓)", text)
    if m_building:
        result["floor"] = re.sub(r"\s+", "", m_building.group(1))

    m_age = re.search(r"([\d\.]+\s*年)\s*(屋齡|建物)", text)
    if m_age:
        result["age"] = m_age.group(0)

    if re.search(r"(車位|停車位)", text):
        m_parking = re.search(r"((?:坡道|升降)?\s*(?:平面|機械)?\s*(?:車位|停車位))", text)
        if m_parking:
            result["parking"] = m_parking.group(1)

    desc_el = soup.select_one('meta[name="description"]')
    if desc_el:
        result["intro"] = desc_el.get("content", "")[:500]

    return _clean_result(result)


# ═══════════════════════════════════════════
#  住商不動產 & 中信房屋 & 東森房屋
# ═══════════════════════════════════════════

@register_site(["hbhousing.com.tw", "cthouse.com.tw", "etwarm.com.tw"])
def _extract_generic_broker(soup: BeautifulSoup, text: str, url: str) -> dict:
    """通用房仲網站提取器"""
    result = {}

    meta_title = soup.select_one('meta[property="og:title"]')
    if meta_title:
        result["title"] = meta_title.get("content", "").strip()

    m_loc = re.search(r"([\u4e00-\u9fff]+(?:市|縣)[\u4e00-\u9fff]+(?:區|鎮|鄉))", text)
    if m_loc:
        result["location"] = m_loc.group(1)

    m_price = re.search(r"([\d,\.]+\s*萬)", text)
    if m_price:
        result["price"] = m_price.group(1).replace(",", "") + " 萬"

    m_size = re.search(r"((?:[\d,\.]+)\s*坪)", text)
    if m_size:
        result["size"] = m_size.group(1).replace(",", "")

    m_rooms = re.search(r"((?:\d+)\s*房\s*(?:\d+)\s*廳\s*(?:\d+)\s*衛)", text)
    if m_rooms:
        result["rooms"] = re.sub(r"\s+", "", m_rooms.group(1))

    m_type = re.search(r"(華廈|大樓|公寓|透天|電梯大樓|別墅|套房)", text)
    if m_type:
        result["type"] = m_type.group(1)

    return _clean_result(result)


def _clean_result(data: dict) -> dict:
    """清理結果：移除 None/空白值，確保格式一致"""
    cleaned = {}
    for k, v in data.items():
        if v and isinstance(v, str) and v.strip():
            cleaned[k] = v.strip()
        elif v and not isinstance(v, str):
            cleaned[k] = v
    return cleaned


# ── 便捷函數 ──
def get_supported_sites() -> list[str]:
    """回傳支援的網站列表"""
    return sorted(set(_SITE_ROUTER.keys()))
