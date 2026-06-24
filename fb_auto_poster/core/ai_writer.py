"""AI 文案生成 — 串接 Ollama 本地 LLM + 物件資訊整合生成"""
import json
import random
import requests
from typing import Optional

# Ollama 預設 API 端點
OLLAMA_API = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "llama3.2"

# 模板文案（Ollama 離線時使用）
_FALLBACK_TEMPLATES = [
    "🔥 超值好物件！{title} 只要 {price}，地點 {location}，錯過不再！\n歡迎私訊預約看屋 📞",
    "🏠 {title}｜{location}\n💰 {price}\n✨ 全新上市，稀有釋出，立即來電預約！",
    "⚡ 限時優惠！{title}\n📍 {location} ｜ 💵 {price}\n好房不等人，快搶！",
    "✨ {title}｜{location}\n價格：{price}\n格局方正，採光通風佳，歡迎預約賞屋 🙌",
]

_FALLBACK_FULL = """🏠 {title}
📍 {location_rewrite}
💰 價格: {price}

{extra}

歡迎預約看屋 📞 私訊或留言立即安排！"""


def _build_property_prompt(info: dict, header: str = "", footer: str = "") -> str:
    """從物件資訊 dict 建立完整的 FB 貼文 prompt"""
    # 清理 description 欄位後再放入 prompt
    import re
    clean_info = {}
    for k, v in info.items():
        if v:
            v = str(v)
            if k == "description":
                v = re.sub(r'[＃#]\s*\S+', '', v)
                v = re.sub(r'點選標籤.*?！', '', v)
                v = re.sub(r'特色描述\s*', '', v)
                v = re.sub(r'\s+', ' ', v).strip()
            if k == "location":
                # 只送簡化的區域（不要完整地址），讓 AI 用自己的話表達
                v = re.sub(r'^[\d萬億,.\s]+', '', v)
                v = re.sub(r'[路街巷弄號樓].*$', '', v)
            if k == "size":
                # 去「含車位」括弧，讓 AI 自己決定如何呈現
                v = re.sub(r'\s*[\(（]含車位[^)）]*[\)）]', '', v)
            clean_info[k] = v

    fields = []
    for k, v in clean_info.items():
        if v:
            fields.append(f"- {k}: {v}")

    desc_part = ""
    if "description" in clean_info:
        desc_text = clean_info["description"]
        if desc_text:
            desc_part = f"\n原始描述（請用自己的話重寫，不要複製貼上）：{desc_text}"

    return f"""你是一個專業的房仲行銷文案專家。請根據以下房屋物件資訊，產生一篇完整的 Facebook 貼文文案。

物件資訊：
{chr(10).join(fields)}{desc_part}

寫作要求：
1. 語氣熱情、專業，使用繁體中文（台灣用語）
2. 包含 emoji 增加吸引力（🏠💰📍✨🛏️🚗 等）
3. 先簡短標題（1 行），然後是重點特色（條列式，3-5 點），最後行動呼籲
4. 總長度不超過 200 字
5. 結尾加上行動呼籲（如「歡迎預約賞屋」、「立即私訊」）
6. 不要使用過度誇大的用詞
7. 描述部分必須用你自己的話重寫，不可直接貼上原始文字
8. 🔴 絕不貼原始地址（如「XX路XX號」），改用「中壢商圈」「近學區」等區域特色描述
9. 🔴 絕不出現任何＃標籤或網站 UI 文字（如「點選標籤」「特色標籤」）

請直接輸出文案，不要加任何前言或說明。"""


def generate_property_post(
    property_info: dict,
    header: str = "",
    footer: str = "",
) -> dict:
    """從提取的物件資訊生成完整 FB 貼文文案

    property_info: extract_property_info() 回傳的 dict
    header/footer: 可選的頁首/頁尾

    Returns: {"success": bool, "text": str, "fallback": bool, "error": str}
    """
    # 組合 Header + Body + Footer
    parts = []
    if header:
        parts.append(header)

    # 生成主體
    body = _generate_body_from_property(property_info)
    parts.append(body)

    if footer:
        parts.append(footer)

    return {
        "success": True,
        "text": "\n\n".join(parts),
        "fallback": body.startswith("🏠") or body.startswith("🔥"),  # template starts
        "error": "",
    }


