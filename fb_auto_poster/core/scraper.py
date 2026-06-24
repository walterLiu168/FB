"""圖片爬取 + AI 物件資訊提取工具
"""
import asyncio
import json
import os
import re
import uuid
import urllib3
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from PIL import Image

from utils.config import get_data_path

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ── 共享瀏覽器（由 app.py 設定，避免每次重新開啟） ──
_shared_browser = None          # BrowserManager (async)
_shared_event_loop = None       # asyncio event loop of the engine thread
_IMG_DOWNLOAD_POOL = ThreadPoolExecutor(max_workers=4)


def set_shared_browser(browser, event_loop):
    """設定共享瀏覽器與事件迴圈，讓 rakuya 操作不用重開瀏覽器"""
    global _shared_browser, _shared_event_loop
    _shared_browser = browser
    _shared_event_loop = event_loop


def _session_dir() -> str:
    now = datetime.now().strftime("%Y-%m-%d_%H")
    path = get_data_path(os.path.join("temp_images", now))
    os.makedirs(path, exist_ok=True)
    return path


def _is_image_url(url: str) -> bool:
    parsed = urlparse(url)
    path = parsed.path.lower()
    return any(path.endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"])


def _download_image(url: str) -> Optional[str]:
    dest_dir = _session_dir()
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        resp = requests.get(url, headers=headers, timeout=15, verify=False)
        resp.raise_for_status()

        ext = os.path.splitext(urlparse(url).path)[1] or ".jpg"
        filename = f"{uuid.uuid4().hex}{ext}"
        filepath = os.path.join(dest_dir, filename)

        with open(filepath, "wb") as f:
            f.write(resp.content)

        try:
            img = Image.open(filepath)
            img.verify()
            return filepath
        except Exception:
            os.remove(filepath)
            return None
    except Exception:
        return None


def _download_images_parallel(urls: list[str], max_count: int) -> list[str]:
    """並行下載圖片，限 max_count 張"""
    results = []
    futures = {_IMG_DOWNLOAD_POOL.submit(_download_image, u): u for u in urls[:max_count * 2]}
    for f in as_completed(futures):
        path = f.result()
        if path:
            results.append(path)
            if len(results) >= max_count:
                break
    return results


# ═══════════════════════════════════════════════════════════════════
#  主入口
# ═══════════════════════════════════════════════════════════════════

def scrape_images_from_url(url: str, max_images: int = 5) -> list[str]:
    """從網址爬取圖片（並行下載）"""
    if not url or not url.strip():
        return []
    url = url.strip()

    if _is_image_url(url):
        path = _download_image(url)
        return [path] if path else []

    if "rakuya.com.tw" in url:
        return _scrape_images_rakuya_shared(url, max_images)

    # ── 一般 HTML ──
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        resp = requests.get(url, headers=headers, timeout=12, verify=False)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        seen = set()
        all_urls = []

        # og:image
        for meta in soup.find_all("meta", property="og:image"):
            s = meta.get("content", "")
            if s and s not in seen:
                seen.add(s); all_urls.append(s)

        # All <img>
        for img in soup.find_all("img"):
            for attr in ("src", "data-src", "data-original", "data-lazy", "data-large"):
                s = img.get(attr, "")
                if s and s not in seen and not s.startswith("data:"):
                    seen.add(s); all_urls.append(s)
            srcset = img.get("srcset", "")
            if srcset:
                cands = re.findall(r"(\S+)\s+(\d+)w", srcset)
                if cands:
                    best = max(cands, key=lambda x: int(x[1]))[0]
                    if best and best not in seen and not best.startswith("data:"):
                        seen.add(best); all_urls.append(best)

        # background-image
        for el in soup.find_all(style=re.compile(r"background-image\s*:")):
            m = re.search(r"url\(['\"]?(.*?)['\"]?\)", el.get("style", ""))
            if m and m.group(1) not in seen:
                seen.add(m.group(1)); all_urls.append(m.group(1))

        # 補全路徑
        parsed = urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        fixed = []
        for s in all_urls:
            if s.startswith("//"):
                s = "https:" + s
            elif s.startswith("/"):
                s = base + s
            if s.startswith("http"):
                fixed.append(s)

        return _download_images_parallel(fixed, max_images)

    except Exception as e:
        print(f"[Scraper] 爬取失敗: {e}")
        return []


def _scrape_images_rakuya_shared(url: str, max_images: int = 5) -> list[str]:
    """從 rakuya 爬取圖片 — 使用獨立 Playwright（含 stealth args 繞 Cloudflare）"""
    return _scrape_images_fallback(url, max_images)


def clean_temp_images():
    import shutil
    base = get_data_path("temp_images")
    if os.path.exists(base):
        shutil.rmtree(base, ignore_errors=True)


def _scrape_images_fallback(url: str, max_images: int = 5) -> list[str]:
    """備用：無共享瀏覽器時用獨立 Playwright（含 stealth args）"""
    paths = []
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
            ])
            ctx = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080},
            )
            page = ctx.new_page()
            page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
                window.chrome = {runtime: {}};
            """)
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(5000)
                img_urls = page.evaluate("""()=>{
                    const u=new Set();
                    document.querySelectorAll('img').forEach(i=>{
                        let s=i.src||''; if(s&&!s.startsWith('data:')&&i.offsetWidth>80&&i.offsetHeight>80)u.add(s);
                        ['data-src','data-original','data-lazy'].forEach(a=>{let d=i.getAttribute(a)||''; if(d)u.add(d);});
                    });
                    return Array.from(u);
                }""") or []
                for iu in img_urls[:max_images]:
                    p = _download_image(iu)
                    if p: paths.append(p)
            except Exception:
                pass
            finally:
                browser.close()
    except Exception:
        pass
    return paths


# ═══════════════════════════════════════════════════════════════════
#  物件資訊提取
# ═══════════════════════════════════════════════════════════════════

def _is_cloudflare_blocked(text: str) -> bool:
    if len(text) < 8000 and ("Just a moment..." in text or "cf-challenge" in text):
        return True
    return False


def _fetch_rendered_with_playwright(url: str) -> str:
    """使用獨立 Playwright（含 stealth args）取得 JS 渲染後的頁面文字。

    專為 rakuya 等 Cloudflare 保護網站設計。
    """
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
                "--disable-site-isolation-trials",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-web-security",
                "--disable-dev-shm-usage",
            ])
            ctx = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080},
                device_scale_factor=1,
                is_mobile=False,
                has_touch=False,
            )
            page = ctx.new_page()
            # 注入反偵測腳本
            page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
                window.chrome = {runtime: {}};
            """)
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(5000)
                return page.locator("body").text_content(timeout=5000) or ""
            except Exception:
                return ""
            finally:
                browser.close()
    except Exception:
        return ""


