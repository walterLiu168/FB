"""Header/Footer 範本管理"""
from typing import Optional

from utils.config import load_json, save_json


class TemplateManager:
    """管理每個帳號的 Header/Footer 範本"""

    def __init__(self):
        self._data = load_json("templates.json", {})

    def _save(self):
        save_json("templates.json", self._data)

    def get_header(self, account_id: str) -> str:
        """取得帳號的 Header"""
        acc = self._data.get(account_id, {})
        return acc.get("header", "")

    def set_header(self, account_id: str, text: str):
        """設定帳號的 Header"""
        self._data.setdefault(account_id, {})["header"] = text
        self._save()

    def get_footer(self, account_id: str) -> str:
        """取得帳號的 Footer"""
        acc = self._data.get(account_id, {})
        return acc.get("footer", "")

    def set_footer(self, account_id: str, text: str):
        """設定帳號的 Footer"""
        self._data.setdefault(account_id, {})["footer"] = text
        self._save()

    def get_default_header(self) -> str:
        """取得全域預設 Header"""
        return self._data.get("__global__", {}).get("header", "")

    def set_default_header(self, text: str):
        self._data.setdefault("__global__", {})["header"] = text
        self._save()

    def get_default_footer(self) -> str:
        """取得全域預設 Footer"""
        return self._data.get("__global__", {}).get("footer", "")

    def set_default_footer(self, text: str):
        self._data.setdefault("__global__", {})["footer"] = text
        self._save()

    def get_all_headers_footers(self) -> dict:
        """取得所有帳號的範本設定"""
        return self._data

    def compose_post(
        self,
        account_id: str,
        body: str,
        override_header: str = "",
        override_footer: str = "",
    ) -> str:
        """組合 Header + 內文 + Footer 成完整貼文

        優先級: override > account-specific > global default
        """
        header = override_header or self.get_header(account_id) or self.get_default_header()
        footer = override_footer or self.get_footer(account_id) or self.get_default_footer()

        parts = []
        if header:
            parts.append(header)
        parts.append(body)
        if footer:
            parts.append(footer)

        return "\n\n".join(parts)
