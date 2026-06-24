"""Threads 操作面板 — 發文 + 海巡回覆"""
import json
import os
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from gui.dark_theme import (
    create_styled_button, create_styled_entry,
    create_styled_label, create_styled_frame
)
from utils.logger import log


class ThreadsPanel(ttk.Frame):
    """Threads.net 發文 + 自動回覆面板"""

    def __init__(self, parent, account_ids=None, account_map=None,
                 engine=None, scheduler=None, **kwargs):
        super().__init__(parent, **kwargs)
        self.account_map = account_map or {}
        self.account_ids = list(self.account_map.values()) or (account_ids or [])
        self.engine = engine
        self.scheduler = scheduler
        self.selected_images = []
        self._replier = None

        # Notebook 分頁: Post | Reply
        self._nb = ttk.Notebook(self)
        self._nb.pack(fill=tk.BOTH, expand=True)

        self._build_post_tab()
        self._build_reply_tab()

    # ════════════════════════════════════════════
    #  發文頁籤
    # ════════════════════════════════════════════

    def _build_post_tab(self):
        tab = ttk.Frame(self._nb)
        self._nb.add(tab, text="📝 Threads 發文")

        # ─ 帳號選擇 ─
        row = ttk.Frame(tab)
        row.pack(fill=tk.X, padx=12, pady=(12, 4))
        create_styled_label(row, "選擇帳號:").pack(side=tk.LEFT)
        self._threads_account_var = tk.StringVar()
        accts = list(self.account_map.keys())
        self._threads_account_cb = ttk.Combobox(
            row, textvariable=self._threads_account_var, values=accts,
            state="readonly", width=30
        )
        self._threads_account_cb.pack(side=tk.LEFT, padx=8)
        if accts:
            self._threads_account_cb.current(0)

        # ─ 文案 ─
        lbl = create_styled_label(tab, "貼文內容 (500 字內):")
        lbl.pack(anchor=tk.W, padx=12, pady=(8, 2))
        self._threads_text = tk.Text(tab, height=5, wrap=tk.WORD, font=("Microsoft JhengHei", 10))
        self._threads_text.pack(fill=tk.X, padx=12, pady=(0, 6))

        # ─ 圖片 ─
        img_frame = ttk.Frame(tab)
        img_frame.pack(fill=tk.X, padx=12, pady=(4, 2))
        create_styled_label(img_frame, "圖片 (可選):").pack(side=tk.LEFT)
        self._img_count_lbl = create_styled_label(img_frame, "0 張")
        self._img_count_lbl.pack(side=tk.LEFT, padx=8)
        btn_sel = create_styled_button(img_frame, "選擇圖片", self._select_images, "secondary")
        btn_sel.pack(side=tk.LEFT, padx=4)
        btn_clr = create_styled_button(img_frame, "清除", self._clear_images, "danger")
        btn_clr.pack(side=tk.LEFT)

        # ─ 進階選項 ─
        opts = ttk.Frame(tab)
        opts.pack(fill=tk.X, padx=12, pady=(10, 4))
        create_styled_label(opts, "排程發文 (HH:MM，留空為立即發文):").pack(side=tk.LEFT)
        self._schedule_time_var = tk.StringVar()
        sch_entry = create_styled_entry(opts, textvariable=self._schedule_time_var, width=8)
        sch_entry.pack(side=tk.LEFT, padx=8)

        # ─ 發文按鈕 ─
        btn_row = ttk.Frame(tab)
        btn_row.pack(fill=tk.X, padx=12, pady=(12, 12))
        btn = create_styled_button(btn_row, "🚀 立即發文到 Threads", self._post_thread_now, "success")
        btn.pack(side=tk.LEFT)
        self._post_status = create_styled_label(btn_row, "")
        self._post_status.pack(side=tk.LEFT, padx=12)

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

        acct_name = self._threads_account_var.get()
        if not acct_name:
            messagebox.showwarning("警告", "請先選擇帳號")
            return

        account_id = self.account_map.get(acct_name)
        if not account_id:
            messagebox.showerror("錯誤", "找不到選擇的帳號")
            return

        schedule_time = self._schedule_time_var.get().strip()
        if schedule_time:
            self._schedule_thread(content, schedule_time)
            return

        if not self.engine:
            messagebox.showerror("錯誤", "發文引擎尚未啟動")
            return

        self._post_status.config(text="發文中...")
        self.engine.threads_post_now(
            account_id=account_id,
            content=content,
            image_paths=self.selected_images if self.selected_images else None,
            callback=lambda r: self.after(0, self._on_post_done, r),
            error_callback=lambda e: self.after(0, self._on_post_error, e),
        )

    def _schedule_thread(self, content, time_str):
        if not self.scheduler:
            messagebox.showerror("錯誤", "排程器尚未啟動")
            return
        try:
            h, m = map(int, time_str.split(":"))
            self.scheduler.schedule_daily(
                name=f"Threads: {content[:20]}...",
                hour=h, minute=m,
                callback=lambda: log("THREADS", "schedule", "排程觸發", "⏰"),
            )
            messagebox.showinfo("成功", f"已排程於每日 {time_str} 發文")
        except Exception as e:
            messagebox.showerror("錯誤", f"時間格式錯誤: {e}")

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

        # ─ 關鍵字設定 ─
        kw_frame = ttk.LabelFrame(tab, text="搜尋關鍵字 (逗號分隔)")
        kw_frame.pack(fill=tk.X, padx=12, pady=(12, 6))
        self._kw_var = tk.StringVar(value="創業, 電商, 副業, 行銷, 自媒體, 網路賺錢")
        kw_entry = create_styled_entry(kw_frame, textvariable=self._kw_var)
        kw_entry.pack(fill=tk.X, padx=8, pady=8)

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

        # ─ 回覆模板 ─
        tmpl_frame = ttk.LabelFrame(tab, text="回覆模板庫")
        tmpl_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=6)

        tmpl_toolbar = ttk.Frame(tmpl_frame)
        tmpl_toolbar.pack(fill=tk.X, padx=8, pady=4)
        btn_add = create_styled_button(tmpl_toolbar, "+ 新增", self._add_template, "success")
        btn_add.pack(side=tk.LEFT, padx=2)
        btn_del = create_styled_button(tmpl_toolbar, "− 刪除選取", self._del_template, "danger")
        btn_del.pack(side=tk.LEFT, padx=2)

        list_frame = ttk.Frame(tmpl_frame)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        self._tmpl_list = tk.Listbox(list_frame, height=6, font=("Microsoft JhengHei", 9))
        scrollbar = ttk.Scrollbar(list_frame)
        self._tmpl_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._tmpl_list.config(yscrollcommand=scrollbar.set)
        scrollbar.config(command=self._tmpl_list.yview)

        # 載入模板
        self._load_templates()

        # ─ 操作按鈕 ─
        btn_row = ttk.Frame(tab)
        btn_row.pack(fill=tk.X, padx=12, pady=(8, 12))
        btn_scan = create_styled_button(btn_row, "🔍 掃描 (僅預覽)", self._scan_only, "info")
        btn_scan.pack(side=tk.LEFT, padx=4)
        btn_reply = create_styled_button(btn_row, "💬 開始海巡回覆", self._start_reply, "success")
        btn_reply.pack(side=tk.LEFT, padx=4)
        self._reply_status = create_styled_label(btn_row, "")
        self._reply_status.pack(side=tk.LEFT, padx=12)

        # ─ 結果顯示 ─
        result_frame = ttk.LabelFrame(tab, text="執行結果")
        result_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))
        self._result_text = tk.Text(result_frame, height=8, wrap=tk.WORD, font=("Microsoft JhengHei", 9))
        self._result_text.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

    def _load_templates(self):
        try:
            from core.threads_replier import ThreadsReplier
            r = ThreadsReplier()
            templates = r.list_templates()
            self._tmpl_list.delete(0, tk.END)
            for t in templates:
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
                r = ThreadsReplier()
                r.add_template(txt)
                self._load_templates()
            dlg.destroy()

        ttk.Button(dlg, text="儲存", command=save).pack(pady=8)

    def _del_template(self):
        sel = self._tmpl_list.curselection()
        if sel:
            from core.threads_replier import ThreadsReplier
            r = ThreadsReplier()
            r.remove_template(sel[0])
            self._load_templates()

    def _get_keywords(self) -> list[str]:
        raw = self._kw_var.get()
        return [k.strip() for k in raw.split(",") if k.strip()]

    def _scan_only(self):
        self._do_reply(dry_run=True)

    def _start_reply(self):
        self._do_reply(dry_run=False)

    def _do_reply(self, dry_run=False):
        acct_name = self._threads_account_var.get()
        if not acct_name:
            messagebox.showwarning("警告", "請先選擇帳號")
            return

        account_id = self.account_map.get(acct_name)
        if not account_id:
            messagebox.showerror("錯誤", "找不到帳號")
            return

        if not self.engine:
            messagebox.showerror("錯誤", "引擎尚未啟動")
            return

        keywords = self._get_keywords()
        if not keywords:
            messagebox.showwarning("警告", "請輸入至少一個關鍵字")
            return

        max_replies = int(self._max_replies_var.get())
        label = "掃描中..." if dry_run else "海巡回覆中..."
        self._reply_status.config(text=label)

        self.engine.threads_reply_now(
            account_id=account_id,
            keywords=keywords,
            max_replies=max_replies,
            dry_run=dry_run,
            callback=lambda r: self.after(0, self._on_reply_done, r, dry_run),
            error_callback=lambda e: self.after(0, self._on_reply_error, e),
        )

    def _on_reply_done(self, result, dry_run):
        action = "掃描" if dry_run else "回覆"
        self._reply_status.config(text=f"✅ {action}完成")

        # 更新結果顯示
        self._result_text.delete("1.0", tk.END)
        self._result_text.insert(tk.END, f"=== {action}結果 ===\n\n")
        self._result_text.insert(tk.END, f"掃描總數: {result.get('scanned', 0)}\n")
        self._result_text.insert(tk.END, f"相關貼文: {result.get('relevant', 0)}\n")
        self._result_text.insert(tk.END, f"實際回覆: {result.get('replied', 0)}\n")
        self._result_text.insert(tk.END, f"已跳過:   {result.get('skipped', 0)}\n")
        self._result_text.insert(tk.END, "\n--- 詳細記錄 ---\n\n")

        for r in result.get("results", []):
            status = "✅" if r.get("success", True) else "❌"
            txt = r.get("text", "")[:80]
            self._result_text.insert(tk.END, f"{status} {txt}\n")
            if r.get("reply"):
                self._result_text.insert(tk.END, f"   ↳ 回覆: {r['reply'][:60]}...\n")
            self._result_text.insert(tk.END, "\n")

    def _on_reply_error(self, error):
        self._reply_status.config(text=f"❌ {error.get('error', '失敗')}")
