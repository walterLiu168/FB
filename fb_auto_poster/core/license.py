"""License 授權引擎 — MAC + Registry 雙綁定 + 月租續期 + Grace Window

防護層級:
  第 1 層: MAC 地址綁定（硬體唯一標識）
  第 2 層: Registry InstallID 綁定（防止複製整個 data/ 資料夾）
  第 3 層: HMAC-SHA256 簽名防竄改
  第 4 層: 到期日檢查 + 3 天寬限期
  第 5 層: Renewal Key 防止重複使用舊授權

架構:
  ┌─────────────────────────┐        ┌─────────────────────────┐
  │  license_generator.py    │        │  主程式 main.py           │
  │  (管理員端)              │        │  (員工端)                │
  │                         │        │                         │
  │  1. 取得員工 MAC +       │ .lic   │  1. 檢查 registry       │
  │     InstallID            │ ────→  │     InstallID 匹配       │
  │  2. 填入 issued          │        │  2. 檢查 renewal_key     │
  │     (今天)               │        │     未被重複使用          │
  │  3. expiry = issued+30d  │        │  3. HMAC 簽名驗證        │
  │  4. 產生 renewal_key     │        │  4. MAC 匹配             │
  │  5. HMAC 簽名            │        │  5. 到期日檢查            │
  └─────────────────────────┘        └─────────────────────────┘
"""
import hashlib
import hmac
import json
import os
import uuid
import secrets
from datetime import datetime, date, timedelta
from typing import Optional, Tuple

# ── 密鑰（執行時期分段解混淆，防止靜態分析提取） ──
# 這不是明碼！每段經過 XOR 混淆，執行時才重組。
# 即使被反編譯，看到的也是無意義的 bytes，提高逆向難度。
import base64 as _b64
import struct as _struct

_LICENSE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
_LICENSE_FILE = "license.lic"

# 密鑰片段（XOR 編碼儲存，非明碼 — 逆推需要動態分析）
_SEG1 = b'\x68\x08\x02\x74\x54\x65\x75\x4c'
_SEG2 = b'\x56\x63\x7d\x44\x58\x73\x15\x68'
_SEG3 = b'\x0a\x4f\x4e\x2b\x74\x6e\x39\x57'
_SEG4 = b'\x54\x72\x45\x6f\x23\x1d\x0a\x5e'
_MASK = b'\x5a\x69\x33\x11\x36\x50\x17\x74\x65\x05\x4f\x71\x6b\x15\x27\x0c\x3e\x7a\x2d\x19\x44\x58\x0b\x6f\x31\x4a\x7c\x5d\x12\x28\x3f\x66'

# ── Registry 路徑 ──
_REG_KEY = r"Software\FBPoster"
_REG_INSTALL_ID = "InstallId"
_REG_LAST_RENEWAL_KEY = "LastRenewalKey"
_REG_ACTIVATED_MAC = "ActivatedMac"

# ── 授權有效天數與寬限期 ──
_LICENSE_DAYS = 30          # 每期有效天數
_GRACE_DAYS = 3             # 寬限期（到期後仍可使用天數）


# ═══════════════════════════════════════════════════════════
#  Registry 操作（Windows）
# ═══════════════════════════════════════════════════════════

def _open_registry_key(mode: str = "read"):
    """開啟 registry key，相容 macOS/Linux"""
    import sys
    if sys.platform != "win32":
        return None
    import winreg
    access = winreg.KEY_READ if mode == "read" else winreg.KEY_WRITE
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_KEY, 0, access)
        return key
    except FileNotFoundError:
        if mode == "write":
            key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, _REG_KEY)
            return key
        return None
    except OSError:
        return None


def _write_registry(name: str, value: str) -> bool:
    """寫入字串值到 registry"""
    import sys
    if sys.platform != "win32":
        return False
    import winreg
    try:
        key = _open_registry_key("write")
        if key is None:
            return False
        winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
        winreg.CloseKey(key)
        return True
    except Exception:
        return False


