"""排程設定界面"""
import tkinter as tk
from tkinter import ttk, messagebox
import uuid

from core.scheduler import ScheduleJob, Scheduler
from gui.dark_theme import (
    create_styled_button, create_styled_entry,
    create_styled_label, create_styled_frame
)


class SchedulerPanel(ttk.Frame):
    """排程設定面板"""

    def __init__(self, parent, scheduler: Scheduler, account_ids: list[str], **kwargs):
        super().__init__(parent, **kwargs)
        self.scheduler = scheduler
        self.account_ids = account_ids
        self._build_ui()
        self._refresh_list()

    def _build_ui(self):
        # 頂部 — 新增排程表單
        form_frame = create_styled_frame(self, padding=10)
        form_frame.pack(fill=tk.X)

        create_styled_label(form_frame, text="新增排程任務", font=("Arial", 14)).pack(anchor=tk.W)

        row1 = create_styled_frame(form_frame)
        row1.pack(fill=tk.X, pady=5)

        create_styled_label(row1, text="帳號:").pack(side=tk.LEFT)
        self.account_var = tk.StringVar(value=self.account_ids[0] if self.account_ids else "")
        self.account_combo = ttk.Combobox(
            row1, textvariable=self.account_var,
            values=self.account_ids, state="readonly", width=30
        )
        self.account_combo.pack(side=tk.LEFT, padx=5)

        create_styled_label(row1, text="任務類型:").pack(side=tk.LEFT, padx=(20, 0))
        self.type_var = tk.StringVar(value="post")
        type_combo = ttk.Combobox(
            row1, textvariable=self.type_var,
            values=["post", "nurture", "delete", "interact"],
            state="readonly", width=15
        )
        type_combo.pack(side=tk.LEFT, padx=5)

        row2 = create_styled_frame(form_frame)
        row2.pack(fill=tk.X, pady=5)

        create_styled_label(row2, text="排程時間 (Cron 格式, 分 時 日 月 週):").pack(side=tk.LEFT)
        self.cron_entry = create_styled_entry(row2, width=25)
        self.cron_entry.insert(0, "0 9 * * 1-5")
        self.cron_entry.pack(side=tk.LEFT, padx=5)

        create_styled_label(row2, text="e.g. 0 9,14,20 * * 1-7").pack(side=tk.LEFT, padx=5)

        create_styled_button(form_frame, text="新增排程", command=self._add_schedule, bootstyle="success").pack(pady=10)

        # 下半部 — 排程列表
        list_frame = create_styled_frame(self, padding=10)
        list_frame.pack(fill=tk.BOTH, expand=True)

        create_styled_label(list_frame, text="現有排程", font=("Arial", 14)).pack(anchor=tk.W, pady=(0, 10))

        columns = ("帳號", "類型", "Cron", "狀態")
        self.tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=10)
        for col in columns:
            self.tree.heading(col, text=col)
        self.tree.column("帳號", width=150)
        self.tree.column("類型", width=100)
        self.tree.column("Cron", width=200)
        self.tree.column("狀態", width=80)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.tree.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.configure(yscrollcommand=scrollbar.set)

        # 操作按鈕
        btn_frame = create_styled_frame(self, padding=10)
        btn_frame.pack(fill=tk.X)
        create_styled_button(btn_frame, text="暫停", command=self._pause_job, bootstyle="warning").pack(side=tk.LEFT, padx=5)
        create_styled_button(btn_frame, text="恢復", command=self._resume_job, bootstyle="info").pack(side=tk.LEFT, padx=5)
        create_styled_button(btn_frame, text="刪除", command=self._remove_job, bootstyle="danger").pack(side=tk.LEFT, padx=5)

    def _refresh_list(self):
        for row in self.tree.get_children():
            self.tree.delete(row)
        for job in self.scheduler.get_jobs():
            status = "✅ 啟用" if job.enabled else "❌ 暫停"
            self.tree.insert("", tk.END, values=(
                job.account_id, job.job_type, job.cron_expr, status
            ))

    def _add_schedule(self):
        account_id = self.account_var.get()
        job_type = self.type_var.get()
        cron_expr = self.cron_entry.get().strip()
        if not account_id or not cron_expr:
            messagebox.showwarning("警告", "請填寫所有欄位")
            return
        parts = cron_expr.split()
        if len(parts) != 5:
            messagebox.showwarning("警告", "Cron 格式錯誤，請使用「分 時 日 月 週」5 個欄位")
            return
        job = ScheduleJob(
            job_id=str(uuid.uuid4()),
            account_id=account_id,
            job_type=job_type,
            cron_expr=cron_expr,
        )
        if self.scheduler.add_job(job):
            self._refresh_list()
            messagebox.showinfo("成功", "排程已新增")
        else:
            messagebox.showerror("錯誤", "新增排程失敗，請檢查 Cron 格式")

    def _pause_job(self):
        selected = self.tree.selection()
        if not selected:
            return
        values = self.tree.item(selected[0])["values"]
        for job in self.scheduler.get_jobs():
            if f"{job.account_id}/{job.job_type}/{job.cron_expr}" == f"{values[0]}/{values[1]}/{values[2]}":
                self.scheduler.pause_job(job.job_id)
                self._refresh_list()
                break

    def _resume_job(self):
        selected = self.tree.selection()
        if not selected:
            return
        values = self.tree.item(selected[0])["values"]
        for job in self.scheduler.get_jobs():
            if f"{job.account_id}/{job.job_type}/{job.cron_expr}" == f"{values[0]}/{values[1]}/{values[2]}":
                self.scheduler.resume_job(job.job_id)
                self._refresh_list()
                break

    def _remove_job(self):
        selected = self.tree.selection()
        if not selected:
            return
        values = self.tree.item(selected[0])["values"]
        if messagebox.askyesno("確認", f"刪除此排程？"):
            for job in self.scheduler.get_jobs():
                if f"{job.account_id}/{job.job_type}/{job.cron_expr}" == f"{values[0]}/{values[1]}/{values[2]}":
                    self.scheduler.remove_job(job.job_id)
                    self._refresh_list()
                    break
