"""TikTok 帳號設定對話框 — 管理帳號，透過瀏覽器登入儲存設定檔"""
import threading
import tkinter as tk
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from tkinter import messagebox

from core import tiktok_uploader


class TikTokSettingsDialog(ttk.Toplevel):
    """管理 TikTok 帳號（暱稱 + 瀏覽器登入狀態）"""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("TikTok 設定")
        self.geometry("560x450")
        self.transient(parent)
        self.grab_set()

        self._build_ui()
        self._refresh_list()

    def _build_ui(self):
        frame = ttk.Frame(self, padding=15)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="TikTok 帳號管理", font=("Arial", 14)).pack(anchor=tk.W)
        ttk.Label(
            frame,
            text="使用瀏覽器設定檔登入，第一次手動登入後自動保存狀態。\n"
                 "之後上傳影片不需重新登入。",
            font=("Arial", 8), bootstyle="secondary", justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(2, 10))

        # ── 現有帳號清單 ──
        lf1 = ttk.LabelFrame(frame, text="已儲存帳號")
        lf1.pack(fill=tk.BOTH, expand=True, pady=5)
        list_inner = ttk.Frame(lf1, padding=8)
        list_inner.pack(fill=tk.BOTH, expand=True)

        self.tree = ttk.Treeview(
            list_inner, columns=("status",), show="tree headings", height=5
        )
        self.tree.heading("#0", text="暱稱")
        self.tree.heading("status", text="登入狀態")
        self.tree.column("#0", width=180)
        self.tree.column("status", width=260)
        self.tree.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)

        btn_frame = ttk.Frame(list_inner)
        btn_frame.pack(side=tk.RIGHT, padx=(8, 0), fill=tk.Y)

        ttk.Button(
            btn_frame, text="🔑 登入", command=self._on_login, bootstyle="info"
        ).pack(pady=2, fill=tk.X)
        ttk.Button(
            btn_frame, text="移除選取", command=self._on_remove, bootstyle="danger-outline"
        ).pack(pady=2, fill=tk.X)

        # ── 新增帳號 ──
        lf2 = ttk.LabelFrame(frame, text="新增帳號")
        lf2.pack(fill=tk.X, pady=5)
        add_frame = ttk.Frame(lf2, padding=8)
        add_frame.pack(fill=tk.X)
        add_frame.columnconfigure(1, weight=1)

        ttk.Label(add_frame, text="暱稱:").grid(row=0, column=0, sticky=tk.W, pady=3)
        self.nick_var = tk.StringVar()
        ttk.Entry(add_frame, textvariable=self.nick_var).grid(row=0, column=1, sticky=tk.EW, pady=3, padx=(5, 0))

        ttk.Label(
            add_frame, text="新增後點擊「🔑 登入」在瀏覽器中手動登入 TikTok",
            font=("Arial", 8), bootstyle="secondary",
        ).grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=(4, 0))

        ttk.Button(
            add_frame, text="新增帳號", command=self._on_save, bootstyle="success"
        ).grid(row=2, column=1, sticky=tk.E, pady=8)

        ttk.Button(frame, text="關閉", command=self.destroy, bootstyle="secondary").pack(pady=5)

    def _refresh_list(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for acc in tiktok_uploader.list_accounts():
            status_text = "✅ 已登入" if acc.get("logged_in") else "❌ 未登入"
            self.tree.insert(
                "", tk.END, text=acc["nickname"],
                values=(status_text,),
            )

    def _on_save(self):
        nickname = self.nick_var.get().strip()
        if not nickname:
            messagebox.showwarning("警告", "請輸入暱稱", parent=self)
            return
        try:
            tiktok_uploader.save_account(nickname=nickname)
        except Exception as e:
            messagebox.showerror("錯誤", f"儲存失敗: {e}", parent=self)
            return
        self.nick_var.set("")
        self._refresh_list()
        messagebox.showinfo("已儲存", f"帳號「{nickname}」已新增\n\n下一步：選取該帳號 → 點「🔑 登入」完成 TikTok 登入", parent=self)

    def _on_login(self):
        """在瀏覽器中登入 TikTok（背景執行緒）"""
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("警告", "請先選取要登入的帳號", parent=self)
            return
        nickname = self.tree.item(sel[0], "text")

        self.config(cursor="watch")
        self.update()

        def do_login():
            import asyncio
            try:
                asyncio.run(tiktok_uploader._login(nickname))
                self.after(0, self._refresh_list)
                self.after(0, lambda: self.config(cursor=""))
                self.after(0, lambda: messagebox.showinfo("完成", f"帳號「{nickname}」已登入！", parent=self))
            except Exception as e:
                self.after(0, lambda: self.config(cursor=""))
                self.after(0, lambda: messagebox.showerror("錯誤", f"登入失敗: {e}", parent=self))

        threading.Thread(target=do_login, daemon=True).start()

    def _on_remove(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("警告", "請先選取要移除的帳號", parent=self)
            return
        nickname = self.tree.item(sel[0], "text")
        if messagebox.askyesno("確認", f"確定移除帳號「{nickname}」？\n（瀏覽器設定檔也將一併刪除）", parent=self):
            tiktok_uploader.remove_account(nickname)
            self._refresh_list()
