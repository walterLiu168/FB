"""可逆密鑰加密 — 用於儲存需要讀回的憑證 (如 OAuth token)

注意：utils/crypto.py 的 Argon2 是「單向雜湊」，只能驗證、無法還原，
適合密碼，不適合需要讀回再使用的 token。本模組用 Fernet (AES-128-CBC + HMAC)
提供可逆加密，金鑰存於 data/.secret_key（首次使用時自動產生）。
"""
import base64
import os

from utils.config import get_data_path

_KEY_FILE = ".secret_key"


def _key_path() -> str:
    return get_data_path(_KEY_FILE)


def _load_or_create_key() -> bytes:
    """讀取本機金鑰，不存在則產生一把新的"""
    from cryptography.fernet import Fernet

    path = _key_path()
    if os.path.exists(path):
        with open(path, "rb") as f:
            return f.read().strip()

    key = Fernet.generate_key()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(key)
    # 盡量限制權限（Windows 上 chmod 影響有限，但無害）
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return key


def encrypt_secret(plain_text: str) -> str:
    """加密字串，回傳可儲存的 base64 字串"""
    from cryptography.fernet import Fernet

    f = Fernet(_load_or_create_key())
    token = f.encrypt(plain_text.encode("utf-8"))
    return token.decode("ascii")


def decrypt_secret(cipher_text: str) -> str:
    """還原由 encrypt_secret 加密的字串"""
    from cryptography.fernet import Fernet

    f = Fernet(_load_or_create_key())
    plain = f.decrypt(cipher_text.encode("ascii"))
    return plain.decode("utf-8")


def mask(secret: str, visible: int = 4) -> str:
    """產生遮罩字串供 UI 顯示，不洩漏完整憑證"""
    if not secret:
        return ""
    if len(secret) <= visible:
        return "*" * len(secret)
    return secret[:visible] + "*" * (len(secret) - visible)