def _fetch_rakuya_text_shared(url: str) -> str:
    """從 rakuya 取得渲染後文字。

    直接使用獨立 Playwright（含 stealth args），不使用共享瀏覽器，
    因為 rakuya 需要乾淨 non-FB context 才能繞過 Cloudflare。
    """
    return _fetch_rendered_with_playwright(url)


async def _fetch_text_rakuya_async(url: str) -> str:
    """async: 用共享瀏覽器取得 rakuya 頁面文字（新建乾淨 context）"""
    try:
        # 不復用 FB 帳號的 context，創一個乾淨的（共享瀏覽器的 stealth 已生效）
        page = await _shared_browser.new_page()
        if not page:
            return ""
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(5)
            return await page.locator("body").text_content(timeout=5000) or ""
        finally:
            # 用完關掉這個臨時 page
            await _shared_browser.close_page(page)
    except Exception:
        return ""


def _extract_with_regex(text: str, soup: BeautifulSoup = None) -> dict:
    """用正則從文字提取物件資訊"""
    result = {}
    # 價格
    pm = re.search(r"(\d[\d,]*\s*[萬億])", text)
    if pm: result["price"] = pm.group(1).strip()
    # 坪數
    sm = re.search(r"(\d+\.?\d*)\s*坪", text)
    if sm: result["size"] = sm.group(0).strip()
    # 格局
    rm = re.search(r"(\d房\d廳\d衛|\d房\d廳|\d房\d衛|\d房)", text)
    if rm: result["rooms"] = rm.group(1).strip()
    # 類型
    for t in ("別墅","透天厝","透天","電梯大廈","華廈","公寓","大樓","店面"):
        if t in text: result["type"] = t; break
    # 車位
    for pk in ("有車位","無車位","坡道平面","機械車位","平面車位"):
        if pk in text: result["parking"] = pk; break
    # 朝向
    om = re.search(r"[座坐][東南西北]+朝[東南西北]+", text)
    if om: result["orientation"] = om.group(0)
    # 樓層
    fm = re.search(r"(\d+/\d+樓|全/\d+樓)", text)
    if fm: result["floor"] = fm.group(1)
    # 屋齡
    am = re.search(r"(\d+\.?\d*年)", text)
    if am: result["age"] = am.group(1)
    # title
    if soup:
        tt = soup.find("title")
        if tt:
            result["title"] = re.sub(r"\s*[|｜\-–—]\s*.*$", "", tt.get_text(strip=True)).strip()
    # desc
    if soup:
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc and meta_desc.get("content"):
            result["description"] = meta_desc["content"].strip()[:200]
    return result


