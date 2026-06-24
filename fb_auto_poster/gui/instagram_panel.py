"""Instagram 操作面板 — 發文 + 自動留言"""
import json, os, threading, tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime

from gui.dark_theme import (
    create_styled_button, create_styled_entry,
    create_styled_label, create_styled_frame
)
from gui.threads_panel import _load_ig_accounts, _save_ig_accounts, save_ig_cookie, load_ig_cookie
from utils.logger import log


class InstagramPanel(ttk.Frame):
    """Instagram 發文 + 自動留言面板"""

    def __init__(self, parent, engine=None, scheduler=None, **kwargs):
        super().__init__(parent, **kwargs)
        self.engine = engine
        self.scheduler = scheduler
        self.selected_images = []
        self._ig_accounts = _load_ig_accounts()

        self._nb = ttk.Notebook(self)
        self._nb.pack(fill=tk.BOTH, expand=True)

        self._build_post_tab()
        self._build_comment_tab()

    # ════════════════════════════════════════════
    #  IG 帳號選擇（共用）
    # ════════════════════════════════════════════

    def _refresh_ig_list_internal(self):
        pass  # uses shared storage from threads_panel

    def _get_selected_ig_account(self) -> dict | None:
        """從 threads_accounts.json 取得第一個有 cookie 的 IG 帳號"""
        for acc in self._ig_accounts:
            if acc.get("has_cookie"):
                return acc
        return None

    # ════════════════════════════════════════════
    #  發文頁籤
    # ════════════════════════════════════════════

    def _build_post_tab(self):
        tab = ttk.Frame(self._nb)
        self._nb.add(tab, text="📸 發文")

        # ─ 帳號狀態 ─
        row = ttk.Frame(tab)
        row.pack(fill=tk.X, padx=12, pady=(12, 4))
        create_styled_label(row, "IG 帳號:").pack(side=tk.LEFT)
        self._ig_status_var = tk.StringVar(value=self._get_account_status())
        ttk.Label(row, textvariable=self._ig_status_var).pack(side=tk.LEFT, padx=8)
        create_styled_button(row, "🔄 重新整理", self._refresh_status, "secondary").pack(side=tk.RIGHT)

        # ─ Caption ─
        create_styled_label(tab, "貼文內容:").pack(anchor=tk.W, padx=12, pady=(8, 2))
        self._ig_caption = tk.Text(tab, height=4, wrap=tk.WORD, font=("Microsoft JhengHei", 10))
        self._ig_caption.pack(fill=tk.X, padx=12, pady=(0, 6))

        # ─ 圖片 ─
        img_frame = ttk.Frame(tab)
        img_frame.pack(fill=tk.X, padx=12, pady=(4, 2))
        create_styled_label(img_frame, "圖片 (必須):").pack(side=tk.LEFT)
        self._img_count_lbl = create_styled_label(img_frame, "0 張")
        self._img_count_lbl.pack(side=tk.LEFT, padx=8)
        create_styled_button(img_frame, "選擇圖片", self._select_images, "secondary").pack(side=tk.LEFT, padx=4)
        create_styled_button(img_frame, "清除", self._clear_images, "danger").pack(side=tk.LEFT)

        # ─ 注意事項 ─
        note = ttk.LabelFrame(tab, text="⚠ 注意")
        note.pack(fill=tk.X, padx=12, pady=8)
        ttk.Label(note, text=(
            "• IG 不支援純文字貼文，必須上傳至少一張圖片\n"
            "• 個人帳號使用瀏覽器自動化（非官方 API），請謹慎使用\n"
            "• 建議發文頻率：每小時不超過 2 篇，每天不超過 10 篇\n"
            "• 使用前請在 🧵 Threads → IG 帳號 匯入 Cookie"
        ), justify=tk.LEFT, font=("Microsoft JhengHei", 9)).pack(padx=10, pady=6)

        # ─ 發文按鈕 ─
        btn_row = ttk.Frame(tab)
        btn_row.pack(fill=tk.X, padx=12, pady=(8, 12))
        create_styled_button(btn_row, "🚀 發布到 Instagram", self._post_ig_now, "success").pack(side=tk.LEFT)
        self._post_status = create_styled_label(btn_row, "")
        self._post_status.pack(side=tk.LEFT, padx=12)

    def _get_account_status(self):
        acc = self._get_selected_ig_account()
        if acc:
            return f"✅ {acc.get('username', '')} (已匯入 Cookie)"
        return "❌ 尚未設定 IG 帳號 → 請到 🧵 Threads → IG 帳號"

    def _refresh_status(self):
        self._ig_accounts = _load_ig_accounts()
        self._ig_status_var.set(self._get_account_status())

    def _select_images(self):
        paths = filedialog.askopenfilenames(
            title="選擇圖片", filetypes=[("Images", "*.jpg *.jpeg *.png *.webp")]
        )
        if paths:
            self.selected_images = list(paths)
            self._img_count_lbl.config(text=f"{len(self.selected_images)} 張")

    def _clear_images(self):
        self.selected_images = []
        self._img_count_lbl.config(text="0 張")

    def _post_ig_now(self):
        caption = self._ig_caption.get("1.0", tk.END).strip()
        if not caption:
            messagebox.showwarning("警告", "請輸入貼文內容")
            return
        if not self.selected_images:
            messagebox.showwarning("警告", "IG 必須上傳圖片（不支援純文字貼文）")
            return
        acc = self._get_selected_ig_account()
        if not acc:
            messagebox.showwarning("警告", "請先在 Threads → IG 帳號 設定並匯入 Cookie")
            return
        if not self.engine:
            messagebox.showerror("錯誤", "發文引擎尚未啟動")
            return

        self._post_status.config(text="發文中...")
        self.engine.instagram_post_now(
            account_id=acc["account_id"],
            caption=caption,
            image_paths=self.selected_images,
            callback=lambda r: self.after(0, self._on_post_done, r),
            error_callback=lambda e: self.after(0, self._on_post_error, e),
        )

    def _on_post_done(self, result):
        if result.get("success"):
            self._post_status.config(text="✅ 發文成功!")
            self.selected_images = []
            self._img_count_lbl.config(text="0 張")
            self._ig_caption.delete("1.0", tk.END)
        else:
            self._post_status.config(text=f"❌ {result.get('error', '失敗')}")

    def _on_post_error(self, error):
        self._post_status.config(text=f"❌ {error.get('error', '失敗')}")

    # ════════════════════════════════════════════
    #  自動留言頁籤
    # ════════════════════════════════════════════

    def _build_comment_tab(self):
        tab = ttk.Frame(self._nb)
        self._nb.add(tab, text="💬 Hashtag 留言")

        # ─ Hashtag 關鍵字 ─
        kw_frame = ttk.LabelFrame(tab, text="Hashtag 關鍵字 (逗號分隔，不包含 #)")
        kw_frame.pack(fill=tk.X, padx=12, pady=(12, 6))
        self._ig_kw_var = tk.StringVar(value="創業, 電商, 副業, 行銷, 自媒體")
        create_styled_entry(kw_frame, textvariable=self._ig_kw_var).pack(fill=tk.X, padx=8, pady=8)

        # ─ 設定 ─
        set_frame = ttk.LabelFrame(tab, text="留言設定")
        set_frame.pack(fill=tk.X, padx=12, pady=6)

        r1 = ttk.Frame(set_frame)
        r1.pack(fill=tk.X, padx=8, pady=4)
        create_styled_label(r1, "每次最多留言:").pack(side=tk.LEFT)
        self._ig_max_var = tk.StringVar(value="10")
        ttk.Spinbox(r1, from_=1, to=30, textvariable=self._ig_max_var, width=5).pack(side=tk.LEFT, padx=8)

        r2 = ttk.Frame(set_frame)
        r2.pack(fill=tk.X, padx=8, pady=4)
        create_styled_label(r2, "留言間隔 (秒):").pack(side=tk.LEFT)
        self._ig_dmin = tk.StringVar(value="60")
        ttk.Spinbox(r2, from_=30, to=600, textvariable=self._ig_dmin, width=5).pack(side=tk.LEFT, padx=4)
        create_styled_label(r2, "~").pack(side=tk.LEFT)
        self._ig_dmax = tk.StringVar(value="180")
        ttk.Spinbox(r2, from_=60, to=900, textvariable=self._ig_dmax, width=5).pack(side=tk.LEFT, padx=4)

        # ─ 模板 ─
        tmpl_frame = ttk.LabelFrame(tab, text="留言模板庫")
        tmpl_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=6)

        tmpl_toolbar = ttk.Frame(tmpl_frame)
        tmpl_toolbar.pack(fill=tk.X, padx=8, pady=4)
        create_styled_button(tmpl_toolbar, "+ 新增", self._add_ig_template, "success").pack(side=tk.LEFT, padx=2)
        create_styled_button(tmpl_toolbar, "− 刪除選取", self._del_ig_template, "danger").pack(side=tk.LEFT, padx=2)

        lf = ttk.Frame(tmpl_frame)
        lf.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        self._ig_tmpl_list = tk.Listbox(lf, height=4, font=("Microsoft JhengHei", 9))
        s = ttk.Scrollbar(lf)
        self._ig_tmpl_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        s.pack(side=tk.RIGHT, fill=tk.Y)
        self._ig_tmpl_list.config(yscrollcommand=s.set)
        s.config(command=self._ig_tmpl_list.yview)
        self._load_ig_templates()

        # ─ 按鈕 ─
        btn_row = ttk.Frame(tab)
        btn_row.pack(fill=tk.X, padx=12, pady=(8, 4))
        create_styled_button(btn_row, "🔍 掃描預覽", self._ig_scan, "info").pack(side=tk.LEFT, padx=4)
        create_styled_button(btn_row, "💬 開始自動留言", self._ig_start, "success").pack(side=tk.LEFT, padx=4)
        self._ig_status = create_styled_label(btn_row, "")
        self._ig_status.pack(side=tk.LEFT, padx=12)

        # ─ 結果 ─
        rf = ttk.LabelFrame(tab, text="執行結果")
        rf.pack(fill=tk.BOTH, expand=True, padx=12, pady=(4, 12))
        self._ig_result = tk.Text(rf, height=5, wrap=tk.WORD, font=("Microsoft JhengHei", 9))
        self._ig_result.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

    def _load_ig_templates(self):
        try:
            from core.instagram_replier import InstagramReplier
            r = InstagramReplier()
            self._ig_tmpl_list.delete(0, tk.END)
            for t in r.list_templates():
                self._ig_tmpl_list.insert(tk.END, t[:60])
        except Exception:
            pass

    def _add_ig_template(self):
        dlg = tk.Toplevel(self)
        dlg.title("新增留言模板")
        dlg.geometry("400x150")
        ttk.Label(dlg, text="留言文字:").pack(padx=12, pady=(12, 4))
        entry = tk.Text(dlg, height=4, wrap=tk.WORD)
        entry.pack(fill=tk.X, padx=12, pady=4)

        def save():
            txt = entry.get("1.0", tk.END).strip()
            if txt:
                from core.instagram_replier import InstagramReplier
                InstagramReplier().add_template(txt)
                self._load_ig_templates()
            dlg.destroy()
        create_styled_button(dlg, "儲存", save, "success").pack(pady=8)

    def _del_ig_template(self):
        sel = self._ig_tmpl_list.curselection()
        if sel:
            from core.instagram_replier import InstagramReplier
            InstagramReplier().remove_template(sel[0])
            self._load_ig_templates()

    def _get_ig_keywords(self) -> list[str]:
        return [k.strip() for k in self._ig_kw_var.get().split(",") if k.strip()]

    def _ig_scan(self):
        self._do_ig_patrol(dry_run=True)

    def _ig_start(self):
        self._do_ig_patrol(dry_run=False)

    def _do_ig_patrol(self, dry_run=False):
        acc = self._get_selected_ig_account()
        if not acc:
            messagebox.showwarning("警告", "請先在 Threads → IG 帳號 匯入 Cookie")
            return
        if not self.engine:
            messagebox.showerror("錯誤", "引擎尚未啟動")
            return
        kw = self._get_ig_keywords()
        if not kw:
            messagebox.showwarning("警告", "請輸入至少一個 hashtag 關鍵字")
            return

        label = "掃描中..." if dry_run else "留言中..."
        self._ig_status.config(text=label)

        self.engine.instagram_patrol_now(
            account_id=acc["account_id"],
            keywords=kw,
            max_comments=int(self._ig_max_var.get()),
            dry_run=dry_run,
            callback=lambda r: self.after(0, self._on_ig_done, r, dry_run),
            error_callback=lambda e: self.after(0, self._on_ig_error, e),
        )

    def _on_ig_done(self, result, dry_run):
        a = "掃描" if dry_run else "留言"
        self._ig_status.config(text=f"✅ {a}完成")
        self._ig_result.delete("1.0", tk.END)
        self._ig_result.insert(tk.END, f"=== {a}結果 ===\n")
        self._ig_result.insert(tk.END, f"掃描: {result.get('scanned',0)} | 留言: {result.get('commented',0)} | 跳過: {result.get('skipped',0)}\n\n")
        for r in result.get("results", []):
            s = "✅" if r.get("success", True) else "❌"
            self._ig_result.insert(tk.END, f"{s} {r.get('url','')[:70]}\n")

    def _on_ig_error(self, error):
        self._ig_status.config(text=f"❌ {error.get('error', '失敗')}")