def _read_registry(name: str) -> Optional[str]:
    """從 registry 讀取字串值"""
    import sys
    if sys.platform != "win32":
        return None
    import winreg
    try:
        key = _open_registry_key("read")
        if key is None:
            return None
        value, _ = winreg.QueryValueEx(key, name)
        winreg.CloseKey(key)
        return str(value)
    except FileNotFoundError:
        return None
    except OSError:
        return None


def _delete_registry_key() -> bool:
    """刪除整個 FBPoster registry key（重設用）"""
    import sys
    if sys.platform != "win32":
        return False
    import winreg
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, _REG_KEY)
        return True
    except FileNotFoundError:
        return True
    except OSError:
        return False


# ═══════════════════════════════════════════════════════════
#  InstallID 管理
# ═══════════════════════════════════════════════════════════

def get_or_create_install_id() -> str:
    """取得或產生本機 InstallID（存於 Windows Registry）
    
    首次執行時產生唯一 UUID 並寫入 registry，
    之後每次讀取相同值，不會改變。
    """
    existing = _read_registry(_REG_INSTALL_ID)
    if existing and len(existing) >= 32:
        return existing

    new_id = str(uuid.uuid4()).replace("-", "") + str(uuid.uuid4())[:8]
    _write_registry(_REG_INSTALL_ID, new_id)
    return new_id


def get_stored_install_id() -> Optional[str]:
    """讀取已儲存的 InstallID（不產生新的）"""
    return _read_registry(_REG_INSTALL_ID)


def get_last_renewal_key() -> Optional[str]:
    """讀取上次使用的 renewal_key"""
    return _read_registry(_REG_LAST_RENEWAL_KEY)


# ═══════════════════════════════════════════════════════════
#  MAC 與授權簽名
# ═══════════════════════════════════════════════════════════

def get_mac_address() -> str:
    """取得本機 MAC 地址（唯一硬體標識）"""
    mac_int = uuid.getnode()
    mac_hex = hex(mac_int)[2:].zfill(12)
    mac_str = ":".join(mac_hex[i:i+2] for i in range(0, 12, 2))
    return mac_str.upper()


def _derive_key() -> bytes:
    """從混淆片段 + XOR mask 動態重組 HMAC 密鑰
    
    設計意圖：原始密鑰不以明碼字串儲存，而是拆成 4 段、每段
    與不同 mask byte 做 XOR。即使反編譯也無法直接取得，
    必須進行動態分析才能推導。
    """
    # 重組 XOR 後的 total
    xored = _SEG1 + _SEG2 + _SEG3 + _SEG4
    # 反 XOR 得到原始密鑰
    key_bytes = bytes([xored[i] ^ _MASK[i % len(_MASK)] for i in range(len(xored))])
    return key_bytes[:32]


def _sign(mac: str, install_id: str, expiry: str, issued: str, renewal_key: str) -> str:
    """用 HMAC-SHA256 簽署授權內容"""
    key = _derive_key()
    message = f"{mac}|{install_id}|{expiry}|{issued}|{renewal_key}".encode()
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def _verify_signature(mac: str, install_id: str, expiry: str, issued: str,
                      renewal_key: str, signature: str) -> bool:
    """驗證簽名"""
    expected = _sign(mac, install_id, expiry, issued, renewal_key)
    return hmac.compare_digest(expected, signature)


# ═══════════════════════════════════════════════════════════
#  License 建立與驗證
# ═══════════════════════════════════════════════════════════