def _extract_rakuya_info(text: str) -> dict:
    """從 rakuya 渲染文字提取物件資訊"""
    # 先清理所有網站 UI 垃圾
    text = _clean_rakuya_text(text)

    result = {}
    # ── 價格 ──
    prices_raw = re.findall(r"([\d,]+)\s*萬", text)
    valid_prices = [int(p.replace(",", "")) for p in prices_raw if p.replace(",", "").isdigit()]
    if valid_prices:
        total_match = re.search(r"總價[：:\s]*([\d,]+)\s*萬", text)
        if total_match:
            try:
                result["price"] = f"{int(total_match.group(1).replace(',','')):,} 萬"
            except ValueError:
                result["price"] = f"{total_match.group(1)} 萬"
        else:
            filtered = [p for p in valid_prices if p > 200]
            if filtered:
                mid = sorted(filtered)[len(filtered)//2]
                result["price"] = f"{mid:,} 萬"

    # ── 坪數：優先找「總坪」「建坪」「權狀」，而非第一個坪數 ──
    size = ""
    for pat in [r"總坪?數?\s*[：:\s]*([\d.]+)\s*坪",
                r"建坪\s*[：:\s]*([\d.]+)\s*坪",
                r"建物.*?([\d.]+)\s*坪",
                r"(?:權狀|登記)\s*[：:\s]*([\d.]+)\s*坪"]:
        m = re.search(pat, text)
        if m:
            main = m.group(1)
            # 找車位坪數跟在後面
            parking_size = ""
            after = text[m.end():m.end()+80]
            pk = re.search(r"(?:含|含車位|車位)\s*[：:\s]*([\d.]+)\s*坪", after)
            if pk:
                parking_size = f"含車位{pk.group(1)}坪"
                size = f"{main}坪 ({parking_size})"
            else:
                size = f"{main}坪"
            break

    if not size:
        # Fallback: 最後一個有意義的坪數（通常是總坪）
        all_sizes = re.findall(r"([\d.]+)坪", text)
        if all_sizes:
            # 取數值最大者（通常是總坪，非主建坪）
            nums = [float(s) for s in all_sizes]
            max_idx = nums.index(max(nums))
            size = f"{all_sizes[max_idx]}坪"

    if size:
        result["size"] = size

    # ── 格局 ──
    rm = re.search(r"(\d房\d廳\d?衛?)", text)
    if rm: result["rooms"] = rm.group(1)

    # ── 類型：從文字中比對已知類型關鍵字，取第一個 ──
    ptype = ""
    ptype_list = ("電梯大廈","華廈","公寓","大樓","透天厝","別墅","透天","店面")
    # 找最早出現的類型（不是全文字首見，而是第一個匹配到的具體字串）
    earliest_idx = len(text)
    for t in ptype_list:
        idx = text.find(t)
        if idx != -1 and idx < earliest_idx:
            earliest_idx = idx
            ptype = t
    if ptype:
        result["type"] = ptype

    # ── 樓層 ──
    fm = re.search(r"(\d+/\d+樓|全/\d+樓)", text)
    if fm: result["floor"] = fm.group(1)

    # ── 屋齡 ──
    am = re.search(r"(\d+\.?\d*年)", text)
    if am: result["age"] = am.group(1)

    # ── 車位 ──
    for pk in ("有車位","無車位","坡道平面","機械車位","平面車位"):
        if pk in text: result["parking"] = pk; break

    # ── 朝向 ──
    om = re.search(r"[座坐][東南西北]+朝[東南西北]+", text)
    if om: result["orientation"] = om.group(0)

    # ── 標題 ──
    tm = re.search(r"目前物件(.+?)(?:\s|分享|照片)", text)
    if tm: result["title"] = tm.group(1).strip()

    # ── 地點（只保留 市區，去掉路名）──
    lm = re.findall(r"([\u4e00-\u9fff]+(?:市|縣)[\u4e00-\u9fff]+(?:區|鎮|鄉))", text)
    if lm:
        best = max(lm, key=len)
        # 清理前綴雜訊（數字、單字「萬」等）
        best = re.sub(r'^[\d萬億,，]+\s*', '', best)
        result["location"] = best

    # ── 描述：從「特色描述」段落提取，排除 UI 垃圾 ──
    desc = ""
    desc_match = re.search(r"特色描述\s*\n?\s*(.+?)(?:\n\s*\n|\Z)", text, re.DOTALL)
    if desc_match:
        raw_desc = desc_match.group(1).strip()
        # 清理：移除標籤符號和網站 UI 文字
        raw_desc = re.sub(r'[＃#]\s*[^\s\n,，]+', '', raw_desc)   # 移除 #hashtags
        raw_desc = re.sub(r'點選標籤.*?！', '', raw_desc)          # 移除網站提示
        raw_desc = re.sub(r'\s+', ' ', raw_desc).strip()
        if raw_desc and len(raw_desc) > 5:
            desc = raw_desc
    result["description"] = desc

    return result


def _clean_rakuya_text(text: str) -> str:
    """清除 rakuya 頁面中的網站 UI 垃圾文字"""
    # 移除含標籤/網站提示的區塊
    text = re.sub(r'點選標籤，.*?！', '', text)
    text = re.sub(r'[＃#]\s*有[^\s\n]+', '', text)
    text = re.sub(r'[＃#]\s*雙[^\s\n]+', '', text)
    text = re.sub(r'[＃#]\s*近[^\s\n]+', '', text)
    text = re.sub(r'[＃#]\s*[^\s\n,，]{2,6}', '', text)  # 剩餘 hashtags
    text = re.sub(r'特色標籤\s*', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text


def extract_property_info(url: str) -> dict:
    """從房仲網頁提取結構化物件資訊"""
    result = {"title":"","price":"","location":"","type":"","size":"","rooms":"","floor":"","age":"","parking":"","orientation":"","description":""}

    is_rakuya = "rakuya.com.tw" in url
    if is_rakuya:
        rendered_text = _fetch_rakuya_text_shared(url)
        if rendered_text:
            info = _extract_rakuya_info(rendered_text)
            if info: return {**result, **info}
            text_sample = rendered_text[:3000]
        else:
            return result
    else:
        try:
            headers = {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            resp = requests.get(url, headers=headers, timeout=12, verify=False)
            resp.raise_for_status()
            if _is_cloudflare_blocked(resp.text):
                rendered_text = _fetch_rendered_with_playwright(url)
                if not rendered_text: return result
                text_sample = rendered_text[:3000]
            else:
                soup = BeautifulSoup(resp.text, "html.parser")
                for t in soup(["script","style","noscript","iframe"]): t.decompose()
                page_text = soup.get_text(separator="\n", strip=True)
                text_sample = page_text[:3000]
        except Exception:
            return result

    # AI extraction fallback
    try:
        ai_result = _extract_with_ollama(text_sample, url)
        if ai_result: return {**result, **ai_result}
    except Exception:
        pass

    result.update(_extract_with_regex(text_sample))
    return result


def _extract_with_ollama(text: str, url: str) -> Optional[dict]:
    try:
        resp = requests.post(
            "http://localhost:11434/api/generate",
            json={"model":"llama3.2","prompt":f"""請從以下房屋網頁文字中提取物件資訊，以 JSON 格式回傳（只有 JSON，不要任何前言）：
{{"title":"","price":"","location":"","type":"","size":"","rooms":"","floor":"","age":"","parking":"","orientation":"","description":""}}
如果找不到某欄位留空。
網頁文字：{text[:2500]}""","stream":False,"temperature":0.1},
            timeout=8,
        )
        if resp.status_code == 200:
            raw = resp.json().get("response","").strip()
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if m: return json.loads(m.group())
    except Exception:
        pass
    return None


def clean_temp_images():
    import shutil
    base = get_data_path("temp_images")
    if os.path.exists(base):
        shutil.rmtree(base, ignore_errors=True)


def get_temp_image_count() -> int:
    base = get_data_path("temp_images")
    if not os.path.exists(base): return 0
    return sum(len([f for f in files if f.endswith((".jpg",".jpeg",".png",".gif",".webp"))]) for _,_,files in os.walk(base))
