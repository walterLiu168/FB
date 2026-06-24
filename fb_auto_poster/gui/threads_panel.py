"""Threads 操作面板 — IG 帳號管理 + 自動發文 + 海巡回覆"""
import json
import os
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime

from gui.dark_theme import (
    create_styled_button, create_styled_entry,
    create_styled_label, create_styled_frame
)
from utils.logger import log

_IG_ACCOUNTS_FILE = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "threads_accounts.json"
)


# ════════════════════════════════════════════
#  IG 帳號儲存管理
# ════════════════════════════════════════════

def _load_ig_accounts() -> list[dict]:
    try:
        if os.path.exists(_IG_ACCOUNTS_FILE):
            with open(_IG_ACCOUNTS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return []


def _save_ig_accounts(accounts: list[dict]):
    os.makedirs(os.path.dirname(_IG_ACCOUNTS_FILE), exist_ok=True)
    with open(_IG_ACCOUNTS_FILE, "w", encoding="utf-8") as f:
        json.dump(accounts, f, ensure_ascii=False, indent=2)


def save_ig_cookie(account_id: str, cookie_json_str: str):
    """儲存 IG cookie 到檔案"""
    cookie_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "data", f"ig_cookies_{account_id}.json"
    )
    data = json.loads(cookie_json_str)
    with open(cookie_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return cookie_path


def load_ig_cookie(account_id: str) -> str:
    """讀取 IG cookie"""
    cookie_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "data", f"ig_cookies_{account_id}.json"
    )
    if not os.path.exists(cookie_path):
        return ""
    with open(cookie_path, "r", encoding="utf-8") as f:
        return f.read()


# ════════════════════════════════════════════
#  Threads 面板
# ════════════════════════════════════════════

