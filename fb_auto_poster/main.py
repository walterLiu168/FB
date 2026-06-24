"""FB POSTER — 主程式入口 (含 License 檢查)"""
import sys
import os
import tkinter as tk
from tkinter import messagebox

# 確保專案目錄在 sys.path 中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.license import verify_license, get_mac_address


def check_license() -> bool:
    """啟動前檢查 license，無效則顯示錯誤並回傳 False"""
    result = verify_license()

    if result["valid"]:
        return True

    # License 無效 → 顯示錯誤視窗
    reason = result["reason"]
    mac = get_mac_address()

    # 初始化 Tkinter root 來顯示訊息框
    root = tk.Tk()
    root.withdraw()  # 隱藏主視窗
    root.title("授權檢查")

    messagebox.showerror(
        "授權驗證失敗",
        f"FB POSTER 無法啟動\n\n"
        f"原因: {reason}\n\n"
        f"本機 MAC: {mac}\n\n"
        f"請聯繫管理員取得有效的授權檔案 (license.lic)，\n"
        f"並放置於 data/license.lic",
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
