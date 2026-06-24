"""日誌檢視面板 — 顯示操作記錄"""
import tkinter as tk
from tkinter import ttk

from gui.dark_theme import create_styled_button, create_styled_label, create_styled_frame
from utils.logger import read_logs


class LogPanel(ttk.Frame):
    """操作日誌檢視面板"""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self._build_ui()

    def _build_ui(self):
        # 工具列
        toolbar = create_styled_frame(self)
        toolbar.pack(fill=tk.X, padx=10, pady=10)

        create_styled_label(toolbar, text="📋 操作日誌", font=("Arial", 14)).pack(side=tk.LEFT)

        create_styled_button(toolbar, text="🔄 重新整理", command=self._refresh, bootstyle="info").pack(side=tk.RIGHT, padx=5)
        create_styled_button(toolbar, text="🗑️ 清除日誌", command=self._clear_log, bootstyle="danger").pack(side=tk.RIGHT, padx=5)

        # 日誌文字顯示區
        self.log_text = tk.Text(self, height=25, bg="#1e1e1e", fg="#e0e0e0",
                                insertbackground="white", font=("Consolas", 10),
                                wrap=tk.WORD, state=tk.DISABLED)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        # 捲軸
        scrollbar = ttk.Scrollbar(self.log_text, orient=tk.VERTICAL, command=self.log_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.configure(yscrollcommand=scrollbar.set)

        # 自動重新整理（每 10 秒）
        self._auto_refresh()

    def _refresh(self):
        """讀取並顯示日誌"""
        logs = read_logs(max_lines=200)
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)

        if not logs:
            self.log_text.insert("1.0", "尚無操作記錄。\n\n發文、養號、刪文等操作將自動記錄於此。")
        else:
            for line in logs:
                # 依狀態著色
                tag = None
                if "✅" in line:
                    tag = "success"
                elif "❌" in line:
                    tag = "error"
                elif "⏳" in line or "⚠️" in line:
                    tag = "warn"

                self.log_text.insert(tk.END, line + "\n", tag)

        # 設定標籤樣式
        self.log_text.tag_config("success", foreground="#4CAF50")
        self.log_text.tag_config("error", foreground="#f44336")
        self.log_text.tag_config("warn", foreground="#FF9800")

        self.log_text.config(state=tk.DISABLED)
        self.log_text.see(tk.END)

    def _clear_log(self):
        """清除日誌檔案"""
        from tkinter import messagebox
        if messagebox.askyesno("確認", "確定清除所有操作日誌？"):
            from utils.config import get_data_path
            import os
            path = get_data_path("operations.log")
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write("")
                self._refresh()
            except Exception:
                pass

    def _auto_refresh(self):
        """每隔 10 秒自動重新整理"""
        self._refresh()
        self.after(10000, self._auto_refresh)
