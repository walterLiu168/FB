"""系統匣模組 — pystray 背景執行

功能：
  - 關閉視窗時最小化到系統匣而不是退出
  - 系統匣圖示雙擊顯示視窗
  - 右鍵選單：顯示視窗 / 暫停排程 / 退出
  - 支援 Auto-start with Windows (可選)
"""
import os
import sys
import threading
from PIL import Image, ImageDraw


def _create_tray_icon(size: int = 64) -> Image.Image:
    """建立系統匣圖示 — FB 風格的藍色 'F' 方塊"""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # 藍色圓角方塊
    margin = 6
    draw.rounded_rectangle(
        [margin, margin, size - margin, size - margin],
        radius=size // 6,
        fill=(45, 125, 210),  # FB blue
    )
    return img


class SystemTray:
    """系統匣管理員"""

    def __init__(self, app):
        self._app = app
        self._tray = None
        self._icon_image = _create_tray_icon()
        self._paused = False

    def setup(self):
        """初始化系統匣"""
        try:
            import pystray
            menu = pystray.Menu(
                pystray.MenuItem("📋 顯示 FB Poster", self._show_window, default=True),
                pystray.MenuItem("⏸️ 暫停排程" if not self._paused else "▶️ 恢復排程", self._toggle_pause),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("❌ 完全退出", self._quit_app),
            )
            self._tray = pystray.Icon(
                "FB Poster",
                self._icon_image,
                "FB Poster — 自動發文",
                menu=menu,
            )
            # 雙擊顯示視窗
            self._tray.activate = self._on_activate
            threading.Thread(target=self._tray.run, daemon=True).start()
            return True
        except ImportError:
            return False

    def _on_activate(self, icon, item=None):
        """系統匣圖示被點擊"""
        if item is None:
            self._show_window(icon, item)

    def _show_window(self, icon=None, item=None):
        """顯示主視窗"""
        self._app.deiconify()
        self._app.lift()
        self._app.focus_force()
        self._app.attributes('-topmost', True)
        self._app.after(500, lambda: self._app.attributes('-topmost', False))

    def _toggle_pause(self, icon=None, item=None):
        """暫停/恢復排程"""
        self._paused = not self._paused
        if self._paused:
            self._app.scheduler.pause()
            self._app.status_var.set("⏸️ 排程已暫停 (系統匣)")
        else:
            self._app.scheduler.resume()
            self._app.status_var.set("▶️ 排程已恢復")
        # 重建選單
        self.setup()

    def _quit_app(self, icon=None, item=None):
        """完全退出"""
        self._app._do_full_close()

    def minimize_to_tray(self):
        """最小化到系統匣"""
        self._app.withdraw()
        self._app.status_var.set("📦 已最小化到系統匣 — 背景持續運作中")

    def show_notification(self, title: str, message: str):
        """顯示系統通知"""
        if self._tray:
            try:
                self._tray.notify(title=title, message=message)
            except Exception:
                pass

    def stop(self):
        """停止系統匣"""
        if self._tray:
            try:
                self._tray.stop()
            except Exception:
                pass


def setup_autostart(enable: bool) -> bool:
    """設定開機自動啟動
    
    寫入 Windows Startup 資料夾的捷徑。
    """
    import winreg
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    app_name = "FB_Poster"

    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
        if enable:
            exe_path = sys.executable
            script_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "run.py")
            command = f'"{exe_path}" "{script_path}"'
            winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, command)
        else:
            try:
                winreg.DeleteValue(key, app_name)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
        return True
    except Exception:
        return False


def is_autostart_enabled() -> bool:
    """檢查是否已設定開機自動啟動"""
    import winreg
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ)
        try:
            winreg.QueryValueEx(key, "FB_Poster")
            winreg.CloseKey(key)
            return True
        except FileNotFoundError:
            winreg.CloseKey(key)
            return False
    except Exception:
        return False