class ThreadsPanel(ttk.Frame):
    """Threads.net — IG 帳號管理 + 發文 + 海巡回覆"""

    def __init__(self, parent, engine=None, scheduler=None, **kwargs):
        super().__init__(parent, **kwargs)
        self.engine = engine
        self.scheduler = scheduler
        self.selected_images = []
        self._ig_accounts = _load_ig_accounts()
        self._replier = None

        self._nb = ttk.Notebook(self)
        self._nb.pack(fill=tk.BOTH, expand=True)

        self._build_account_tab()
        self._build_post_tab()
        self._build_reply_tab()

    # ════════════════════════════════════════════
    #  帳號管理頁籤
    # ════════════════════════════════════════════

    def _build_account_tab(self):
        tab = ttk.Frame(self._nb)
        self._nb.add(tab, text="👤 IG 帳號")

        # ── 帳號列表 ──
        lbl = create_styled_label(tab, "已儲存的 Instagram 帳號:")
        lbl.pack(anchor=tk.W, padx=12, pady=(12, 4))

        list_frame = ttk.Frame(tab)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=4)
        self._ig_list = tk.Listbox(list_frame, height=5, font=("Microsoft JhengHei", 10))
        scrollbar = ttk.Scrollbar(list_frame)
        self._ig_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._ig_list.config(yscrollcommand=scrollbar.set)
        scrollbar.config(command=self._ig_list.yview)
        self._refresh_ig_list()

        # ── 按鈕行 ──
        btn_row = ttk.Frame(tab)
        btn_row.pack(fill=tk.X, padx=12, pady=8)
        create_styled_button(btn_row, "+ 新增 IG 帳號", self._add_ig_account, "success").pack(side=tk.LEFT, padx=2)
        create_styled_button(btn_row, "匯入 Cookie", self._import_ig_cookie, "info").pack(side=tk.LEFT, padx=2)
        create_styled_button(btn_row, "🗑 刪除帳號", self._delete_ig_account, "danger").pack(side=tk.LEFT, padx=2)

        # ── 說明 ──
        info_frame = ttk.LabelFrame(tab, text="📖 使用說明")
        info_frame.pack(fill=tk.X, padx=12, pady=12)

        help_text = (
            "1. 點擊「+ 新增 IG 帳號」輸入你的 Instagram 帳號名稱\n"
            "2. 在瀏覽器中登入 threads.net（使用同一個 IG 帳號）\n"
            "3. 使用瀏覽器擴充功能匯出 Cookie（JSON 格式）\n"
            "4. 點擊「匯入 Cookie」貼上 Cookie JSON 內容\n"
            "5. 切換到「發文」或「海巡回覆」分頁開始使用\n\n"
            "⚠ Threads 使用 Instagram 帳號登入，非 Facebook 帳號。"
        )
        info = ttk.Label(info_frame, text=help_text, justify=tk.LEFT, font=("Microsoft JhengHei", 9))
        info.pack(padx=10, pady=10, anchor=tk.W)

    def _refresh_ig_list(self):
        self._ig_list.delete(0, tk.END)
        for acc in self._ig_accounts:
            cookie_ok = "✅" if acc.get("has_cookie") else "❌"
            self._ig_list.insert(tk.END, f"{cookie_ok} {acc.get('username', '')}  [{acc.get('account_id', '')[:8]}...]")

    def _add_ig_account(self):
        dlg = tk.Toplevel(self)
        dlg.title("新增 IG 帳號")
        dlg.geometry("400x180")
        dlg.transient(self)
        dlg.grab_set()

        ttk.Label(dlg, text="Instagram 帳號名稱:").pack(padx=12, pady=(12, 4))
        username_var = tk.StringVar()
        create_styled_entry(dlg, textvariable=username_var).pack(fill=tk.X, padx=12, pady=4)

        ttk.Label(dlg, text="顯示名稱 (選填):").pack(padx=12, pady=4)
        nickname_var = tk.StringVar()
        create_styled_entry(dlg, textvariable=nickname_var).pack(fill=tk.X, padx=12, pady=4)

        def save():
            username = username_var.get().strip()
            if not username:
                messagebox.showwarning("警告", "請輸入 IG 帳號名稱")
                return
            import uuid
            acc_id = str(uuid.uuid4())
            self._ig_accounts.append({
                "account_id": acc_id,
                "username": username,
                "nickname": nickname_var.get().strip() or username,
                "has_cookie": False,
                "added_at": datetime.now().isoformat(),
            })
            _save_ig_accounts(self._ig_accounts)
            self._refresh_ig_list()
            dlg.destroy()
            messagebox.showinfo("成功", f"已新增 IG 帳號: {username}")

        create_styled_button(dlg, "儲存", save, "success").pack(pady=12)

    def _delete_ig_account(self):
        sel = self._ig_list.curselection()
        if not sel:
            messagebox.showwarning("警告", "請先選擇要刪除的帳號")
            return
        acc = self._ig_accounts[sel[0]]
        conf = messagebox.askyesno("確認", f"確定要刪除 {acc.get('username')} 嗎？")
        if conf:
            self._ig_accounts.pop(sel[0])
            _save_ig_accounts(self._ig_accounts)
            self._refresh_ig_list()

    def _import_ig_cookie(self):
        sel = self._ig_list.curselection()
        if not sel:
            messagebox.showwarning("警告", "請先選擇要匯入 Cookie 的帳號")
            return

        acc = self._ig_accounts[sel[0]]

        dlg = tk.Toplevel(self)
        dlg.title(f"匯入 IG Cookie — {acc.get('username')}")
        dlg.geometry("600x450")
        dlg.transient(self)
        dlg.grab_set()

        ttk.Label(dlg, text="請貼上 Instagram Cookie (JSON 格式):", font=("Microsoft JhengHei", 10)).pack(padx=12, pady=(12, 4))
        ttk.Label(dlg, text="可用 EditThisCookie 或 Cookie-Editor 擴充功能匯出", font=("Microsoft JhengHei", 8, "italic")).pack(padx=12)

        cookie_text = tk.Text(dlg, height=15, wrap=tk.WORD, font=("Consolas", 9))
        cookie_text.pack(fill=tk.BOTH, expand=True, padx=12, pady=8)

        status_var = tk.StringVar()
        ttk.Label(dlg, textvariable=status_var).pack(padx=12, pady=4)

        def import_cookie():
            raw = cookie_text.get("1.0", tk.END).strip()
            if not raw:
                return
            try:
                json.loads(raw)  # validate
                cookie_path = save_ig_cookie(acc["account_id"], raw)
                acc["has_cookie"] = True
                _save_ig_accounts(self._ig_accounts)
                self._refresh_ig_list()
                status_var.set("✅ Cookie 已成功匯入！")
                dlg.after(1500, dlg.destroy)
            except json.JSONDecodeError:
                status_var.set("❌ JSON 格式錯誤，請檢查內容")

        create_styled_button(dlg, "匯入 Cookie", import_cookie, "success").pack(pady=10)

    def _get_selected_ig_account(self) -> dict | None:
        """取得目前選中的 IG 帳號"""
        sel = self._ig_list.curselection()
        if not sel:
            return None
        return self._ig_accounts[sel[0]]

    # ════════════════════════════════════════════
    #  發文頁籤
    # ════════════════════════════════════════════

    def _build_post_tab(self):
        tab = ttk.Frame(self._nb)
        self._nb.add(tab, text="📝 發文")

        # ─ 帳號顯示 ─
        row = ttk.Frame(tab)
        row.pack(fill=tk.X, padx=12, pady=(12, 4))
        create_styled_label(row, "使用 IG 帳號:").pack(side=tk.LEFT)
        self._ig_display_var = tk.StringVar(value="(請先在 IG 帳號頁籤選擇帳號)")
        self._ig_display_label = ttk.Label(row, textvariable=self._ig_display_var)
        self._ig_display_label.pack(side=tk.LEFT, padx=8)

        # ─ 文案 ─
        create_styled_label(tab, "貼文內容 (500 字內):").pack(anchor=tk.W, padx=12, pady=(8, 2))
        self._threads_text = tk.Text(tab, height=5, wrap=tk.WORD, font=("Microsoft JhengHei", 10))
        self._threads_text.pack(fill=tk.X, padx=12, pady=(0, 6))

        # ─ 圖片 ─
        img_frame = ttk.Frame(tab)
        img_frame.pack(fill=tk.X, padx=12, pady=(4, 2))
        create_styled_label(img_frame, "圖片 (可選):").pack(side=tk.LEFT)
        self._img_count_lbl = create_styled_label(img_frame, "0 張")
        self._img_count_lbl.pack(side=tk.LEFT, padx=8)
        create_styled_button(img_frame, "選擇圖片", self._select_images, "secondary").pack(side=tk.LEFT, padx=4)
        create_styled_button(img_frame, "清除", self._clear_images, "danger").pack(side=tk.LEFT)

        # ─ 發文按鈕 ─
        btn_row = ttk.Frame(tab)
        btn_row.pack(fill=tk.X, padx=12, pady=(12, 12))
        create_styled_button(btn_row, "🚀 發文到 Threads", self._post_thread_now, "success").pack(side=tk.LEFT)
        self._post_status = create_styled_label(btn_row, "")
        self._post_status.pack(side=tk.LEFT, padx=12)

        # 切換分頁時更新帳號顯示
        self._nb.bind("<<NotebookTabChanged>>", self._on_tab_changed)

    def _on_tab_changed(self, event=None):
        """切換分頁時更新 IG 帳號顯示"""
        acc = self._get_selected_ig_account()
        if acc:
            self._ig_display_var.set(f"{acc.get('username', '')} ({acc.get('nickname', '')})")
        else:
            self._ig_display_var.set("(請先在「IG 帳號」頁籤選擇帳號)")

    def _select_images(self):
        paths = filedialog.askopenfilenames(
            title="選擇圖片",
            filetypes=[("Image files", "*.jpg *.jpeg *.png *.webp")]
        )
        if paths:
            self.selected_images = list(paths)
            self._img_count_lbl.config(text=f"{len(self.selected_images)} 張")

    def _clear_images(self):
        self.selected_images = []
        self._img_count_lbl.config(text="0 張")

    def _post_thread_now(self):
        content = self._threads_text.get("1.0", tk.END).strip()
        if not content:
            messagebox.showwarning("警告", "請輸入貼文內容")
            return

        acc = self._get_selected_ig_account()
        if not acc:
            messagebox.showwarning("警告", "請先在「IG 帳號」頁籤選擇帳號")
            return

        if not acc.get("has_cookie"):
            messagebox.showwarning("警告", "此帳號尚未匯入 Cookie\n請在「IG 帳號」頁籤中匯入")
            return

        if not self.engine:
            messagebox.showerror("錯誤", "發文引擎尚未啟動")
            return

        self._post_status.config(text="發文中...")

        # 使用 IG 帳號 ID 提交（engine 會用 ig_cookies_ 前綴讀取）
        self.engine.threads_post_now(
            account_id=acc["account_id"],
            content=content,
            image_paths=self.selected_images if self.selected_images else None,
            callback=lambda r: self.after(0, self._on_post_done, r),
            error_callback=lambda e: self.after(0, self._on_post_error, e),
        )

    def _on_post_done(self, result):
        if result.get("success"):
            self._post_status.config(text="✅ 發文成功!")
            if result.get("post_url"):
                log("THREADS", "ui", result["post_url"], "🔗")
        else:
            self._post_status.config(text=f"❌ {result.get('error', '失敗')}")

    def _on_post_error(self, error):
        self._post_status.config(text=f"❌ {error.get('error', '失敗')}")

    # ════════════════════════════════════════════
    #  海巡回覆頁籤
    # ════════════════════════════════════════════

    def _build_reply_tab(self):
        tab = ttk.Frame(self._nb)
        self._nb.add(tab, text="🔍 海巡回覆")

        # ─ 關鍵字 ─
        kw_frame = ttk.LabelFrame(tab, text="搜尋關鍵字 (逗號分隔)")
        kw_frame.pack(fill=tk.X, padx=12, pady=(12, 6))
        self._kw_var = tk.StringVar(value="創業, 電商, 副業, 行銷, 自媒體, 網路賺錢")
        create_styled_entry(kw_frame, textvariable=self._kw_var).pack(fill=tk.X, padx=8, pady=8)

        # ─ 回覆設定 ─
        set_frame = ttk.LabelFrame(tab, text="回覆設定")
        set_frame.pack(fill=tk.X, padx=12, pady=6)

        r1 = ttk.Frame(set_frame)
        r1.pack(fill=tk.X, padx=8, pady=4)
        create_styled_label(r1, "每次最多回覆:").pack(side=tk.LEFT)
        self._max_replies_var = tk.StringVar(value="10")
        ttk.Spinbox(r1, from_=1, to=50, textvariable=self._max_replies_var, width=5).pack(side=tk.LEFT, padx=8)

        r2 = ttk.Frame(set_frame)
        r2.pack(fill=tk.X, padx=8, pady=4)
        create_styled_label(r2, "回覆間隔 (秒):").pack(side=tk.LEFT)
        self._delay_min = tk.StringVar(value="30")
        ttk.Spinbox(r2, from_=10, to=600, textvariable=self._delay_min, width=5).pack(side=tk.LEFT, padx=4)
        create_styled_label(r2, "~").pack(side=tk.LEFT)
        self._delay_max = tk.StringVar(value="120")
        ttk.Spinbox(r2, from_=30, to=900, textvariable=self._delay_max, width=5).pack(side=tk.LEFT, padx=4)

        # ─ 模板 ─
        tmpl_frame = ttk.LabelFrame(tab, text="回覆模板庫")
        tmpl_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=6)

        tmpl_toolbar = ttk.Frame(tmpl_frame)
        tmpl_toolbar.pack(fill=tk.X, padx=8, pady=4)
        create_styled_button(tmpl_toolbar, "+ 新增", self._add_template, "success").pack(side=tk.LEFT, padx=2)
        create_styled_button(tmpl_toolbar, "− 刪除選取", self._del_template, "danger").pack(side=tk.LEFT, padx=2)

        list_frame = ttk.Frame(tmpl_frame)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        self._tmpl_list = tk.Listbox(list_frame, height=4, font=("Microsoft JhengHei", 9))
        tmpl_scroll = ttk.Scrollbar(list_frame)
        self._tmpl_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tmpl_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self._tmpl_list.config(yscrollcommand=tmpl_scroll.set)
        tmpl_scroll.config(command=self._tmpl_list.yview)
        self._load_templates()

        # ─ 操作按鈕 ─
        btn_row = ttk.Frame(tab)
        btn_row.pack(fill=tk.X, padx=12, pady=(8, 4))
        create_styled_button(btn_row, "🔍 掃描預覽", self._scan_only, "info").pack(side=tk.LEFT, padx=4)
        create_styled_button(btn_row, "💬 開始海巡回覆", self._start_reply, "success").pack(side=tk.LEFT, padx=4)
        self._reply_status = create_styled_label(btn_row, "")
        self._reply_status.pack(side=tk.LEFT, padx=12)

        # ─ 結果 ─
        result_frame = ttk.LabelFrame(tab, text="執行結果")
        result_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=(4, 12))
        self._result_text = tk.Text(result_frame, height=6, wrap=tk.WORD, font=("Microsoft JhengHei", 9))
        self._result_text.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

    def _load_templates(self):
        try:
            from core.threads_replier import ThreadsReplier
            r = ThreadsReplier()
            self._tmpl_list.delete(0, tk.END)
            for t in r.list_templates():
                self._tmpl_list.insert(tk.END, t[:60])
        except Exception:
            pass

    def _add_template(self):
        dlg = tk.Toplevel(self)
        dlg.title("新增回覆模板")
        dlg.geometry("400x150")
        ttk.Label(dlg, text="回覆文字:").pack(padx=12, pady=(12, 4))
        entry = tk.Text(dlg, height=4, wrap=tk.WORD)
        entry.pack(fill=tk.X, padx=12, pady=4)

        def save():
            txt = entry.get("1.0", tk.END).strip()
            if txt:
                from core.threads_replier import ThreadsReplier
                ThreadsReplier().add_template(txt)
                self._load_templates()
            dlg.destroy()
        create_styled_button(dlg, "儲存", save, "success").pack(pady=8)

    def _del_template(self):
        sel = self._tmpl_list.curselection()
        if sel:
            from core.threads_replier import ThreadsReplier
            ThreadsReplier().remove_template(sel[0])
            self._load_templates()

    def _get_keywords(self) -> list[str]:
        return [k.strip() for k in self._kw_var.get().split(",") if k.strip()]

    def _scan_only(self):
        self._do_reply(dry_run=True)

    def _start_reply(self):
        self._do_reply(dry_run=False)

    def _do_reply(self, dry_run=False):
        acc = self._get_selected_ig_account()
        if not acc:
            messagebox.showwarning("警告", "請先在「IG 帳號」頁籤選擇帳號")
            return
        if not acc.get("has_cookie"):
            messagebox.showwarning("警告", "此帳號尚未匯入 Cookie")
            return
        if not self.engine:
            messagebox.showerror("錯誤", "引擎尚未啟動")
            return

        keywords = self._get_keywords()
        if not keywords:
            messagebox.showwarning("警告", "請輸入至少一個關鍵字")
            return

        label = "掃描中..." if dry_run else "海巡回覆中..."
        self._reply_status.config(text=label)

        self.engine.threads_reply_now(
            account_id=acc["account_id"],
            keywords=keywords,
            max_replies=int(self._max_replies_var.get()),
            dry_run=dry_run,
            callback=lambda r: self.after(0, self._on_reply_done, r, dry_run),
            error_callback=lambda e: self.after(0, self._on_reply_error, e),
        )

    def _on_reply_done(self, result, dry_run):
        action = "掃描" if dry_run else "回覆"
        self._reply_status.config(text=f"✅ {action}完成")
        self._result_text.delete("1.0", tk.END)
        self._result_text.insert(tk.END, f"=== {action}結果 ===\n")
        self._result_text.insert(tk.END, f"掃描: {result.get('scanned', 0)} | 相關: {result.get('relevant', 0)} | 回覆: {result.get('replied', 0)}\n")
        self._result_text.insert(tk.END, f"跳過: {result.get('skipped', 0)}\n\n")
        for r in result.get("results", []):
            s = "✅" if r.get("success", True) else "❌"
            self._result_text.insert(tk.END, f"{s} {r.get('text', '')[:60]}\n")

    def _on_reply_error(self, error):
        self._reply_status.config(text=f"❌ {error.get('error', '失敗')}")
