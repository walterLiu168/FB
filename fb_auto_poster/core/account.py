"""帳號管理 — 多帳號 CRUD + 加密儲存"""
import json
import os
from typing import Optional

from utils.config import load_accounts, save_accounts, get_data_path
from utils.crypto import encrypt


class Account:
    def __init__(
        self,
        account_id: str,
        email: str,
        password: str = "",
        cookie_path: str = "",
        nickname: str = "",
        is_active: bool = True,
    ):
        self.account_id = account_id
        self.email = email
        self.password = password
        self.cookie_path = cookie_path
        self.nickname = nickname or email
        self.is_active = is_active

    def to_dict(self) -> dict:
        return {
            "account_id": self.account_id,
            "email": self.email,
            "password_hash": encrypt(self.password) if self.password else "",
            "cookie_path": self.cookie_path,
            "nickname": self.nickname,
            "is_active": self.is_active,
        }

    @staticmethod
    def from_dict(data: dict) -> "Account":
        return Account(
            account_id=data["account_id"],
            email=data["email"],
            cookie_path=data.get("cookie_path", ""),
            nickname=data.get("nickname", data["email"]),
            is_active=data.get("is_active", True),
        )


class AccountManager:
    """帳號管理器"""

    def __init__(self):
        self._accounts: dict[str, Account] = {}
        self.load()

    def add(self, account: Account) -> None:
        self._accounts[account.account_id] = account
        self.save()

    def remove(self, account_id: str) -> bool:
        if account_id in self._accounts:
            del self._accounts[account_id]
            self.save()
            return True
        return False

    def get(self, account_id: str) -> Optional[Account]:
        return self._accounts.get(account_id)

    def list_all(self) -> list[Account]:
        return list(self._accounts.values())

    def list_active(self) -> list[Account]:
        return [a for a in self._accounts.values() if a.is_active]

    def set_active(self, account_id: str, active: bool) -> None:
        if account_id in self._accounts:
            self._accounts[account_id].is_active = active
            self.save()

    def load(self) -> None:
        raw = load_accounts()
        seen = {}
        for item in raw:
            acc = Account.from_dict(item)
            seen[acc.account_id] = acc
        self._accounts = seen

    def save(self) -> None:
        raw = [a.to_dict() for a in self._accounts.values()]
        save_accounts(raw)

    def import_cookie(self, account_id: str, cookie_json_str: str) -> bool:
        """匯入 FB Cookie JSON 字串，存到本地檔案"""
        try:
            data = json.loads(cookie_json_str)
            if not isinstance(data, list):
                return False
            cookie_file = f"cookies_{account_id}.json"
            cookie_path = get_data_path(cookie_file)
            os.makedirs(os.path.dirname(cookie_path), exist_ok=True)
            with open(cookie_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            if account_id in self._accounts:
                self._accounts[account_id].cookie_path = cookie_path
                self.save()
            return True
        except (json.JSONDecodeError, Exception):
            return False

    def get_cookie_json(self, account_id: str) -> str:
        """讀取已儲存的 Cookie JSON 字串"""
        acc = self._accounts.get(account_id)
        if not acc or not acc.cookie_path:
            return ""
        try:
            with open(acc.cookie_path, "r", encoding="utf-8") as f:
                return f.read()
        except (FileNotFoundError, Exception):
            return ""
