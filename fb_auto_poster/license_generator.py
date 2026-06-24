"""
============================================
  FB POSTER — License 授權碼產生器 (V3)
============================================
  僅限管理員使用！請勿交給員工！

  新版功能:
    - MAC + InstallID 雙重綁定（防止複製到其他電腦）
    - 月租模式：每 30 天需續期
    - Renewal Key 防重複使用
    - Grace Window：到期後 3 天寬限期

  用法:
    python license_generator.py                     → 互動模式
    python license_generator.py --generate          → 產生授權
    python license_generator.py --verify license.lic → 驗證授權
    python license_generator.py --info              → 顯示本機資訊 (MAC + InstallID)
    python license_generator.py --init              → 初始化員工端 registry

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
    get_or_create_install_id,
    get_stored_install_id,
    create_license,
    verify_license,
    activate_license,
    get_license_path,
    get_last_renewal_key,
    _delete_registry_key,
)


def print_banner():
    print("=" * 52)
    print("  FB POSTER — License 授權管理工具 V3")
    print("  " + "=" * 52)
    print()


def show_info():
    """顯示本機資訊（MAC + InstallID），管理員需要此資訊來產生授權"""
    print("📍 本機授權資訊")
    print("-" * 40)

    mac = get_mac_address()
    install_id = get_or_create_install_id()

    print(f"   MAC 地址:   {mac}")
    print(f"   InstallID:  {install_id}")
    print()
    print("請將以上資訊提供給管理員以產生授權檔案。")
    print("InstallID 已自動寫入 Windows Registry。")
    print()


def do_init_employee():
    """初始化員工端：產生並儲存 InstallID 到 registry"""
    print("🔧 初始化授權環境")
    print("-" * 40)

    install_id = get_or_create_install_id()

    print(f"   ✓ InstallID 已建立: {install_id}")
    print()
    print("請執行以下步驟:")
    print(f"   1. 將上方 InstallID 和 MAC 地址 ({get_mac_address()})")
    print(f"      提供給管理員")
    print(f"   2. 管理員會產生 license.lic 授權檔給你")
    print(f"   3. 將 license.lic 放到: {get_license_path()}")
    print()


def do_generate():
    print("📝 產生月租授權檔案")
    print("-" * 40)

    mac = input("請輸入員工電腦的 MAC 地址: ").strip().upper()
    if not mac:
        print("❌ MAC 地址不可為空")
        return

    install_id = input("請輸入員工電腦的 InstallID: ").strip()
    if not install_id:
        print("❌ InstallID 不可為空")
        return

    print()
    print("核發日期:")
    print("  1. 使用今天 (預設)")
    print("  2. 自訂日期")
    choice = input("請選擇 [1]: ").strip()

    if choice == "2":
        issued = input("請輸入核發日期 (YYYY-MM-DD): ").strip()
        try:
            from datetime import datetime
            datetime.strptime(issued, "%Y-%m-%d")
        except ValueError:
            print("❌ 日期格式錯誤")
            return
    else:
        from datetime import datetime
        issued = datetime.now().strftime("%Y-%m-%d")

    # 計算到期日
    from datetime import datetime, timedelta
    expiry_dt = datetime.strptime(issued, "%Y-%m-%d") + timedelta(days=30)
    expiry = expiry_dt.strftime("%Y-%m-%d")

    print()
    print(f"  授權摘要:")
    print(f"    MAC:        {mac}")
    print(f"    InstallID:  {install_id[:16]}...")
    print(f"    核發日:     {issued}")
    print(f"    到期日:     {expiry}")
    print(f"    有效天數:   30 天")
    print()

    confirm = input("確認產生? (Y/N): ").strip().upper()
    if confirm != "Y":
        print("❌ 已取消")
        return

    output = input(f"輸出檔案路徑 (Enter 使用預設名稱): ").strip()

    try:
        if output:
            path = create_license(mac, install_id, issued, output)
        else:
            # 輸出到當前目錄，命名為 license_YYYYMMDD.lic
            filename = f"license_{datetime.now().strftime('%Y%m%d')}.lic"
            path = create_license(mac, install_id, issued, filename)

        with open(path, "r", encoding="utf-8") as f:
            import json
            lic_data = json.load(f)

        print()
        print(f"✅ 授權已產生!")
        print(f"   檔案: {path}")
        print(f"   MAC:  {mac}")
        print(f"   InstallID: {install_id[:16]}...")
        print(f"   核發: {issued}")
        print(f"   到期: {expiry}")
        print(f"   續期金鑰: {lic_data['renewal_key'][:16]}...")
        print()
        print("📋 部署步驟:")
        print(f"   1. 將此 .lic 檔案傳給員工")
        print(f"   2. 員工放在: {get_license_path()}")
        print(f"   3. 員工執行程式，自動完成 registry 比對")
        print()
        print("⏰ 下次續期日: " + expiry)
        print("   (到期後有 3 天寬限期)")
    except Exception as e:
        print(f"❌ 產生失敗: {e}")


def do_renew():
    """續期：產生新的月租授權"""
    print("🔄 續期授權")
    print("-" * 40)

    lic_path = input(f"請輸入現有 license 檔案路徑 (Enter 使用預設): ").strip()
    if not lic_path:
        lic_path = get_license_path()

    if not os.path.exists(lic_path):
        print(f"❌ 找不到檔案: {lic_path}")
        print("   提示: 如果只有員工提供的 MAC + InstallID，請用「產生授權」功能")
        return

    # 讀取現有 license 取得 MAC 和 InstallID
    try:
        import json
        with open(lic_path, "r", encoding="utf-8") as f:
            old_lic = json.load(f)

        mac = old_lic.get("mac", "")
        install_id = old_lic.get("install_id", "")
        old_expiry = old_lic.get("expiry", "N/A")

        print(f"   現有授權:")
        print(f"     MAC:        {mac}")
        print(f"     InstallID:  {install_id[:16]}...")
        print(f"     原到期日:   {old_expiry}")
        print()
    except Exception as e:
        print(f"❌ 讀取失敗: {e}")
        return

    from datetime import datetime
    issued = datetime.now().strftime("%Y-%m-%d")
    expiry_dt = datetime.now() + __import__("datetime").timedelta(days=30)
    expiry = expiry_dt.strftime("%Y-%m-%d")

    print(f"   新授權:")
    print(f"     核發日:  {issued}")
    print(f"     到期日:  {expiry}")
    print()

    confirm = input("確認續期? (Y/N): ").strip().upper()
    if confirm != "Y":
        print("❌ 已取消")
        return

    try:
        output = input(f"輸出檔案路徑 (Enter 使用預設名稱): ").strip()
        filename = f"license_renew_{datetime.now().strftime('%Y%m%d')}.lic"

        path = create_license(mac, install_id, issued,
                              output if output else filename)

        print()
        print(f"✅ 續期授權已產生!")
        print(f"   檔案: {path}")
        print(f"   到期: {expiry}")
        print()
        print("📋 部署步驟:")
        print(f"   員工需用此新檔案替換舊的 license.lic")
        print(f"   （新舊檔案 renewal_key 不同，舊的會自動失效）")
    except Exception as e:
        print(f"❌ 續期失敗: {e}")


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

    print(f"   綁定 MAC:     {result.get('mac', 'N/A')}")
    print(f"   綁定 InstallID: {result.get('install_id', 'N/A')[:16]}...")
    print(f"   核發日期:     {result.get('issued', 'N/A')}")
    print(f"   到期日期:     {result.get('expiry', 'N/A')}")
    print(f"   剩餘天數:     {result.get('days_remaining', 'N/A')} 天")
    print(f"   寬限模式:     {'是' if result.get('grace') else '否'}")
    print(f"   本機 MAC:     {get_mac_address()}")
    print(f"   本機 InstallID: {get_stored_install_id() or '(未初始化)'}")

    if result["valid"]:
        print(f"\n✅ 狀態: 授權有效!")
    else:
        print(f"\n❌ 狀態: {result['reason']}")


def interactive_menu():
    while True:
        print()
        print("請選擇操作:")
        print("  1. 查看本機資訊 (MAC + InstallID)")
        print("  2. 初始化員工端環境")
        print("  3. 產生月租授權檔案")
        print("  4. 續期現有授權")
        print("  5. 驗證授權檔案")
        print("  6. 驗證預設授權 (data/license.lic)")
        print("  0. 離開")
        print()

        choice = input("請輸入編號: ").strip()

        if choice == "1":
            show_info()
        elif choice == "2":
            do_init_employee()
        elif choice == "3":
            do_generate()
        elif choice == "4":
            do_renew()
        elif choice == "5":
            do_verify()
        elif choice == "6":
            do_verify(get_license_path())
        elif choice == "0":
            print("👋 再見!")
            break
        else:
            print("❌ 無效的選擇")


if __name__ == "__main__":
    print_banner()

    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg == "--info":
            show_info()
        elif arg == "--init":
            do_init_employee()
        elif arg == "--generate":
            do_generate()
        elif arg == "--renew":
            do_renew()
        elif arg == "--verify":
            lic_path = sys.argv[2] if len(sys.argv) > 2 else None
            do_verify(lic_path)
        elif arg == "--help":
            print(__doc__)
        elif arg == "--reset":
            confirm = input("⚠ 確定要清除本機所有授權資訊? (YES/NO): ").strip()
            if confirm == "YES":
                _delete_registry_key()
                print("✅ Registry 授權資訊已清除")
        else:
            print(f"未知參數: {arg}")
            print("使用 --help 查看說明")
    else:
        interactive_menu()
