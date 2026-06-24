"""License 授權引擎 — MAC 綁定 + HMAC 簽名驗證

架構:
  license_generator.py (你)        主程式 app (員工)
  ┌─────────────────┐              ┌─────────────────────┐
  │ 員工 MAC + 到期日 │              │ 讀取 license.lic     │
  │ → HMAC 簽名      │  ──傳送──→   │ → 取本機 MAC         │
  │ → 產出 .lic 檔   │   license   │ → 比對簽名 + 到期日   │
  └─────────────────┘              │ → 通過才能啟動        │
                                   └─────────────────────┘
"""
import hashlib
import hmac
import json
import os
import uuid
from datetime import datetime
from typing import Optional

# ── 密鑰（程式內嵌 + 混淆處理） ──
# 實際密鑰由多段組成，增加逆向難度
_KEY_SEED = "Sn@pP0st!2026#Secure"
_KEY_SALT = "FBAuto@License$V2"
_LICENSE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
_LICENSE_FILE = "license.lic"


def _derive_key() -> bytes:
    """從 seed + salt 推導出 HMAC 密鑰"""
    raw = hashlib.sha256((_KEY_SEED + _KEY_SALT).encode()).hexdigest()
    return raw.encode()[:32]


def get_mac_address() -> str:
    """取得本機 MAC 地址（唯一硬體標識）"""
    mac_int = uuid.getnode()
    mac_hex = hex(mac_int)[2:].zfill(12)
    mac_str = ":".join(mac_hex[i:i+2] for i in range(0, 12, 2))
    return mac_str.upper()


def _sign(mac: str, expiry: str) -> str:
    """用 HMAC-SHA256 簽署 MAC + 到期日"""
    key = _derive_key()
    message = f"{mac}|{expiry}".encode()
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def _verify(mac: str, expiry: str, signature: str) -> bool:
    """驗證簽名是否正確"""
    expected = _sign(mac, expiry)
    return hmac.compare_digest(expected, signature)


def create_license(mac: str, expiry_date: str, output_path: Optional[str] = None) -> str:
    """產生 license 檔案

    Args:
        mac: 目標電腦的 MAC 地址 (e.g. "AA:BB:CC:DD:EE:FF")
        expiry_date: 到期日 (e.g. "2026-12-31")
        output_path: 輸出檔案路徑，預設 data/license.lic

    Returns:
        產生的 license 檔案路徑
    """
    expiry = expiry_date.strip()
    mac = mac.strip().upper()
    signature = _sign(mac, expiry)

    lic_data = {
        "mac": mac,
        "expiry": expiry,
        "signature": signature,
    }

    if output_path is None:
        output_path = os.path.join(_LICENSE_DIR, _LICENSE_FILE)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(lic_data, f, ensure_ascii=False, indent=2)

    return output_path


def verify_license(lic_path: Optional[str] = None) -> dict:
    """驗證 license 是否有效

    Returns:
        {"valid": bool, "reason": str, "mac": str, "expiry": str}
    """
    if lic_path is None:
        lic_path = os.path.join(_LICENSE_DIR, _LICENSE_FILE)

    result = {"valid": False, "reason": "", "mac": "", "expiry": ""}

    # 1. 檢查檔案存在
    if not os.path.exists(lic_path):
        result["reason"] = "找不到授權檔案 (license.lic)"
        return result

    # 2. 讀取並解析
    try:
        with open(lic_path, "r", encoding="utf-8") as f:
            lic_data = json.load(f)
    except (json.JSONDecodeError, Exception):
        result["reason"] = "授權檔案格式錯誤"
        return result

    mac = lic_data.get("mac", "").upper()
    expiry = lic_data.get("expiry", "")
    signature = lic_data.get("signature", "")
    result["mac"] = mac
    result["expiry"] = expiry

    # 3. 驗證簽名
    if not _verify(mac, expiry, signature):
        result["reason"] = "授權檔案已被竄改或無效"
        return result

    # 4. 比對本機 MAC
    current_mac = get_mac_address()
    if mac != current_mac:
        result["reason"] = f"此授權綁定 {mac}，與本機 {current_mac} 不符"
        return result

    # 5. 檢查到期日
    try:
        exp_date = datetime.strptime(expiry, "%Y-%m-%d").date()
        if datetime.now().date() > exp_date:
            result["reason"] = f"授權已於 {expiry} 到期"
            return result
    except ValueError:
        result["reason"] = "到期日格式錯誤"
        return result

    # 全部通過
    result["valid"] = True
    result["reason"] = "授權有效"
    return result


def get_license_path() -> str:
    """取得 license 檔案預設路徑"""
    return os.path.join(_LICENSE_DIR, _LICENSE_FILE)
