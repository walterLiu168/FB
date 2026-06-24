"""GPT / OpenAI 整合模組 — 支援 mock 模式與雲端 server 模式

使用方式：
  from core.gpt_client import gpt_generate
  
  # Mock 模式（離線）
  result = gpt_generate("幫我寫一段房仲文案")
  
  # 真實模式（需設定 OPENAI_API_KEY 或 GPT_SERVER_URL）
  設定 .env 中的 OPENAI_API_KEY 或 GPT_SERVER_URL

Mock 模式會根據 prompt 內容生成合理的中文模擬回應。
"""
import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from utils.universal_config import get, is_mock, OPENAI_API_KEY, GPT_SERVER_URL, OPENAI_MOCK
except ImportError:
    OPENAI_MOCK = True
    OPENAI_API_KEY = "MOCK"
    GPT_SERVER_URL = "https://ezup.work/api/gpt"


def gpt_generate(
    prompt: str,
    system_prompt: str = "你是專業的台灣房仲文案撰寫助手。",
    model: str = "gpt-4.1-mini",
    temperature: float = 0.8,
    max_tokens: int = 800,
    use_mock: Optional[bool] = None,
) -> dict:
    """呼叫 GPT 產生文案
    
    Args:
        prompt: 使用者提示詞
        system_prompt: 系統提示詞
        model: 模型名稱
        temperature: 創造力 (0-1)
        max_tokens: 最大 token 數
        use_mock: 強制使用 mock (None=自動判斷)
    
    Returns:
        {"success": bool, "text": str, "error": str|None}
    """
    mock_mode = use_mock if use_mock is not None else OPENAI_MOCK
    
    if mock_mode:
        return _mock_generate(prompt, system_prompt)
    
    # Try cloud server first
    if GPT_SERVER_URL and "localhost" not in GPT_SERVER_URL:
        result = _call_gpt_server(prompt, system_prompt, temperature, max_tokens)
        if result["success"]:
            return result
    
    # Try direct OpenAI
    if OPENAI_API_KEY:
        result = _call_openai_direct(prompt, system_prompt, model, temperature, max_tokens)
        if result["success"]:
            return result
    
    # Fallback to mock
    logger.warning("All GPT backends failed, falling back to mock")
    return _mock_generate(prompt, system_prompt)


def _call_gpt_server(prompt: str, system_prompt: str, temperature: float, max_tokens: int) -> dict:
    """透過雲端 server 呼叫 GPT"""
    try:
        import requests
        resp = requests.post(
            GPT_SERVER_URL,
            json={
                "prompt": prompt,
                "system_prompt": system_prompt,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            timeout=30,
        )
        if resp.status_code == 200:
            data = resp.json()
            return {"success": True, "text": data.get("text", data.get("response", "")), "error": None}
        return {"success": False, "text": "", "error": f"Server returned {resp.status_code}"}
    except Exception as e:
        return {"success": False, "text": "", "error": str(e)}


def _call_openai_direct(prompt: str, system_prompt: str, model: str, temperature: float, max_tokens: int) -> dict:
    """直接呼叫 OpenAI API"""
    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return {"success": True, "text": response.choices[0].message.content.strip(), "error": None}
    except ImportError:
        return {"success": False, "text": "", "error": "openai package not installed"}
    except Exception as e:
        return {"success": False, "text": "", "error": str(e)}


def _mock_generate(prompt: str, system_prompt: str) -> dict:
    """Mock GPT — 根據 prompt 產生模擬文案"""
    prompt_lower = prompt.lower()
    
    # 房仲物件介紹
    if any(w in prompt for w in ("物件", "房屋", "房仲", "格局", "坪數", "標題", "價格")):
        # 從 prompt 提取關鍵字
        import re
        title = ""
        price = ""
        location = ""
        rooms = ""
        size = ""
        ptype = ""
        
        m = re.search(r'title[：:](.+)', prompt)
        if m: title = m.group(1).strip()
        m = re.search(r'price[：:](.+)', prompt)
        if m: price = m.group(1).strip()
        m = re.search(r'location[：:](.+)', prompt)
        if m: location = m.group(1).strip()
        m = re.search(r'rooms[：:](.+)', prompt)
        if m: rooms = m.group(1).strip()
        m = re.search(r'size[：:](.+)', prompt)
        if m: size = m.group(1).strip()
        m = re.search(r'type[：:](.+)', prompt)
        if m: ptype = m.group(1).strip()
        
        parts = []
        if title:
            parts.append(f"{title}，")
        if location:
            loc_short = location.replace("桃園市", "").replace("台中市", "").replace("台北市", "")
            if loc_short:
                parts.append(f"位於{loc_short}精華地段，")
        if size and rooms:
            parts.append(f"{size}大空間{rooms}，")
        if ptype:
            parts.append(f"{ptype}物件稀有釋出，")
        parts.append("生活機能完善，鄰近商圈與學區，交通便利，是自住或投資的最佳選擇。歡迎預約賞屋！")
        return {"success": True, "text": "".join(parts), "error": None, "mock": True}
    
    # 通用文案
    if "介紹" in prompt or "文案" in prompt or "廣告" in prompt:
        return {
            "success": True,
            "text": "精選物件，絕佳地段，完善的生活機能，讓您享受便利又舒適的居住環境。優質建材，格局方正，通風採光極佳。歡迎來電預約參觀！",
            "error": None,
            "mock": True,
        }
    
    # 預設
    return {
        "success": True,
        "text": "這是一個優質的物件，地處精華地段，交通便利，生活機能完善。歡迎洽詢了解更多資訊！",
        "error": None,
        "mock": True,
    }


# ── 便捷函數 ──
def generate_property_intro(fields: dict, use_mock: Optional[bool] = None) -> str:
    """根據物件欄位生成介紹文案"""
    prompt = "請根據以下物件資訊，寫一段吸引人的介紹（2-3句，繁體中文）：\n"
    for k, v in fields.items():
        if v and k != "intro":
            prompt += f"- {k}: {v}\n"
    
    result = gpt_generate(
        prompt,
        system_prompt="你是台灣房仲文案專家。輸出簡潔有力的中文介紹，強調物件亮點。",
        temperature=0.8,
        max_tokens=200,
        use_mock=use_mock,
    )
    return result.get("text", "")


def generate_social_post(fields: dict, header: str = "", footer: str = "", use_mock: Optional[bool] = None) -> str:
    """生成完整社群貼文文案"""
    intro = generate_property_intro(fields, use_mock)
    
    lines = []
    if fields.get("title"):
        lines.append(f"🏠 {fields['title']}")
    if fields.get("price"):
        lines.append(f"💰 {fields['price']}")
    if fields.get("location"):
        lines.append(f"📍 {fields['location']}")
    lines.append("")
    lines.append(intro)
    
    body = "\n".join(lines)
    parts = []
    if header:
        parts.append(header)
    parts.append(body)
    if footer:
        parts.append(footer)
    
    return "\n\n".join(parts)