def _generate_body_from_property(info: dict) -> str:
    """從 property dict 生成文案主體（Ollama 或 fallback）"""
    title = info.get("title", "").strip()
    price = info.get("price", "").strip()
    location = info.get("location", "").strip()
    size = info.get("size", "").strip()
    rooms = info.get("rooms", "").strip()
    floor = info.get("floor", "").strip()
    age = info.get("age", "").strip()
    parking = info.get("parking", "").strip()
    orientation = info.get("orientation", "").strip()
    ptype = info.get("type", "").strip()
    desc = info.get("description", "").strip()

    # 清理 description：移除任何殘留的 hashtags / UI 文字
    import re
    desc = re.sub(r'[＃#]\s*\S+', '', desc)
    desc = re.sub(r'點選標籤.*?！', '', desc)
    desc = re.sub(r'\s+', ' ', desc).strip()

    # 嘗試用 Ollama
    ollama_ok = _is_ollama_running()
    if ollama_ok:
        prompt = _build_property_prompt(info)
        try:
            resp = requests.post(
                OLLAMA_API,
                json={"model": DEFAULT_MODEL, "prompt": prompt, "stream": False, "temperature": 0.7},
                timeout=60,
            )
            if resp.status_code == 200:
                text = resp.json().get("response", "").strip()
                if text:
                    return text
        except Exception:
            pass

    # Fallback: 模板組合，所有欄位 AI 重寫不貼原始文字
    import re

    # ── 地點：不貼完整地址，改用區域概括 ──
    loc_display = ""
    if location:
        # 只保留 市/區 層級（不要路名）
        loc_short = re.sub(r'^[\d萬億,.\s]+', '', location)
        loc_short = re.sub(r'[路街巷弄號樓].*$', '', loc_short)
        if loc_short:
            loc_display = loc_short

    # ── 坪數：去「含車位」細節，只留主坪數 ──
    size_display = size or ""
    size_display = re.sub(r'\s*[\(（]含車位[^)）]*[\)）]', '', size_display)

    # ── 車位坪數獨立 ──
    parking_size_str = ""
    if size:
        pm = re.search(r'[含含車位]\s*[：:\s]*([\d.]+)\s*坪', size)
        if pm:
            parking_size_str = pm.group(1)

    extra_lines = []
    if ptype:
        extra_lines.append(f"🏗️ 類型: {ptype}")
    if size_display:
        extra_lines.append(f"📐 坪數: {size_display}")
    if parking_size_str:
        extra_lines.append(f"🅿️ 車位坪數: {parking_size_str}坪")
    if rooms:
        extra_lines.append(f"🛏️ 格局: {rooms}")
    if floor:
        extra_lines.append(f"🏢 {floor}")
    if age:
        extra_lines.append(f"📅 {age}")
    if parking:
        extra_lines.append(f"🚗 {parking}")
    if orientation:
        extra_lines.append(f"🧭 {orientation}")
    if desc:
        # AI-重寫：只用精華短句
        short = desc.split("。")[0].strip()
        if not short:
            short = desc.split("，")[0].strip()
        if short and len(short) > 3:
            # 移除任何殘留的 hashtag
            short = re.sub(r'[＃#]\s*\S+', '', short).strip()
            if short:
                extra_lines.append(f"\n✨ {short}")

    extra = "\n".join(extra_lines) if extra_lines else "稀有釋出，錯過不再！"

    if not title:
        title = "精選好屋"

    return _FALLBACK_FULL.format(
        title=title,
        location_rewrite=loc_display or "絕佳地段",
        price=price or "價格驚喜",
        extra=extra,
    )


def generate_ad(
    title: str,
    price: str,
    location: str,
    description: str = "",
    style: str = "房仲",
    model: str = DEFAULT_MODEL,
) -> dict:
    """呼叫 Ollama 產生廣告文案（保留舊有介面）

    Returns: {"success": bool, "text": str, "fallback": bool, "error": str}
    """
    prompt = _build_old_prompt(title, price, location, description, style)

    ollama_ok = _is_ollama_running()
    if not ollama_ok:
        template = random.choice(_FALLBACK_TEMPLATES)
        text = template.format(
            title=title or "超值物件",
            price=price or "價格優惠",
            location=location or "全台",
        )
        return {"success": True, "text": text, "fallback": True, "error": "Ollama 未執行，使用模板文案"}

    try:
        resp = requests.post(
            OLLAMA_API,
            json={"model": model, "prompt": prompt, "stream": False, "temperature": 0.7},
            timeout=60,
        )
        if resp.status_code == 200:
            data = resp.json()
            text = data.get("response", "").strip()
            if text:
                return {"success": True, "text": text, "fallback": False, "error": ""}
    except requests.ConnectionError:
        return {"success": True, "text": f"⚠️ 無法連線 Ollama。\n\n🔥 超值好物件！{title or '詳情請私訊'}", "fallback": True, "error": "ConnectionError"}
    except requests.Timeout:
        return {"success": True, "text": f"⚠️ Ollama 逾時。\n\n{title or '物美價廉！'}\n歡迎預約看屋 📞", "fallback": True, "error": "Timeout"}
    except Exception as e:
        return {"success": True, "text": f"⚠️ AI 錯誤: {str(e)[:30]}", "fallback": True, "error": str(e)}

    template = random.choice(_FALLBACK_TEMPLATES)
    text = template.format(title=title or "超值物件", price=price or "價格優惠", location=location or "全台")
    return {"success": True, "text": text, "fallback": True, "error": "未知錯誤"}


def _build_old_prompt(title: str, price: str, location: str, description: str, style: str = "房仲") -> str:
    return f"""你是一個專業的{style}行銷文案專家。請根據以下商品資訊，產生一篇吸引人的 Facebook 貼文文案。

商品資訊：
- 標題：{title}
- 價格：{price}
- 地點：{location}
- 描述：{description}

寫作要求：
1. 語氣熱情、專業，使用繁體中文（台灣用語）
2. 包含 emoji 增加吸引力
3. 簡潔有力，不超過 150 字
4. 結尾加上行動呼籲（如「歡迎預約」、「立即私訊」）
5. 不要使用過度誇大的用詞

請直接輸出文案，不要加任何前言或說明。"""


def _is_ollama_running() -> bool:
    try:
        resp = requests.get("http://localhost:11434/api/tags", timeout=3)
        return resp.status_code == 200
    except Exception:
        return False


def list_ollama_models() -> list[str]:
    try:
        resp = requests.get("http://localhost:11434/api/tags", timeout=5)
        if resp.status_code == 200:
            models = resp.json().get("models", [])
            return [m["name"] for m in models]
    except Exception:
        pass
    return [DEFAULT_MODEL]


def is_ollama_running() -> bool:
    return _is_ollama_running()
