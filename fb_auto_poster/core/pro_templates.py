"""Pro 模板引擎 — 管理房屋/土地/廠房模板，填值產生文案，儲存/載入

獨立模組：可從 Telegram bot 直接 import，不依賴 GUI。
"""

import json
import os
import re
from datetime import datetime
from typing import Optional, Any

# ── 預設 3 種模板 ──
_DEFAULT_TEMPLATES: list[dict] = [
    {
        "name": "房屋物件",
        "type": "house",
        "template": (
            "🏠 {title}\n"
            "📍 {location}\n"
            "💰 價格: {price}\n"
            "\n"
            "📐 坪數: {size} | 🛏️ 格局: {rooms} | 🏗️ 類型: {type}\n"
            "🏢 {floor} | 📅 {age} | 🚗 {parking} | 🧭 {orientation}\n"
            "\n"
            "✨ {intro}\n"
        ),
        "fields": [
            {"key": "title", "label": "標題", "required": True},
            {"key": "price", "label": "價格", "required": True},
            {"key": "location", "label": "地點"},
            {"key": "size", "label": "坪數"},
            {"key": "rooms", "label": "格局"},
            {"key": "type", "label": "類型"},
            {"key": "floor", "label": "樓層"},
            {"key": "age", "label": "屋齡"},
            {"key": "parking", "label": "車位"},
            {"key": "orientation", "label": "朝向"},
            {"key": "intro", "label": "介紹", "multiline": True},
        ],
    },
    {
        "name": "土地",
        "type": "land",
        "template": (
            "🌍 {title}\n"
            "📍 {location}\n"
            "💰 價格: {price}\n"
            "\n"
            "📐 土地坪數: {size} | 🏗️ 使用分區: {type}\n"
            "🛣️ 路寬: {road_width}\n"
            "\n"
            "✨ {intro}\n"
        ),
        "fields": [
            {"key": "title", "label": "標題", "required": True},
            {"key": "price", "label": "價格", "required": True},
            {"key": "location", "label": "地點"},
            {"key": "size", "label": "土地坪數"},
            {"key": "type", "label": "使用分區"},
            {"key": "road_width", "label": "路寬"},
            {"key": "intro", "label": "介紹", "multiline": True},
        ],
    },
    {
        "name": "廠房",
        "type": "factory",
        "template": (
            "🏭 {title}\n"
            "📍 {location}\n"
            "💰 價格: {price}\n"
            "\n"
            "📐 建物坪數: {size} | 🌍 土地坪數: {land_size}\n"
            "🏗️ {type} | 🏢 {floor} | 📅 {age}\n"
            "\n"
            "✨ {intro}\n"
        ),
        "fields": [
            {"key": "title", "label": "標題", "required": True},
            {"key": "price", "label": "價格", "required": True},
            {"key": "location", "label": "地點"},
            {"key": "size", "label": "建物坪數"},
            {"key": "land_size", "label": "土地坪數"},
            {"key": "type", "label": "類型"},
            {"key": "floor", "label": "樓層"},
            {"key": "age", "label": "屋齡"},
            {"key": "intro", "label": "介紹", "multiline": True},
        ],
    },
]


def _data_dir() -> str:
    d = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
    os.makedirs(d, exist_ok=True)
    return d


def _templates_path() -> str:
    return os.path.join(_data_dir(), "pro_templates.json")


def _group_sets_path() -> str:
    return os.path.join(_data_dir(), "group_post_sets.json")


def _pending_dir() -> str:
    d = os.path.join(_data_dir(), "pending_posts")
    os.makedirs(d, exist_ok=True)
    return d


# ═════════════════════════════════════════════════════════════
#  模板 CRUD
# ═════════════════════════════════════════════════════════════

