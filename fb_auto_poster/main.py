"""FB POSTER — 主程式入口 (含 License 檢查 + 首次啟用)"""
import sys
import os
import tkinter as tk
from tkinter import messagebox

# 確保專案目錄在 sys.path 中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.license import (
    verify_license,
    activate_license,
    get_mac_address,
    get_or_create_install_id,
    get_stored_install_id,
    get_license_path,
    get_license_status,
)


def check_license() -> bool:
    """啟動前檢查 license，無效則顯示錯誤並回傳 False

    支援流程:
      1. 首次安裝 → 引導用戶提供 MAC + InstallID 給管理員
      2. 已有 registry 但無 license → 提示放置 license.lic
      3. license 有效 → 正常啟動
      4. license 到期（寬限期內）→ 警告但仍允許啟動
      5. license 完全失效 → 拒絕啟動
    """
    result = verify_license()

    if result["valid"]:
        # Grace 模式下仍有 warning
        if result.get("grace"):
            root = tk.Tk()
            root.withdraw()
            root.title("授權提醒")
            messagebox.showwarning(
                "授權即將到期",
                f"{result['reason']}\n\n"
                f"剩餘寬限天數有限，請盡快聯繫管理員。",
            )
            root.destroy()
        return True

    # ── License 無效 → 判斷原因並顯示對應訊息 ──
    reason = result["reason"]
    mac = get_mac_address()
    install_id = get_stored_install_id()

    root = tk.Tk()
    root.withdraw()
    root.title("授權檢查")

    # 判斷是否為首次安裝（registry 未初始化）
    if install_id is None:
        # 首次安裝 → 初始化 InstallID
        install_id = get_or_create_install_id()

        messagebox.showinfo(
            "首次安裝 — 需要授權",
            f"歡迎使用 FB POSTER！\n\n"
            f"請將以下資訊提供給管理員以取得授權：\n\n"
            f"📌 MAC 地址: {mac}\n"
            f"📌 InstallID: {install_id}\n\n"
            f"管理員會提供 license.lic 檔案，\n"
            f"請將其放置於:\n{get_license_path()}",
        )
        root.destroy()
        return False

    # 各式錯誤
    if "找不到授權檔案" in reason:
        messagebox.showerror(
            "授權驗證失敗",
            f"找不到授權檔案\n\n"
            f"本機 MAC: {mac}\n"
            f"InstallID: {install_id}\n\n"
            f"請將管理員提供的 license.lic 放置於:\n"
            f"{get_license_path()}",
        )
    elif "已被使用過" in reason:
        messagebox.showerror(
            "授權驗證失敗",
            f"{reason}\n\n"
            f"本機 MAC: {mac}\n\n"
            f"請聯繫管理員取得新的月租授權。",
        )
    else:
        messagebox.showerror(
            "授權驗證失敗",
            f"FB POSTER 無法啟動\n\n"
            f"原因: {reason}\n\n"
            f"本機 MAC: {mac}\n"
            f"InstallID: {install_id[:16] if install_id else '無'}...\n\n"
            f"請聯繫管理員取得有效的授權檔案 (license.lic)，\n"
            f"並放置於 {get_license_path()}",
        )
    root.destroy()
    return False


def main():
    # 先檢查 license
    if not check_license():
        sys.exit(1)

    # License 通過 → 啟動主程式
    from gui.app import FBPosterApp
    app = FBPosterApp()
    app.mainloop()


if __name__ == "__main__":
    main()
