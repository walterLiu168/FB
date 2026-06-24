"""多帳號管理面板"""
import tkinter as tk
from tkinter import ttk, messagebox
import uuid

from core.account import Account, AccountManager
from gui.dark_theme import (
    create_styled_button, create_styled_entry,
    create_styled_label, create_styled_frame
)


class AccountManagerPanel(ttk.Frame):
    """帳號管理界面"""

    def __init__(self, parent, account_manager: AccountManager, on_change=None, **kwargs):
        super().__init__(parent, **kwargs)
        self.manager = account_manager
        self._on_change = on_change  # 帳號異動時通知外層刷新
        self._build_ui()
        self._refresh_list()

    def _build_ui(self):
        # 左側 — 帳號列表
        left_frame = create_styled_frame(self, padding=10)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        create_styled_label(left_frame, text="帳號列表", font=("Arial", 14)).pack(anchor=tk.W, pady=(0, 10))

        list_frame = create_styled_frame(left_frame)
        list_frame.pack(fill=tk.BOTH, expand=True)

        self.tree = ttk.Treeview(
            list_frame,
            columns=("email", "nickname", "status"),
            show="headings",
            height=15,
        )
        self.tree.heading("email", text="Email")
        self.tree.heading("nickname", text="暱稱")
        self.tree.heading("status", text="狀態")
        self.tree.column("email", width=200)
        self.tree.column("nickname", width=150)
        self.tree.column("status", width=80)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.tree.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.configure(yscrollcommand=scrollbar.set)

        # 右側 — 按鈕
        right_frame = create_styled_frame(self, padding=10)
        right_frame.pack(side=tk.RIGHT, fill=tk.Y)

        create_styled_button(right_frame, text="新增帳號", command=self._add_account, bootstyle="success").pack(pady=5, fill=tk.X)
        create_styled_button(right_frame, text="刪除帳號", command=self._remove_account, bootstyle="danger").pack(pady=5, fill=tk.X)
        create_styled_button(right_frame, text="啟用/停用", command=self._toggle_active, bootstyle="warning").pack(pady=5, fill=tk.X)
        create_styled_button(right_frame, text="匯入 Cookie", command=self._import_cookie, bootstyle="info").pack(pady=5, fill=tk.X)

    def _add_account(self):
        dialog = tk.Toplevel(self)
        dialog.title("新增帳號")
        dialog.geometry("400x250")
        dialog.transient(self)
        dialog.grab_set()

        create_styled_label(dialog, text="Email:").pack(pady=(10, 0))
        email_entry = create_styled_entry(dialog, width=40)
        email_entry.pack(pady=5)

        create_styled_label(dialog, text="密碼 (選填):").pack(pady=(10, 0))
        pwd_entry = create_styled_entry(dialog, width=40, show="*")
        pwd_entry.pack(pady=5)

        create_styled_label(dialog, text="暱稱 (選填):").pack(pady=(10, 0))
        nickname_entry = create_styled_entry(dialog, width=40)
        nickname_entry.pack(pady=5)

        def save():
            email = email_entry.get().strip()
            if not email:
                messagebox.showwarning("警告", "Email 不可為空")
                return
            acc = Account(
                account_id=str(uuid.uuid4()),
                email=email,
                password=pwd_entry.get(),
                nickname=nickname_entry.get() or email,
            )
            self.manager.add(acc)
            self._refresh_list()
            self._notify_change()
            dialog.destroy()

        create_styled_button(dialog, text="儲存", command=save, bootstyle="success").pack(pady=15)

    def _remove_account(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("警告", "請先選擇一個帳號")
            return
        item = self.tree.item(selected[0])
        email = item["values"][0]
        if messagebox.askyesno("確認", f"確定刪除 {email}？"):
            for acc in self.manager.list_all():
                if acc.email == email:
                    self.manager.remove(acc.account_id)
                    self._refresh_list()
                    self._notify_change()
                    break

    def _toggle_active(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("警告", "請先選擇一個帳號")
            return
        item = self.tree.item(selected[0])
        email = item["values"][0]
        for acc in self.manager.list_all():
            if acc.email == email:
                self.manager.set_active(acc.account_id, not acc.is_active)
                self._refresh_list()
                self._notify_change()
                break

    def _import_cookie(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("警告", "請先選擇一個帳號")
            return
        item = self.tree.item(selected[0])
        email = item["values"][0]

        dialog = tk.Toplevel(self)
        dialog.title("匯入 Cookie")
        dialog.geometry("500x300")
        dialog.transient(self)
        dialog.grab_set()

        create_styled_label(dialog, text="貼上 FB Cookie JSON (從瀏覽器匯出):").pack(pady=(10, 0))
        text_widget = tk.Text(dialog, height=12, bg="#2b2b2b", fg="#ffffff", insertbackground="white")
        text_widget.pack(padx=10, pady=5, fill=tk.BOTH, expand=True)

        def save_cookie():
            cookie_str = text_widget.get("1.0", tk.END).strip()
            if not cookie_str:
                messagebox.showwarning("警告", "請貼上 Cookie JSON")
                return
            for acc in self.manager.list_all():
                if acc.email == email:
                    if self.manager.import_cookie(acc.account_id, cookie_str):
                        messagebox.showinfo("成功", "Cookie 匯入成功")
                    else:
                        messagebox.showerror("錯誤", "Cookie 格式錯誤")
                    dialog.destroy()
                    break

        create_styled_button(dialog, text="匯入", command=save_cookie, bootstyle="success").pack(pady=10)

    def _notify_change(self):
        """通知外層帳號有異動"""
        if self._on_change:
            self._on_change()

    def _refresh_list(self):
        for row in self.tree.get_children():
            self.tree.delete(row)
        for acc in self.manager.list_all():
            status = "✅ 啟用" if acc.is_active else "❌ 停用"
            self.tree.insert("", tk.END, values=(acc.email, acc.nickname, status))