def create_license(
    mac: str,
    install_id: str,
    issued_date: Optional[str] = None,
    output_path: Optional[str] = None,
) -> str:
    """產生月租授權檔案

    Args:
        mac: 目標電腦的 MAC 地址 (e.g. "AA:BB:CC:DD:EE:FF")
        install_id: 目標電腦的 Registry InstallID
        issued_date: 核發日期，預設今天 (YYYY-MM-DD 格式)
        output_path: 輸出檔案路徑，預設 data/license.lic

    Returns:
        產生的 license 檔案路徑
    """
    if issued_date is None:
        issued_date = datetime.now().strftime("%Y-%m-%d")

    issued_dt = datetime.strptime(issued_date, "%Y-%m-%d")
    expiry_dt = issued_dt + timedelta(days=_LICENSE_DAYS)
    expiry = expiry_dt.strftime("%Y-%m-%d")

    mac = mac.strip().upper()
    install_id = install_id.strip()
    renewal_key = secrets.token_hex(16)

    signature = _sign(mac, install_id, expiry, issued_date, renewal_key)

    lic_data = {
        "mac": mac,
        "install_id": install_id,
        "issued": issued_date,
        "expiry": expiry,
        "renewal_key": renewal_key,
        "signature": signature,
    }

    if output_path is None:
        output_path = os.path.join(_LICENSE_DIR, _LICENSE_FILE)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(lic_data, f, ensure_ascii=False, indent=2)

    return output_path


def verify_license(lic_path: Optional[str] = None) -> dict:
    """完整授權驗證（MAC + InstallID + 簽名 + 到期日 + Renewal Key）

    Returns:
        {
            "valid": bool,
            "reason": str,
            "mac": str,
            "install_id": str,
            "issued": str,
            "expiry": str,
            "days_remaining": int,
            "grace": bool,
        }
    """
    import sys as _sys

    if lic_path is None:
        lic_path = os.path.join(_LICENSE_DIR, _LICENSE_FILE)

    result = {
        "valid": False,
        "reason": "",
        "mac": "",
        "install_id": "",
        "issued": "",
        "expiry": "",
        "days_remaining": 0,
        "grace": False,
    }

    # ── 第 0 層: 檢查 registry 是否被重置（未初始化） ──
    stored_install_id = get_stored_install_id()
    if stored_install_id is None and _sys.platform == "win32":
        result["reason"] = "系統尚未初始化授權，請先執行安裝程序"
        return result

    # ── 第 1 層: 檢查檔案存在 ──
    if not os.path.exists(lic_path):
        result["reason"] = "找不到授權檔案 (license.lic)"
        return result

    # ── 第 2 層: 讀取並解析 ──
    try:
        with open(lic_path, "r", encoding="utf-8") as f:
            lic_data = json.load(f)
    except (json.JSONDecodeError, Exception):
        result["reason"] = "授權檔案格式錯誤"
        return result

    mac = lic_data.get("mac", "").upper()
    install_id = lic_data.get("install_id", "")
    issued = lic_data.get("issued", "")
    expiry = lic_data.get("expiry", "")
    renewal_key = lic_data.get("renewal_key", "")
    signature = lic_data.get("signature", "")

    result["mac"] = mac
    result["install_id"] = install_id
    result["issued"] = issued
    result["expiry"] = expiry

    # 檢查必要欄位
    if not all([mac, install_id, issued, expiry, renewal_key, signature]):
        result["reason"] = "授權檔案欄位不完整"
        return result

    # ── 第 3 層: 驗證 HMAC 簽名 ──
    if not _verify_signature(mac, install_id, expiry, issued, renewal_key, signature):
        result["reason"] = "授權檔案已被竄改或無效"
        return result

    # ── 第 4 層: 比對本機 MAC ──
    current_mac = get_mac_address()
    if mac != current_mac:
        result["reason"] = f"此授權綁定 MAC {mac}，與本機 {current_mac} 不符"
        return result

    # ── 第 5 層: 比對 Registry InstallID ──
    actual_install_id = get_stored_install_id()
    if actual_install_id and install_id != actual_install_id:
        result["reason"] = (
            f"此授權綁定 InstallID {install_id[:8]}...，"
            f"與本機 {actual_install_id[:8]}... 不符\n"
            f"請勿複製授權檔案到其他電腦"
        )
        return result

    # ── 第 6 層: 檢查 Renewal Key 是否被重複使用 ──
    last_renewal = get_last_renewal_key()
    if last_renewal and last_renewal == renewal_key:
        result["reason"] = "此授權金鑰已被使用過，請取得新的月租授權"
        return result

    # ── 第 7 層: 檢查到期日 ──
    try:
        issued_dt = datetime.strptime(issued, "%Y-%m-%d").date()
        exp_dt = datetime.strptime(expiry, "%Y-%m-%d").date()
        today = datetime.now().date()
        grace_end = exp_dt + timedelta(days=_GRACE_DAYS)
    except ValueError:
        result["reason"] = "授權日期格式錯誤"
        return result

    # 計算剩餘天數（相對於正常到期日）
    days_remaining = (exp_dt - today).days
    result["days_remaining"] = max(days_remaining, 0)

    # 完全過期（超過寬限期）
    if today > grace_end:
        result["reason"] = (
            f"授權已於 {expiry} 到期（已超過 {_GRACE_DAYS} 天寬限期），"
            f"請聯繫管理員續期"
        )
        return result

    # 在寬限期內
    if today > exp_dt:
        result["grace"] = True
        result["reason"] = (
            f"授權已於 {expiry} 到期，寬限期將於 {grace_end} 結束\n"
            f"請盡快聯繫管理員續期"
        )

    # ── 全部通過 ──
    # 記下這次的 renewal_key 到 registry，防止重複使用
    if _sys.platform == "win32":
        _write_registry(_REG_LAST_RENEWAL_KEY, renewal_key)
        _write_registry(_REG_ACTIVATED_MAC, current_mac)

    result["valid"] = True
    result["reason"] = "授權有效"
    return result


