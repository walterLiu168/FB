"""操作日誌系統 — 記錄所有發文/刪文/養號操作"""
import json
import os
from datetime import datetime
from typing import Optional

from utils.config import get_data_path

_LOG_FILE = "operations.log"


def _log_path() -> str:
    return get_data_path(_LOG_FILE)


def log(
    action_type: str,
    account: str,
    action: str,
    status: str,
    detail: str = "",
    schedule_delete_at: Optional[str] = None,
):
    """寫入一筆操作日誌

    Args:
        action_type: 操作類型 (POST, DELETE, NURTURE, etc.)
        account: 帳號 Email
        action: 動作描述
        status: 結果 (✅ 成功, ❌ 失敗, ⏳ 進行中)
        detail: 詳細資訊
        schedule_delete_at: 預計刪除時間 (ISO 格式)
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    parts = [f"[{timestamp}]", f"{action_type:>8}", f"| {account}", f"| {action}", f"| {status}"]

    if detail:
        parts.append(f"| {detail}")
    if schedule_delete_at:
        parts.append(f"| 🗑️ {schedule_delete_at}")

    line = " ".join(parts)

    path = _log_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def read_logs(max_lines: int = 100) -> list[str]:
    """讀取最近的日誌行數"""
    path = _log_path()
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        return [l.strip() for l in lines[-max_lines:]]
    except Exception:
        return []


def get_post_logs_for_clean() -> list[dict]:
    """掃描日誌中已排程刪除的貼文，回傳 list[dict]"""
    path = _log_path()
    if not os.path.exists(path):
        return []
    posts = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if "POST" in line and "🗑️" in line:
                    try:
                        # 解析格式: [2026-06-08 15:30:00]      POST | email | 動作 | 成功 | detail | 🗑️ 2026-06-09 15:30
                        parts = line.strip().split("|")
                        if len(parts) >= 6:
                            timestamp_str = parts[0].strip().strip("[]")
                            account = parts[1].strip()
                            detail = parts[4].strip() if len(parts) > 4 else ""
                            delete_str = parts[5].strip().replace("🗑️ ", "")
                            posts.append({
                                "time": timestamp_str,
                                "account": account,
                                "detail": detail,
                                "delete_at": delete_str,
                            })
                    except Exception:
                        continue
    except Exception:
        pass
    return posts
