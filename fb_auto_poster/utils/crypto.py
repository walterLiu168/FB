"""Argon2 加密工具 — 用於加密儲存帳號密碼與 cookies"""
import json
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_ph = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=4,
    hash_len=32,
    salt_len=16,
)


def encrypt(plain_text: str) -> str:
    """使用 Argon2 加密明文字串"""
    return _ph.hash(plain_text)


def verify(hashed: str, plain_text: str) -> bool:
    """驗證明文字串是否匹配 Argon2 hash"""
    try:
        return _ph.verify(hashed, plain_text)
    except VerifyMismatchError:
        return False


def encrypt_dict(data: dict) -> str:
    """將 dict 序列化後加密"""
    return encrypt(json.dumps(data, ensure_ascii=False))


def decrypt_dict(hashed: str) -> dict:
    """驗證並還原 dict（此處使用空字串作為 dummy verify，實際解密是透過 verify）

    Note: Argon2 是單向 hash，真正的「解密」是透過 verify 比對。
    此處保留為介面相容，實際使用時不應嘗試反解密。
    """
    raise NotImplementedError("Argon2 不支援解密，如需還原資料請重新加密")