def activate_license(lic_path: Optional[str] = None) -> dict:
    """首次啟用授權：寫入 InstallID 到 registry 並記錄 renewal_key

    在用戶第一次放置 license.lic 時呼叫。會建立 registry 中的 InstallID。
    """
    import sys as _sys

    if lic_path is None:
        lic_path = os.path.join(_LICENSE_DIR, _LICENSE_FILE)

    result = {"success": False, "reason": ""}

    if not os.path.exists(lic_path):
        result["reason"] = "找不到授權檔案"
        return result

    try:
        with open(lic_path, "r", encoding="utf-8") as f:
            lic_data = json.load(f)
    except Exception:
        result["reason"] = "授權檔案格式錯誤"
        return result

    install_id_from_lic = lic_data.get("install_id", "")
    renewal_key = lic_data.get("renewal_key", "")
    mac_from_lic = lic_data.get("mac", "")

    if not install_id_from_lic:
        result["reason"] = "授權檔案中缺少 InstallID"
        return result

    # 檢查 MAC 是否匹配
    if mac_from_lic and mac_from_lic.upper() != get_mac_address():
        result["reason"] = "此授權檔案與本機 MAC 不符"
        return result

    # 寫入 registry
    if _sys.platform == "win32":
        _write_registry(_REG_INSTALL_ID, install_id_from_lic)
        if renewal_key:
            _write_registry(_REG_LAST_RENEWAL_KEY, renewal_key)
        _write_registry(_REG_ACTIVATED_MAC, get_mac_address())

        # 驗證寫入成功
        actual = _read_registry(_REG_INSTALL_ID)
        if actual != install_id_from_lic:
            result["reason"] = "寫入 registry 失敗，請以系統管理員身分執行"
            return result

    result["success"] = True
    result["reason"] = "授權啟用成功"
    return result


def get_license_path() -> str:
    """取得 license 檔案預設路徑"""
    return os.path.join(_LICENSE_DIR, _LICENSE_FILE)


def get_license_status() -> dict:
    """取得授權狀態資訊（供 UI 顯示）

    Returns:
        {
            "activated": bool,
            "valid": bool,
            "days_remaining": int,
            "expiry": str,
            "grace": bool,
            "mac": str,
            "install_id": str,
        }
    """
    result = verify_license()
    stored_id = get_stored_install_id()

    return {
        "activated": stored_id is not None,
        "valid": result["valid"],
        "days_remaining": result.get("days_remaining", 0),
        "expiry": result.get("expiry", ""),
        "grace": result.get("grace", False),
        "mac": get_mac_address(),
        "install_id": stored_id or "",
    }
