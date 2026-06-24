"""主視窗應用程式 — 整合所有功能面板 (V3)"""
import tkinter as tk
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from tkinter import messagebox

from core.account import AccountManager
from core.scheduler import Scheduler, ScheduleJob
from core.templates import TemplateManager
from core.footprint_cleaner import FootprintCleaner
from core.auto_cleaner import AutoCleaner
from core.engine import SessionManager
from gui.account_manager import AccountManagerPanel
from gui.poster_panel import PosterPanel
from gui.scheduler_panel import SchedulerPanel
from gui.nurturer_panel import NurturerPanel
from gui.threads_panel import ThreadsPanel
from gui.log_panel import LogPanel
from gui.system_tray import SystemTray, setup_autostart, is_autostart_enabled
from core.fb_graph_poster import FBPageManager
from utils.logger import log


class FBPosterApp(ttk.Window):
    """FB 自動發文主應用程式"""

    def __init__(self):
        super().__init__(themename="darkly")
        self.title("FB POSTER")
        self.geometry("1200x800")
        self.minsize(900, 600)

        # 初始化核心模組（不啟動瀏覽器，延後到視窗就緒）
        self.account_manager = AccountManager()
        self.scheduler = Scheduler()
        self.template_manager = TemplateManager()
        self.footprint_cleaner = FootprintCleaner()
        self.auto_cleaner = AutoCleaner()
        self.fb_page_manager = FBPageManager()

        # 初始化發文引擎（背景執行緒 + Playwright）— **延後啟動瀏覽器**
        self.session_manager = SessionManager()
        self.session_manager.set_ui_callback(self.after)

        # 建立 UI
        self._build_menu()
        self._build_main_area()

        # 啟動排程器
        self.scheduler.load_persisted()

        # 註冊足跡清理回呼
        self.scheduler.register_callback("footprint_clean", self._on_footprint_clean)
        # 註冊自動刪文回呼（使用 AutoCleaner）
        self.scheduler.register_callback("auto_clean", self._on_auto_clean)
        # 每週補漏刪（同樣走 _on_auto_clean，參數 mode=weekly）
        self.scheduler.register_callback("auto_clean_weekly", self._on_auto_clean)
        self.scheduler.register_callback("post", self._on_scheduled_post)

        # 自動新增每小時足跡清理排程（如果尚未存在）
        self._setup_auto_footprint_clean()
        # 自動新增每日刪文排程（如果尚未存在）
        self._setup_auto_clean_schedule()

        self.scheduler.start()

        # 關閉事件 — 改為最小化到系統匣
        self.protocol("WM_DELETE_WINDOW", self._on_minimize_to_tray)
        
        # 初始化系統匣 (背景執行)
        self._tray = SystemTray(self)
        self._tray_ok = self._tray.setup()
        
        if not self._tray_ok:
            self.protocol("WM_DELETE_WINDOW", self._on_full_close)

        # 啟動後檢查設定狀態
        self.after(500, self._check_startup_status)

        # Force window to front
        self.attributes('-topmost', True)
        self.after(1000, lambda: self.attributes('-topmost', False))
        self.lift()
        self.focus_force()

    def _build_menu(self):
        """建立選單列"""
        menubar = ttk.Menu(self)
        self.config(menu=menubar)

        file_menu = ttk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Header/Footer 設定", command=self._show_template_settings)
        file_menu.add_command(label="自動刪文設定", command=self._show_clean_settings)
        file_menu.add_command(label="TikTok 設定", command=self._show_tiktok_settings)
        file_menu.add_command(label="FB API 設定", command=self._show_fb_api_settings)
        file_menu.add_separator()
        file_menu.add_command(label="📦 最小化到系統匣", command=self._on_minimize_to_tray)
        auto_start = is_autostart_enabled()
        file_menu.add_command(label=f"{'✅' if auto_start else '☐'} 開機自動啟動", command=self._toggle_autostart)
        file_menu.add_separator()
        file_menu.add_command(label="離開", command=self._on_full_close)
        menubar.add_cascade(label="檔案", menu=file_menu)

        help_menu = ttk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="關於", command=self._show_about)
        menubar.add_cascade(label="說明", menu=help_menu)

    def _build_main_area(self):
        """建立主內容區域 — 分頁切換"""
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 建立帳號映射 {顯示名稱: account_id}
        def build_account_map():
            m = {}
            for a in self.account_manager.list_active():
                m[f"{a.email} ({a.nickname})"] = a.account_id
            if not m:
                for a in self.account_manager.list_all():
                    m[f"{a.email} ({a.nickname})"] = a.account_id
            return m

        account_map = build_account_map()

        self.account_panel = AccountManagerPanel(
            self.notebook, self.account_manager,
            on_change=self._on_accounts_changed,
        )
        self.notebook.add(self.account_panel, text="帳號管理")

        account_ids = list(account_map.values())
        self.poster_panel = PosterPanel(
            self.notebook, account_ids=account_ids, account_map=account_map,
            engine=self.session_manager, scheduler=self.scheduler
        )
        self.notebook.add(self.poster_panel, text="發文")

        self.scheduler_panel = SchedulerPanel(
            self.notebook, self.scheduler, account_ids=account_ids
        )
        self.notebook.add(self.scheduler_panel, text="排程")

        self.nurturer_panel = NurturerPanel(
            self.notebook, account_ids=account_ids, engine=self.session_manager
        )
        self.notebook.add(self.nurturer_panel, text="養號")

        # Threads 分頁
        self.threads_panel = ThreadsPanel(
            self.notebook,
            engine=self.session_manager, scheduler=self.scheduler,
        )
        self.notebook.add(self.threads_panel, text="🧵 Threads")

        # 日誌分頁
        self.log_panel = LogPanel(self.notebook)
        self.notebook.add(self.log_panel, text="📋 日誌")

        # 狀態列
        self.status_var = ttk.StringVar(value="就緒")
        status_bar = ttk.Label(self, textvariable=self.status_var, font=("Arial", 9))
        status_bar.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=5)

    def _show_template_settings(self):
        """Header/Footer 設定視窗"""
        dialog = ttk.Toplevel(self)
        dialog.title("Header/Footer 範本設定")
        dialog.geometry("600x500")
        dialog.transient(self)
        dialog.grab_set()

        notebook = ttk.Notebook(dialog)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 全域預設分頁
        global_frame = ttk.Frame(notebook, padding=10)
        notebook.add(global_frame, text="全域預設")

        ttk.Label(global_frame, text="預設 Header (頁首):").pack(anchor=tk.W)
        global_header = tk.Text(global_frame, height=5, bg="#2b2b2b", fg="#ffffff", insertbackground="white")
        global_header.insert("1.0", self.template_manager.get_default_header())
        global_header.pack(fill=tk.X, pady=5)

        ttk.Label(global_frame, text="預設 Footer (頁尾):").pack(anchor=tk.W)
        global_footer = tk.Text(global_frame, height=5, bg="#2b2b2b", fg="#ffffff", insertbackground="white")
        global_footer.insert("1.0", self.template_manager.get_default_footer())
        global_footer.pack(fill=tk.X, pady=5)

        def save_global():
            self.template_manager.set_default_header(global_header.get("1.0", tk.END).strip())
            self.template_manager.set_default_footer(global_footer.get("1.0", tk.END).strip())
            self.poster_panel._load_header_footer()
            ttk.Messagebox.show_info("已儲存", "全域範本設定已儲存")

        ttk.Button(global_frame, text="儲存全域預設", command=save_global, bootstyle="success").pack(pady=10)

        # 各帳號分頁
        accounts_frame = ttk.Frame(notebook, padding=10)
        notebook.add(accounts_frame, text="各帳號設定")

        accounts = self.account_manager.list_all()
        if not accounts:
            ttk.Label(accounts_frame, text="尚無帳號，請先在「帳號管理」新增").pack(pady=20)
        else:
            canvas = tk.Canvas(accounts_frame, bg="#2b2b2b", highlightthickness=0)
            scrollbar = ttk.Scrollbar(accounts_frame, orient=tk.VERTICAL, command=canvas.yview)
            scroll_frame = ttk.Frame(canvas)

            scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
            canvas.create_window((0, 0), window=scroll_frame, anchor=tk.NW)
            canvas.configure(yscrollcommand=scrollbar.set)

            self._acc_header_entries = {}
            self._acc_footer_entries = {}

            for i, acc in enumerate(accounts):
                lf = ttk.LabelFrame(scroll_frame, text=acc.email)
                lf.pack(fill=tk.X, pady=5, padx=5)
                frame = ttk.Frame(lf, padding=8)
                frame.pack(fill=tk.X)

                ttk.Label(frame, text="Header:").pack(anchor=tk.W)
                h_entry = tk.Text(frame, height=2, bg="#2b2b2b", fg="#ffffff", insertbackground="white")
                h_entry.insert("1.0", self.template_manager.get_header(acc.account_id))
                h_entry.pack(fill=tk.X, pady=2)
                self._acc_header_entries[acc.account_id] = h_entry

                ttk.Label(frame, text="Footer:").pack(anchor=tk.W)
                f_entry = tk.Text(frame, height=2, bg="#2b2b2b", fg="#ffffff", insertbackground="white")
                f_entry.insert("1.0", self.template_manager.get_footer(acc.account_id))
                f_entry.pack(fill=tk.X, pady=2)
                self._acc_footer_entries[acc.account_id] = f_entry

            def save_accounts():
                for acc_id, entry in self._acc_header_entries.items():
                    self.template_manager.set_header(acc_id, entry.get("1.0", tk.END).strip())
                for acc_id, entry in self._acc_footer_entries.items():
                    self.template_manager.set_footer(acc_id, entry.get("1.0", tk.END).strip())
                self.poster_panel._load_header_footer()
                ttk.Messagebox.show_info("已儲存", "各帳號範本已儲存")

            ttk.Button(accounts_frame, text="儲存所有帳號設定", command=save_accounts, bootstyle="success").pack(pady=10)

            canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def _show_clean_settings(self):
        """自動刪文設定視窗"""
        dialog = ttk.Toplevel(self)
        dialog.title("自動刪文設定")
        dialog.geometry("450x340")
        dialog.transient(self)
        dialog.grab_set()

        from core.auto_cleaner import AutoCleaner
        cleaner = self.auto_cleaner  # 使用全域實例

        frame = ttk.Frame(dialog, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="自動刪文排程設定", font=("Arial", 14)).pack(anchor=tk.W)

        ttk.Label(frame, text="保留時間 (小時):").pack(anchor=tk.W, pady=(15, 0))
        retention_var = tk.StringVar(value=str(cleaner.get_retention()))
        retention_spin = ttk.Spinbox(frame, from_=1, to=720, width=8, textvariable=retention_var)
        retention_spin.pack(anchor=tk.W, pady=5)

        # ── 每日執行時間 ──
        _daily_h, _daily_m = 23, 0
        try:
            existing = [j for j in self.scheduler.get_jobs() if j.job_type == "auto_clean"]
            if existing:
                parts = (existing[0].cron_expr or "").strip().split()
                if len(parts) == 5 and parts[0].isdigit() and parts[1].isdigit():
                    _daily_m = int(parts[0])
                    _daily_h = int(parts[1])
        except Exception:
            pass
        time_row = ttk.Frame(frame)
        time_row.pack(anchor=tk.W, pady=(10, 0))
        ttk.Label(time_row, text="每日執行時間:").pack(side=tk.LEFT)
        daily_hour_var = tk.StringVar(value=f"{_daily_h:02d}")
        ttk.Spinbox(time_row, from_=0, to=23, width=5, format="%02.0f", textvariable=daily_hour_var).pack(side=tk.LEFT, padx=5)
        ttk.Label(time_row, text=":").pack(side=tk.LEFT)
        daily_min_var = tk.StringVar(value=f"{_daily_m:02d}")
        ttk.Spinbox(time_row, from_=0, to=59, width=5, format="%02.0f", textvariable=daily_min_var).pack(side=tk.LEFT)
        ttk.Label(time_row, text="  (例: 23:00 = 每晚 11 點)").pack(side=tk.LEFT, padx=5)

        # ── 每日刪除上限 ──
        ttk.Label(frame, text="每日最多刪除篇數（避免一次刪太多觸發驗證）:").pack(anchor=tk.W, pady=(8, 0))
        _daily_limit = 30
        try:
            existing_i = [j for j in self.scheduler.get_jobs() if j.job_type == "auto_clean"]
            if existing_i:
                _daily_limit = int((existing_i[0].params or {}).get("daily_limit", 30) or 30)
        except Exception:
            pass
        daily_limit_var = tk.StringVar(value=str(_daily_limit))
        daily_limit_spin = ttk.Spinbox(frame, from_=0, to=1000, width=8, textvariable=daily_limit_var)
        daily_limit_spin.pack(anchor=tk.W, pady=5)

        # ── 每週補漏刪（預設：週日 18:00） ──
        ttk.Label(frame, text="每週補漏刪（找出漏刪/抓不到 URL 的貼文）:").pack(anchor=tk.W, pady=(8, 0))

        weekly_enabled_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(frame, text="啟用每週補漏刪", variable=weekly_enabled_var).pack(anchor=tk.W, pady=2)

        _wh, _wm, _wdays = 18, 0, 7
        try:
            existing_w = [j for j in self.scheduler.get_jobs() if j.job_type == "auto_clean_weekly"]
            if existing_w:
                parts = (existing_w[0].cron_expr or "").strip().split()
                if len(parts) == 5:
                    _wm = int(parts[0])
                    _wh = int(parts[1])
                _wdays = int((existing_w[0].params or {}).get("days", 7) or 7)
        except Exception:
            pass

        weekly_row = ttk.Frame(frame)
        weekly_row.pack(anchor=tk.W, pady=2, fill=tk.X)
        ttk.Label(weekly_row, text="時間(週日):").pack(side=tk.LEFT)
        weekly_hour_var = tk.StringVar(value=f"{_wh:02d}")
        weekly_hour_spin = ttk.Spinbox(weekly_row, from_=0, to=23, width=5, format="%02.0f", textvariable=weekly_hour_var)
        weekly_hour_spin.pack(side=tk.LEFT, padx=(6, 0))
        ttk.Label(weekly_row, text=":").pack(side=tk.LEFT, padx=2)
        weekly_min_var = tk.StringVar(value=f"{_wm:02d}")
        weekly_min_spin = ttk.Spinbox(weekly_row, from_=0, to=59, width=5, format="%02.0f", textvariable=weekly_min_var)
        weekly_min_spin.pack(side=tk.LEFT)

        ttk.Label(weekly_row, text="  補漏天數:").pack(side=tk.LEFT, padx=(10, 0))
        weekly_days_var = tk.StringVar(value=str(_wdays))
        weekly_days_spin = ttk.Spinbox(weekly_row, from_=1, to=365, width=6, textvariable=weekly_days_var)
        weekly_days_spin.pack(side=tk.LEFT, padx=(6, 0))

        # 當前的排程任務
        ttk.Label(frame, text="").pack(pady=5)
        status_text = cleaner.estimate_next_clean()
        status_label = ttk.Label(frame, text=status_text, font=("Arial", 9))
        status_label.pack(anchor=tk.W)

        def preview_now():
            """只做掃描，不提交刪除任務"""
            try:
                n = cleaner.run_clean("system", params={"dry_run": True})
                status_label.configure(text=f"預演結果：目前有 {n} 篇貼文已到期")
            except Exception:
                status_label.configure(text="預演失敗：請檢查日誌")

        def run_now():
            """立即觸發一次刪文（走同一條排程流程）"""
            try:
                self._on_auto_clean("system", {})
                status_label.configure(text="已提交刪文任務（請看左下角狀態與日誌）")
            except Exception:
                status_label.configure(text="立即清理失敗：請檢查日誌")

        def save_clean():
            hours = int(retention_var.get())
            cleaner.set_retention(hours)
            from core.scheduler import ScheduleJob
            import uuid

            # 每日固定時間刪文
            daily_h = int(daily_hour_var.get())
            daily_m = int(daily_min_var.get())
            cron = f"{daily_m} {daily_h} * * *"
            existing = [j for j in self.scheduler.get_jobs() if j.job_type == "auto_clean"]
            for j in existing:
                self.scheduler.remove_job(j.job_id)
            job = ScheduleJob(
                job_id=str(uuid.uuid4()),
                account_id="system",
                job_type="auto_clean",
                cron_expr=cron,
                params={"retention_hours": hours, "daily_limit": int(daily_limit_var.get() or 30)},
            )
            self.scheduler.add_job(job)

            # 每週補漏刪（週日固定時間）
            try:
                existing_w = [j for j in self.scheduler.get_jobs() if j.job_type == "auto_clean_weekly"]
                for j in existing_w:
                    self.scheduler.remove_job(j.job_id)

                if weekly_enabled_var.get():
                    wh = int(weekly_hour_var.get())
                    wm = int(weekly_min_var.get())
                    days = int(weekly_days_var.get())
                    cron_w = f"{wm} {wh} * * 0"  # 週日
                    job_w = ScheduleJob(
                        job_id=str(uuid.uuid4()),
                        account_id="system",
                        job_type="auto_clean_weekly",
                        cron_expr=cron_w,
                        params={"mode": "weekly", "days": max(1, days), "daily_limit": int(daily_limit_var.get() or 30)},
                    )
                    self.scheduler.add_job(job_w)
            except Exception:
                pass

            ttk.Messagebox.show_info(
                "已儲存",
                f"自動刪文設定已更新\n每天 {daily_hour_var.get()}:{daily_min_var.get()} 執行一次\n保留 {hours} 小時內的貼文\n每日上限 {daily_limit_var.get()} 篇\n每週補漏刪：週日 {weekly_hour_var.get()}:{weekly_min_var.get()}",
            )
            dialog.destroy()

        btn_row = ttk.Frame(frame)
        btn_row.pack(pady=15, fill=tk.X)
        ttk.Button(btn_row, text="預演掃描", command=preview_now, bootstyle="info").pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_row, text="立即清理一次", command=run_now, bootstyle="warning").pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_row, text="儲存設定", command=save_clean, bootstyle="success").pack(side=tk.RIGHT, padx=5)

    def _show_tiktok_settings(self):
        """開啟 TikTok 帳號設定對話框"""
        from gui.tiktok_settings import TikTokSettingsDialog
        dialog = TikTokSettingsDialog(self)
        # 關閉後刷新發文面板的 TikTok 帳號下拉選單
        self.wait_window(dialog)
        if hasattr(self, "poster_panel") and hasattr(self.poster_panel, "_refresh_tiktok_accounts"):
            self.poster_panel._refresh_tiktok_accounts()

    def _show_fb_api_settings(self):
        """開啟 FB Graph API Token 設定對話框"""
        from gui.fb_token_dialog import FBTokenDialog
        dialog = FBTokenDialog(self)
        self.wait_window(dialog)
        # 關閉後刷新發文面板的 API 模式可用性
        if hasattr(self, "poster_panel") and hasattr(self.poster_panel, "_refresh_fb_api_pages"):
            self.poster_panel._refresh_fb_api_pages()

    def _show_about(self):
        """顯示關於資訊"""
        from tkinter import messagebox
        messagebox.showinfo(
            title="關於 FB POSTER",
            message="FB POSTER v3.0\n\nFacebook 自動發文工具\n\n✅ 多帳號管理\n✅ AI 文案生成 (Ollama)\n✅ 網頁圖片爬取\n✅ Header/Footer 範本\n✅ 自動排程發文/刪文\n✅ 操作日誌追蹤\n\n資料僅存於您的設備，安全無憂。",
        )

    def _on_accounts_changed(self):
        """帳號異動時刷新發文面板的下拉選單"""
        m = {}
        for a in self.account_manager.list_active():
            m[f"{a.email} ({a.nickname})"] = a.account_id
        if not m:
            for a in self.account_manager.list_all():
                m[f"{a.email} ({a.nickname})"] = a.account_id
        if hasattr(self, 'poster_panel'):
            self.poster_panel.refresh_accounts(m)

    def _on_close(self):
        """關閉應用程式 (deprecated, use _do_full_close)"""
        self._do_full_close()
    
    def _on_minimize_to_tray(self):
        """點 X → 最小化到系統匣"""
        if self._tray_ok:
            self._tray.minimize_to_tray()
        else:
            self._do_full_close()

    def _on_full_close(self):
        """直接關閉 (無系統匣 fallback)"""
        if messagebox.askyesno("確認關閉", "確定要完全退出 FB Poster？\n\n背景發文也會停止。"):
            self._do_full_close()

    def _do_full_close(self):
        """完全關閉應用程式"""
        self.session_manager.stop()
        self.scheduler.stop()
        self._tray.stop()
        self.destroy()

    def _toggle_autostart(self):
        """切換開機自動啟動"""
        current = is_autostart_enabled()
        ok = setup_autostart(not current)
        if ok:
            msg = "已開啟開機自動啟動" if not current else "已關閉開機自動啟動"
            self.status_var.set(f"🔄 {msg}")
            messagebox.showinfo("成功", msg)
        else:
            messagebox.showerror("失敗", "無法變更開機自動啟動設定")

    def _check_startup_status(self):
        """啟動後檢查必要設定，提示使用者缺少什麼。

        同時延後啟動瀏覽器引擎（等視窗已顯示後才啟動 Chromium），
        並設定共享瀏覽器給 scraper 模組重複使用。
        """
        # ── 延後啟動瀏覽器引擎 ──
        self.session_manager.start()

        # 設定共享瀏覽器給 scraper 模組
        def _wait_and_share_browser():
            if self.session_manager.is_browser_ready():
                browser = self.session_manager.get_browser()
                # 從 engine 取得事件迴圈（透過 worker thread 的 loop）
                loop = getattr(self.session_manager, '_loop', None)
                if browser and loop:
                    import core.scraper as scraper
                    scraper.set_shared_browser(browser, loop)
                    log("ENGINE", "system", "共享瀏覽器已就緒 (rakuya/抓圖共用)", "✅")
            else:
                self.after(2000, _wait_and_share_browser)

        self.after(3000, _wait_and_share_browser)

        # ── 檢查設定 ──
        issues = []

        # 檢查帳號是否有 Cookie
        accounts = self.account_manager.list_all()
        has_cookie = any(a.cookie_path for a in accounts)

        # 檢查是否有 FB API Page
        fb_pages = self.fb_page_manager.list_all()
        has_api_page = any(p.access_token_encrypted for p in fb_pages)

        if not accounts:
            issues.append("尚無帳號 → 請先在「帳號管理」新增 FB 帳號並匯入 Cookie")
        elif not has_cookie and not has_api_page:
            issues.append("帳號缺少 Cookie → 請在「帳號管理」匯入 FB Cookie (瀏覽器模式)")
            issues.append("或設定 Graph API →「檔案 → FB API 設定」新增 Page Token (API 模式)")

        if accounts and has_cookie and not has_api_page:
            self.status_var.set("✅ 瀏覽器模式就緒 (Cookie 已匯入) | 💡 也可設定 API 模式更快")
        elif accounts and has_api_page and not has_cookie:
            self.status_var.set("✅ API 模式就緒 (Page Token 已設定)")
        elif accounts and has_cookie and has_api_page:
            self.status_var.set("✅ 雙模式就緒 — 瀏覽器 + API 皆可用")
        elif issues:
            self.status_var.set("⚠️ 需要設定才能發文 — 詳見下方提示")

        if issues:
            # 彈出一次性提示
            msg = "FB POSTER 尚未完成設定，無法發文：\n\n" + "\n".join(f"• {i}" for i in issues)
            msg += "\n\n設定完成後即可開始自動發文！"
            from tkinter import messagebox
            messagebox.showinfo("歡迎使用 FB POSTER", msg, parent=self)

    def _setup_auto_footprint_clean(self):
        """自動設定每小時足跡清理排程（如果尚無此排程）"""
        import uuid
        existing = [j for j in self.scheduler.get_jobs() if j.job_type == "footprint_clean"]
        if existing:
            return  # 已有排程，不重複新增

        params = self.footprint_cleaner.schedule_job_params()
        job = ScheduleJob(
            job_id=str(uuid.uuid4()),
            account_id="system",
            job_type="footprint_clean",
            cron_expr=params["cron"],
        )
        self.scheduler.add_job(job)

    def _setup_auto_clean_schedule(self):
        """自動設定刪文排程（如果尚無此排程）

        預設每天 23:00 執行一次，每天最多刪 30 篇。
        既有排程若為舊格式（每10分鐘/凌晨3點）會自動升級。
        """
        import uuid
        jobs = self.scheduler.get_jobs()

        # 1) 每天固定時間刪文（預設 23:00）
        existing_daily = [j for j in jobs if j.job_type == "auto_clean"]
        if existing_daily:
            # 舊版可能還是 */10 或 0 3 * * *，升級成 0 23 * * *
            try:
                j0 = existing_daily[0]
                old_cron = (j0.cron_expr or "").strip()
                if old_cron != "0 23 * * *":
                    old_id = j0.job_id
                    self.scheduler.remove_job(old_id)
                    job = ScheduleJob(
                        job_id=old_id,
                        account_id="system",
                        job_type="auto_clean",
                        cron_expr="0 23 * * *",
                        params=dict(j0.params or {}, **{"retention_hours": 168, "daily_limit": 30}),
                    )
                    self.scheduler.add_job(job)
            except Exception:
                pass
        else:
            job = ScheduleJob(
                job_id=str(uuid.uuid4()),
                account_id="system",
                job_type="auto_clean",
                cron_expr="0 23 * * *",  # 每天 23:00
                params={"retention_hours": 168, "daily_limit": 30},
            )
            self.scheduler.add_job(job)

        # 2) 每週補漏刪（週日 18:00）
        existing_weekly = [j for j in jobs if j.job_type == "auto_clean_weekly"]
        if not existing_weekly:
            job2 = ScheduleJob(
                job_id=str(uuid.uuid4()),
                account_id="system",
                job_type="auto_clean_weekly",
                cron_expr="0 18 * * 0",  # 每週日 18:00
                params={"mode": "weekly", "days": 7, "daily_limit": 30},
            )
            self.scheduler.add_job(job2)

    def _on_auto_clean(self, account_id: str, params: dict):
        """定時觸發自動刪文 — 優先使用 PostStore 的 post_url 精準刪除

        params:
          - mode="weekly": 每週補漏刪（掃描超過 N 天未刪的紀錄）
          - days: 補漏天數
        """
        from datetime import datetime

        # 先用 PostStore（新方案：URL + DB）
        try:
            from core import post_store

            mode = (params or {}).get("mode", "")
            daily_limit = int((params or {}).get("daily_limit", 30) or 30)
            if mode == "weekly":
                days = int((params or {}).get("days", 7) or 7)
                items = post_store.get_weekly_candidates(days=days, limit=50)
                # weekly 只補漏：若 delete_at 還在未來，跳過
                now = datetime.now()
                now_s = now.strftime("%Y-%m-%d %H:%M")
                items = [it for it in items if not it.get("delete_at") or it.get("delete_at") <= now_s]
                tag = f"每週補漏({days}天)"
            else:
                items = post_store.get_due(limit=50)
                tag = "到點刪除"

            if items:
                # 每日上限控制（以『已提交刪除任務』作保守計數）
                try:
                    from core.clean_quota import reserve
                    quota_tag = "weekly" if mode == "weekly" else "interval"
                    allowed = reserve(len(items), daily_limit=daily_limit, tag=quota_tag)
                    if allowed <= 0:
                        log("CLEAN", "system", f"排程清理({tag}): 今日已達上限 {daily_limit}，跳過", "✅")
                        return
                    items = items[:allowed]
                except Exception:
                    # 若配額模組出錯，就不阻擋刪除流程
                    pass

                log("CLEAN", "system", f"排程清理({tag}): {len(items)} 筆待刪", "⏳")

                for it in items:
                    post_id = int(it.get("id") or 0)
                    aid = it.get("account_id") or account_id
                    post_url = (it.get("post_url") or "").strip()
                    target_type = (it.get("target_type") or "wall").strip()
                    target_url = (it.get("target_url") or "").strip()

                    def _ok(r, _pid=post_id, _aid=aid, _purl=post_url):
                        try:
                            if (r or {}).get("deleted", 0) > 0:
                                post_store.mark_deleted(_pid)
                                log("CLEAN", _aid, "刪文成功", "🗑️", detail=_purl[:80] if _purl else "")
                            else:
                                post_store.mark_failed(_pid, "未刪除（可能權限/版型/已刪）")
                                log("CLEAN", _aid, "刪文未成功", "⚠️", detail=_purl[:80] if _purl else "")
                        except Exception:
                            pass

                    def _err(r, _pid=post_id, _aid=aid, _purl=post_url):
                        try:
                            post_store.mark_failed(_pid, (r or {}).get("error", "刪文例外"))
                        except Exception:
                            pass
                        log("CLEAN", _aid, "刪文失敗", "❌", detail=_purl[:80] if _purl else "")

                    # 1) 有 post_url → 精準刪
                    if post_url:
                        self.session_manager.delete_now(
                            account_id=aid,
                            target="url",
                            params={"post_url": post_url},
                            callback=_ok,
                            error_callback=_err,
                        )
                    # 2) 沒 URL → fallback（社團/個人頁面）
                    elif target_type == "group" and target_url:
                        self.session_manager.delete_now(
                            account_id=aid,
                            target="group",
                            params={"group_url": target_url, "max": 3},
                            callback=_ok,
                            error_callback=_err,
                        )
                    else:
                        self.session_manager.delete_now(
                            account_id=aid,
                            target="wall",
                            params={"max": 3},
                            callback=_ok,
                            error_callback=_err,
                        )

                log("CLEAN", "system", f"排程清理({tag}): 已提交 {len(items)} 筆任務", "✅")
                return
        except Exception:
            pass

        # 若 PostStore 尚無資料（舊資料），才降級走舊的 pending_deletes.json
        from core.auto_cleaner import get_expired_deletes, remove_pending_deletes, get_pending_deletes
        expired = get_expired_deletes()
        if not expired:
            log("CLEAN", "system", "排程清理: 無過期待刪貼文", "✅")
            return

        log("CLEAN", "system", f"排程清理(舊佇列): 發現 {len(expired)} 篇過期待刪", "⏳")

        by_account: dict[str, list[dict]] = {}
        for item in expired:
            aid = item.get("account_id", account_id)
            by_account.setdefault(aid, []).append(item)

        cleaned_indices = set()
        all_pending = get_pending_deletes()
        account_id_to_wall_count: dict[str, int] = {}

        for item in expired:
            for i, p in enumerate(all_pending):
                if p.get("delete_at") == item.get("delete_at") and \
                   p.get("account_id") == item.get("account_id") and \
                   p.get("detail") == item.get("detail"):
                    cleaned_indices.add(i)
                    break

        for aid, items in by_account.items():
            for item in items:
                gurl = item.get("group_url", "")
                if gurl:
                    self.session_manager.delete_now(
                        account_id=aid,
                        target="group",
                        params={"group_url": gurl, "max": 3},
                        callback=lambda r, a=aid: log("CLEAN", a, f"社團刪文: {r.get('deleted', 0)} 篇", "🗑️"),
                        error_callback=lambda r, a=aid: log("CLEAN", a, f"社團刪文失敗", "❌"),
                    )
                else:
                    account_id_to_wall_count[aid] = account_id_to_wall_count.get(aid, 0) + 1

            for wall_aid, count in account_id_to_wall_count.items():
                self.session_manager.delete_now(
                    account_id=wall_aid,
                    target="wall",
                    params={"max": min(count * 2, 50)},
                    callback=lambda r, a=wall_aid: log("CLEAN", a, f"個人刪文: {r.get('deleted', 0)} 篇", "🗑️"),
                    error_callback=lambda r, a=wall_aid: log("CLEAN", a, f"個人刪文失敗", "❌"),
                )

        if cleaned_indices:
            remove_pending_deletes(cleaned_indices)

        log("CLEAN", "system", f"排程清理(舊佇列): 已提交 {len(expired)} 篇刪除任務", "✅")

    def _on_scheduled_post(self, account_id: str, params: dict):
        """定時觸發排程發文（由 APScheduler 呼叫，只執行一次）"""
        content = params.get("content", "")
        images = params.get("images", [])
        groups = params.get("groups")
        delete_at = params.get("delete_at", "")
        retention_hours = params.get("retention_hours", 168)

        group_str = ", ".join(groups) if groups else "個人頁面"
        detail = f"排程發送到「{group_str}」"
        log("SCHEDULER", "post", detail, "🕐 排程觸發", schedule_delete_at=delete_at)
        self.status_var.set(f"🕐 排程發送中 → {group_str}...")

        # 儲存活頁簿待刪除記錄
        if delete_at:
            from core.auto_cleaner import add_pending_delete
            for g in (groups or [None]):
                gurl = ""
                gdetail = detail
                if g:
                    if "facebook.com/groups/" in g:
                        gurl = g
                    gdetail = f"排程發送到「{g}」"
                add_pending_delete(
                    account_id=account_id,
                    delete_at=delete_at,
                    detail=gdetail,
                    group_url=gurl,
                    retention_hours=retention_hours,
                )

        def on_success(result):
            status_text = f"✅ 排程發送成功! (將於 {delete_at or '手動'} 刪除)"
            self.status_var.set(status_text)
            log("SCHEDULER", "post", status_text, "✅")

        def on_error(result):
            status_text = f"❌ 排程發送失敗: {result.get('error', '未知')}"
            self.status_var.set(status_text)
            log("SCHEDULER", "post", status_text, "❌")

        self.session_manager.post_now(
            account_id=account_id,
            content=content,
            images=images,
            groups=groups,
            delete_at=delete_at,
            detail=detail,
            auto_like=bool(params.get("auto_like", False)),
            callback=on_success,
            error_callback=on_error,
        )

        # 排程任務只執行一次，完成後自動移除
        job_id = params.get("job_id", "")
        if job_id:
            from core.scheduler import ScheduleJob
            self.scheduler.remove_job(job_id)

    def _on_footprint_clean(self, account_id: str, params: dict):
        """定時觸發足跡清理（同步版本，APScheduler BackgroundScheduler 呼叫）"""
        import asyncio
        accounts = self.session_manager._account_manager.list_active()
        ids = [a.account_id for a in accounts]
        # 在 engine 的 event loop 中執行非同步清理
        loop = self.session_manager._loop
        if loop:
            asyncio.run_coroutine_threadsafe(
                self.footprint_cleaner.clean_all_accounts(ids), loop
            )