def list_templates() -> list[dict]:
    """列出所有模板（含預設）"""
    if not os.path.exists(_templates_path()):
        _init_default_templates()
    try:
        with open(_templates_path(), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return list(_DEFAULT_TEMPLATES)


def get_template(name: str) -> Optional[dict]:
    """依名稱取得單一模板"""
    for t in list_templates():
        if t["name"] == name:
            return t
    return None


def save_template(name: str, ttype: str, template_text: str, fields: list[dict]):
    """新增或覆蓋一個模板"""
    templates = list_templates()
    for t in templates:
        if t["name"] == name:
            t["type"] = ttype
            t["template"] = template_text
            t["fields"] = fields
            break
    else:
        templates.append({
            "name": name, "type": ttype,
            "template": template_text, "fields": fields,
        })
    _write_templates(templates)


def delete_template(name: str) -> bool:
    templates = list_templates()
    original_len = len(templates)
    templates = [t for t in templates if t["name"] != name]
    if len(templates) < original_len:
        _write_templates(templates)
        return True
    return False


def _init_default_templates():
    _write_templates(list(_DEFAULT_TEMPLATES))


def _write_templates(templates: list[dict]):
    with open(_templates_path(), "w", encoding="utf-8") as f:
        json.dump(templates, f, ensure_ascii=False, indent=2)


# ═════════════════════════════════════════════════════════════
#  填值產生文案
# ═════════════════════════════════════════════════════════════

def fill_template(data: dict, template_name: str = "房屋物件") -> str:
    """把 data dict 填入模板，產出最終文案。

    data 格式: {"title": "...", "price": "...", ...}
    template_name: "房屋物件" / "土地" / "廠房" 等

    模板中的 {field_name} 會被 data[field_name] 替換。
    空的非必填欄位 → 整行省略。
    """
    tmpl = get_template(template_name)
    if not tmpl:
        # fallback: 用傳入的 raw text
        return data.get("text", "") or data.get("raw", "") or ""

    raw = tmpl["template"]
    fields = {f["key"]: f for f in tmpl["fields"]}

    # Step 1: 處理空欄位 → 移除該行
    for key, fdef in fields.items():
        val = str(data.get(key, "")).strip()
        if not val and not fdef.get("required"):
            # 移除含有 {key} 的那一整行
            raw = _remove_line_with_key(raw, key)

    # Step 2: 替換所有 {key}
    result = raw
    for key in fields:
        val = str(data.get(key, "")).strip()
        result = result.replace(f"{{{key}}}", val)

    # Step 3: 清理空白行
    result = re.sub(r"\n{3,}", "\n\n", result)
    result = re.sub(r"^\n+", "", result)
    result = re.sub(r"\n+$", "", result)

    return result


def _remove_line_with_key(text: str, key: str) -> str:
    """移除含有 {key} 的整行"""
    lines = text.split("\n")
    return "\n".join(l for l in lines if f"{{{key}}}" not in l)


def generate_post(
    data: dict,
    template_name: str = "房屋物件",
    header: str = "",
    footer: str = "",
    images: list[str] = None,
) -> dict:
    """一站式產生完整發文內容

    Returns:
        {"text": "完整文案", "images": [...]}
    """
    body = fill_template(data, template_name)
    parts = []
    if header:
        parts.append(header)
    parts.append(body)
    if footer:
        parts.append(footer)

    return {
        "text": "\n\n".join(parts),
        "images": images or [],
    }


# ═════════════════════════════════════════════════════════════
#  社團組合 (Group Post Sets)
# ═════════════════════════════════════════════════════════════

def list_group_sets() -> dict[str, list[str]]:
    """回傳 {"Set 1": ["社團A", "社團B"], ...}"""
    if not os.path.exists(_group_sets_path()):
        return {"Set 1": [], "Set 2": [], "Set 3": []}
    try:
        with open(_group_sets_path(), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"Set 1": [], "Set 2": [], "Set 3": []}


def save_group_set(name: str, groups: list[str]):
    """儲存一個社團組合"""
    sets = list_group_sets()
    sets[name] = groups
    with open(_group_sets_path(), "w", encoding="utf-8") as f:
        json.dump(sets, f, ensure_ascii=False, indent=2)


def get_group_set(name: str) -> list[str]:
    return list_group_sets().get(name, [])


# ═════════════════════════════════════════════════════════════
#  Telegram 待發佇列
# ═════════════════════════════════════════════════════════════

def queue_post(data: dict, template_name: str = "房屋物件"):
    """從 Telegram 接收貼文 → 寫入 pending queue"""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(_pending_dir(), f"{ts}.json")
    payload = {
        "data": data,
        "template": template_name,
        "created_at": datetime.now().isoformat(),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return path


def list_pending_posts() -> list[dict]:
    """列出所有待發貼文"""
    posts = []
    d = _pending_dir()
    if not os.path.exists(d):
        return posts
    for fname in sorted(os.listdir(d)):
        if fname.endswith(".json"):
            try:
                with open(os.path.join(d, fname), "r", encoding="utf-8") as f:
                    posts.append(json.load(f))
            except Exception:
                pass
    return posts


def pop_pending_post(path: str):
    """發文後刪除 pending 檔案"""
    try:
        os.remove(path)
    except OSError:
        pass


def get_pending_paths() -> list[str]:
    d = _pending_dir()
    if not os.path.exists(d):
        return []
    return sorted(os.path.join(d, f) for f in os.listdir(d) if f.endswith(".json"))
