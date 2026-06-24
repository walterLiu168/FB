"""
============================================
  FB POSTER — License 授權碼產生器
============================================
  僅限管理員使用！請勿交給員工！

  用法:
    python license_generator.py                     → 互動模式
    python license_generator.py --generate          → 產生授權
    python license_generator.py --verify license.lic → 驗證授權
    python license_generator.py --mac               → 顯示本機 MAC

  也可編譯成 .exe:
    pip install pyinstaller
    pyinstaller --onefile --console license_generator.py
============================================
"""
import sys
import os

# 確保能找到 core/license.py
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.license import (
    get_mac_address,
    create_license,
    verify_license,
    get_license_path,
)


def print_banner():
    print("=" * 52)
    print("  FB POSTER — License 授權管理工具")
    print("  " + "=" * 52)
    print()


def show_mac():
    mac = get_mac_address()
    print(f"📍 本機 MAC 地址: {mac}")
    print()
    print("將此 MAC 提供給 license_generator 產生授權檔。")
    print()


def do_generate():
    print("📝 產生授權檔案")
    print("-" * 40)

    mac = input("請輸入員工電腦的 MAC 地址: ").strip().upper()
    if not mac:
        print("❌ MAC 地址不可為空")
        return

    expiry = input("請輸入到期日 (格式 YYYY-MM-DD，e.g. 2026-12-31): ").strip()
    if not expiry:
        print("❌ 到期日不可為空")
        return

    try:
        from datetime import datetime
        datetime.strptime(expiry, "%Y-%m-%d")
    except ValueError:
        print("❌ 日期格式錯誤，請使用 YYYY-MM-DD 格式")
        return

    output = input(f"輸出檔案路徑 (Enter 使用預設: {get_license_path()}): ").strip()

    try:
        if output:
            path = create_license(mac, expiry, output)
        else:
            path = create_license(mac, expiry)

        print()
        print(f"✅ License 已產生!")
        print(f"   檔案: {path}")
        print(f"   MAC:  {mac}")
        print(f"   到期: {expiry}")
        print()
        print("請將此 license.lic 檔案傳給員工，放到 data/ 目錄下。")
    except Exception as e:
        print(f"❌ 產生失敗: {e}")


def do_verify(lic_path=None):
    if not lic_path:
        lic_path = input("請輸入 license 檔案路徑 (Enter 使用預設): ").strip()
        if not lic_path:
            lic_path = get_license_path()

    if not os.path.exists(lic_path):
        print(f"❌ 找不到檔案: {lic_path}")
        return

    print(f"🔍 正在驗證: {lic_path}")
    print("-" * 40)

    result = verify_license(lic_path)
    mac = result.get("mac", "N/A")
    expiry = result.get("expiry", "N/A")

    print(f"   綁定 MAC: {mac}")
    print(f"   到期日期: {expiry}")
    print(f"   本機 MAC: {get_mac_address()}")

    if result["valid"]:
        print(f"\n✅ 狀態: 授權有效!")
    else:
        print(f"\n❌ 狀態: {result['reason']}")


def interactive_menu():
    while True:
        print()
        print("請選擇操作:")
        print("  1. 查看本機 MAC 地址")
        print("  2. 產生授權檔案 (給員工)")
        print("  3. 驗證授權檔案")
        print("  4. 驗證預設授權 (data/license.lic)")
        print("  0. 離開")
        print()

        choice = input("請輸入編號: ").strip()

        if choice == "1":
            show_mac()
        elif choice == "2":
            do_generate()
        elif choice == "3":
            do_verify()
        elif choice == "4":
            do_verify(get_license_path())
        elif choice == "0":
            print("👋 再見!")
            break
        else:
            print("❌ 無效的選擇")


if __name__ == "__main__":
    print_banner()

    # 指令列參數模式
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg == "--mac":
            show_mac()
        elif arg == "--generate":
            do_generate()
        elif arg == "--verify":
            lic_path = sys.argv[2] if len(sys.argv) > 2 else None
            do_verify(lic_path)
        elif arg == "--help":
            print(__doc__)
        else:
            print(f"未知參數: {arg}")
            print("使用 --help 查看說明")
    else:
        # 互動模式
        interactive_menu()
