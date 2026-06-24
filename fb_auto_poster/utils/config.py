"""設定管理 — 讀寫本地 JSON 設定檔"""
import json
import os
from typing import Any

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")


def _ensure_data_dir():
    os.makedirs(_DATA_DIR, exist_ok=True)


def get_data_path(filename: str) -> str:
    return os.path.join(_DATA_DIR, filename)


def load_json(filename: str, default: Any = None) -> Any:
    """從 data/ 目錄載入 JSON 檔案"""
    _ensure_data_dir()
    path = get_data_path(filename)
    if not os.path.exists(path):
        return default if default is not None else {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return default if default is not None else {}


def save_json(filename: str, data: Any) -> None:
    """儲存 JSON 到 data/ 目錄"""
    _ensure_data_dir()
    path = get_data_path(filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_accounts() -> list:
    """載入帳號列表"""
    return load_json("accounts.json", [])


def save_accounts(accounts: list) -> None:
    """儲存帳號列表"""
    save_json("accounts.json", accounts)


def load_schedules() -> list:
    return load_json("schedules.json", [])


def save_schedules(schedules: list) -> None:
    save_json("schedules.json", schedules)


def load_config() -> dict:
    return load_json("config.json", {})


def save_config(config: dict) -> None:
    save_json("config.json", config)
