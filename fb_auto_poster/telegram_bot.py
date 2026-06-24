"""Telegram Bot — 接收物件資訊 JSON，填入模板，寫入 pending queue

使用方式：
  python telegram_bot.py

環境變數 (或 .env):
  TELEGRAM_BOT_TOKEN=12345:ABCDEF...

接收格式 (文字訊息)：
  {
    "template": "房屋物件",
    "title": "元生國小大3房車",
    "price": "988 萬",
    "location": "桃園市中壢區",
    "size": "50.37坪",
    "rooms": "3房2廳2衛",
    "type": "華廈",
    "intro": "近學區機能好有大露臺",
    "images": ["https://..."],
    "header": "住商內壢 大雄",
    "footer": "歡迎預約看屋"
  }

簡短格式 (用 | 分隔)：
  房屋物件 | 元生國小大3房車 | 988萬 | 桃園市中壢區

"""

import json
import os
import re
import sys
import asyncio
from datetime import datetime

TELEGRAM_AVAILABLE = False
try:
    from telegram import Update
    from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
    TELEGRAM_AVAILABLE = True
except ImportError:
    pass

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from core.pro_templates import queue_post, list_templates, list_pending_posts


def parse_message(text: str) -> dict:
    """解析 Telegram 訊息，回傳 {data, template_name, header, footer, images}"""
    text = text.strip()

    # Try JSON
    if text.startswith("{"):
        try:
            j = json.loads(text)
            return {
                "data": {k: v for k, v in j.items() if k not in ("template", "header", "footer", "images")},
                "template_name": j.get("template", "房屋物件"),
                "header": j.get("header", ""),
                "footer": j.get("footer", ""),
                "images": j.get("images", []),
            }
        except json.JSONDecodeError:
            pass

    # Try pipe format: 模板名稱 | 標題 | 價格 | 地點 | ...
    parts = [p.strip() for p in text.split("|")]
    if len(parts) >= 2:
        templates = [t["name"] for t in list_templates()]
        tmpl_name = parts[0] if parts[0] in templates else "房屋物件"
        data_start = 1 if parts[0] in templates else 0
        data = {}
        fields = ["title", "price", "location", "size", "rooms", "type", "intro"]
        for i, val in enumerate(parts[data_start:]):
            if i < len(fields):
                data[fields[i]] = val
        return {"data": data, "template_name": tmpl_name, "header": "", "footer": "", "images": []}

    # Raw text → intro
    return {"data": {"intro": text}, "template_name": "房屋物件", "header": "", "footer": "", "images": []}


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🏠 FB Poster Bot\n\n"
        "貼上 JSON 格式的物件資訊，我會自動填入模板並排入發文佇列。\n\n"
        "格式範例:\n"
        "```json\n"
        '{"template":"房屋物件","title":"元生國小大3房車","price":"988萬","location":"桃園市中壢區"}\n'
        "```\n\n"
        "或簡短格式:\n"
        "`房屋物件 | 元生國小大3房車 | 988萬 | 桃園市中壢區`\n\n"
        "命令:\n"
        "/templates — 列出可用模板\n"
        "/pending — 檢視待發貼文\n"
        "/post — 立即發送最新待發貼文 (模擬)",
        parse_mode="Markdown",
    )


async def templates_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    names = [t["name"] for t in list_templates()]
    await update.message.reply_text(f"📋 可用模板:\n" + "\n".join(f"  • {n}" for n in names))


async def pending_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    posts = list_pending_posts()
    if not posts:
        await update.message.reply_text("📭 目前沒有待發貼文")
        return
    lines = [f"📋 待發貼文 ({len(posts)} 篇):"]
    for i, p in enumerate(posts[-5:], 1):
        d = p.get("data", {})
        lines.append(f"  {i}. {d.get('title', '無標題')} | {d.get('price', '')} — {p.get('template', '')}")
    await update.message.reply_text("\n".join(lines))


async def post_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """模擬發文 (實際上 pending queue 等待 GUI 處理)"""
    posts = list_pending_posts()
    if not posts:
        await update.message.reply_text("📭 沒有待發貼文")
        return
    p = posts[-1]
    d = p.get("data", {})
    await update.message.reply_text(
        f"✅ 模擬送出: {d.get('title', '無標題')}\n"
        f"模板: {p.get('template', '')}\n"
        f"實際發文請在 FB Poster GUI 中點擊「立即發文」"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or update.message.caption or ""
    if not text.strip():
        await update.message.reply_text("❌ 請傳送文字訊息")
        return

    parsed = parse_message(text)
    data = parsed["data"]
    tmpl = parsed["template_name"]

    if not data:
        await update.message.reply_text("❌ 無法解析訊息內容")
        return

    path = queue_post(data, tmpl)
    preview = data.get("title", "無標題")
    await update.message.reply_text(
        f"✅ 已排入發文佇列\n"
        f"📋 {preview}\n"
        f"🏷️ 模板: {tmpl}\n"
        f"📂 {path}\n\n"
        f"請在 FB Poster GUI 中確認並發送"
    )


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """處理圖片訊息 (存 description)"""
    caption = update.message.caption or ""
    await handle_message(update, context)


def run_bot(token: str):
    if not TELEGRAM_AVAILABLE:
        print("[TelegramBot] python-telegram-bot 未安裝。請執行: pip install python-telegram-bot")
        return

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("templates", templates_cmd))
    app.add_handler(CommandHandler("pending", pending_cmd))
    app.add_handler(CommandHandler("post", post_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    print(f"[TelegramBot] Bot 啟動中...")
    app.run_polling()


if __name__ == "__main__":
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        # Try .env file
        env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    if line.startswith("TELEGRAM_BOT_TOKEN="):
                        token = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not token:
        print("請設定 TELEGRAM_BOT_TOKEN 環境變數或在 .env 檔案中")
        sys.exit(1)
    run_bot(token)
