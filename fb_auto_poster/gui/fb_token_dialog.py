"""FB API 設定對話框 — 管理粉絲專頁的 Graph API Token

使用者可在此輸入：
  - 粉絲專頁 ID
  - 粉絲專頁名稱（僅供辨識）
  - Page Access Token

Token 透過 utils/secret_store.py 加密儲存於 data/fb_pages.json。
"""
import threading
import tkinter as tk
from datetime import datetime
from tkinter import messagebox
import ttkbootstrap as ttk
from ttkbootstrap.constants import *

from core.fb_graph_poster import (
    FBPageManager, FBPageConfig, FBGraphAPI, FBGraphAPIError, get_stored_pages,
    post_via_api,
)
from core.account import AccountManager
from utils.secret_store import mask
from utils.logger import log


class FBTokenDialog(ttk.Toplevel):
    """FB Graph API Token 設定對話框"""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("FB API 設定 — Graph Token")
        self.geometry("620x520")
        self.transient(parent)
        self.grab_set()

        self._page_mgr = FBPageManager()
        self._account_mgr = AccountManager()

        self._build_ui()
        self._refresh_list()

    def _build_ui(self):
        main_frame = ttk.Frame(self, padding=15)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # ── 標題 ──
        ttk.Label(main_frame, text="FB Graph API 設定", font=("Arial", 14)).pack(anchor=tk.W)
        ttk.Label(
            main_frame,
            text="在此管理粉絲專頁的 Access Token。\n"
                 "發文時可選擇「API 模式」直接透過 Graph API 發布，不需開啟瀏覽器。\n\n"
                 "如何取得 Token：\n"
                 "1. 前往 https://developers.facebook.com/apps/ 建立/選取 App\n"
                 "2. 工具 → Graph API Explorer → 選取粉絲專頁 → 取得 Page Access Token\n"
                 "3. Token 權限需包含: pages_manage_posts, pages_read_engagement",
            font=("Arial", 8), bootstyle="secondary", justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(2, 10))

        # ── 現有清單 ──
        lf_list = ttk.LabelFrame(main_frame, text="已設定的粉絲專頁")
        lf_list.pack(fill=tk.BOTH, expand=True, pady=5)
        list_inner = ttk.Frame(lf_list, padding=8)
        list_inner.pack(fill=tk.BOTH, expand=True)

        columns = ("page_name", "page_id", "linked_account", "token_status")
        self.tree = ttk.Treeview(list_inner, columns=columns, show="headings", height=5)
        self.tree.heading("page_name", text="粉絲專頁名稱")
        self.tree.heading("page_id", text="Page ID")
        self.tree.heading("linked_account", text="連結 FB 帳號")
        self.tree.heading("token_status", text="Token 狀態")
        self.tree.column("page_name", width=160)
        self.tree.column("page_id", width=110)
        self.tree.column("linked_account", width=160)
        self.tree.column("token_status", width=100)
        self.tree.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)

        btn_side = ttk.Frame(list_inner)
        btn_side.pack(side=tk.RIGHT, padx=(8, 0), fill=tk.Y)
        ttk.Button(btn_side, text="驗證 Token", command=self._on_verify, bootstyle="info").pack(pady=2, fill=tk.X)
        ttk.Button(btn_side, text="測試發文", command=self._on_test_post, bootstyle="warning").pack(pady=2, fill=tk.X)
        ttk.Button(btn_side, text="移除選取", command=self._on_remove, bootstyle="danger-outline").pack(pady=2, fill=tk.X)

        # ── 新增/編輯表單 ──
        lf_form = ttk.LabelFrame(main_frame, text="新增/編輯粉絲專頁")
        lf_form.pack(fill=tk.X, pady=5)
        form_inner = ttk.Frame(lf_form, padding=8)
        form_inner.pack(fill=tk.X)
        form_inner.columnconfigure(1, weight=1)

        ttk.Label(form_inner, text="Page ID:").grid(row=0, column=0, sticky=tk.W, pady=3)
        self.page_id_var = tk.StringVar()
        ttk.Entry(form_inner, textvariable=self.page_id_var).grid(row=0, column=1, sticky=tk.EW, pady=3, padx=(5, 0))

        ttk.Label(form_inner, text="Page 名稱:").grid(row=1, column=0, sticky=tk.W, pady=3)
        self.page_name_var = tk.StringVar()
        ttk.Entry(form_inner, textvariable=self.page_name_var).grid(row=1, column=1, sticky=tk.EW, pady=3, padx=(5, 0))

        ttk.Label(form_inner, text="Access Token:").grid(row=2, column=0, sticky=tk.W, pady=3)
        token_frame = ttk.Frame(form_inner)
        token_frame.grid(row=2, column=1, sticky=tk.EW, pady=3, padx=(5, 0))
        token_frame.columnconfigure(0, weight=1)
        self.token_var = tk.StringVar()
        self.token_entry = ttk.Entry(token_frame, textvariable=self.token_var, show="*")
        self.token_entry.grid(row=0, column=0, sticky=tk.EW)
        self.show_token_btn = ttk.Button(token_frame, text="👁", width=3, command=self._toggle_token_show)
        self.show_token_btn.grid(row=0, column=1, padx=(4, 0))
        self._token_shown = False

        ttk.Label(form_inner, text="連結 FB 帳號:").grid(row=3, column=0, sticky=tk.W, pady=3)
        self.link_var = tk.StringVar()
        accounts = self._account_mgr.list_all()
        account_names = [f"{a.email} ({a.nickname})" for a in accounts] if accounts else ["（無帳號）"]
        self.link_combo = ttk.Combobox(
            form_inner, textvariable=self.link_var,
            values=account_names, state="readonly", width=35,
        )
        self.link_combo.grid(row=3, column=1, sticky=tk.EW, pady=3, padx=(5, 0))
        if account_names:
            self.link_combo.current(0)

        btn_row = ttk.Frame(form_inner)
        btn_row.grid(row=4, column=1, sticky=tk.E, pady=8)
        ttk.Button(btn_row, text="儲存", command=self._on_save, bootstyle="success").pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_row, text="清除", command=self._clear_form, bootstyle="secondary").pack(side=tk.LEFT, padx=2)

        # ── 底部提示 ──
        self.status_label = ttk.Label(main_frame, text="", font=("Arial", 9))
        self.status_label.pack(anchor=tk.W, pady=2)

        ttk.Button(main_frame, text="關閉", command=self.destroy, bootstyle="secondary").pack(pady=5)

    def _refresh_list(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        pages = get_stored_pages()
        accounts = {a.account_id: f"{a.email} ({a.nickname})" for a in self._account_mgr.list_all()}
        for p in pages:
            linked = accounts.get(p["linked_account_id"], p.get("linked_account_id", ""))
            token_status = "✅ 已設定" if p.get("has_token") else "❌ 無 Token"
            self.tree.insert(
                "", tk.END,
                values=(p["page_name"], p["page_id"], linked, token_status),
            )

    def _on_save(self):
        page_id = self.page_id_var.get().strip()
        page_name = self.page_name_var.get().strip()
        token = self.token_var.get().strip()
        link_display = self.link_var.get().strip()

        if not page_id:
            messagebox.showwarning("警告", "請輸入 Page ID", parent=self)
            return
        if not token:
            messagebox.showwarning("警告", "請輸入 Access Token", parent=self)
            return

        # 解析 linked account id
        linked_account_id = ""
        if link_display and link_display != "（無帳號）":
            for a in self._account_mgr.list_all():
                if f"{a.email} ({a.nickname})" == link_display:
                    linked_account_id = a.account_id
                    break

        cfg = FBPageConfig(page_id=page_id, page_name=page_name, linked_account_id=linked_account_id)
        cfg.access_token = token  # 自動加密
        self._page_mgr.add(cfg)
        log("FBAPI", page_id, f"已儲存 Page: {page_name}", "✅")
        self._clear_form()
        self._refresh_list()
        self.status_label.config(text=f"✅ 已儲存 {page_name} (Page ID: {page_id})")

    def _on_remove(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("警告", "請先選取要移除的項目", parent=self)
            return
        values = self.tree.item(sel[0], "values")
        page_id = values[1]
        page_name = values[0]
        if messagebox.askyesno("確認", f"確定移除「{page_name}」({page_id})？", parent=self):
            self._page_mgr.remove(page_id)
            self._refresh_list()
            self.status_label.config(text=f"已移除 {page_name}")

    def _on_verify(self):
        """驗證選取的 token 是否有效"""
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("警告", "請先選取要驗證的粉絲專頁", parent=self)
            return
        values = self.tree.item(sel[0], "values")
        page_id = values[1]

        cfg = self._page_mgr.get(page_id)
        if not cfg or not cfg.access_token_encrypted:
            messagebox.showwarning("警告", "此 Page 沒有設定 Token", parent=self)
            return

        token = cfg.access_token
        self.status_label.config(text="⏳ 驗證中...")
        self.update()

        def do_verify():
            info = FBGraphAPI.validate_token(token)
            self.after(0, lambda: self._show_verify_result(page_id, info))

        threading.Thread(target=do_verify, daemon=True).start()

    def _show_verify_result(self, page_id: str, info: dict):
        if info.get("is_valid"):
            from datetime import datetime
            expires = info.get("expires_at", 0)
            if expires:
                exp_str = datetime.fromtimestamp(expires).strftime("%Y-%m-%d %H:%M")
            else:
                exp_str = "永不（Page Token）/ 無法判斷"
            scopes = ", ".join(info.get("scopes", [])) or "（無）"
            missing = info.get("missing_scopes", [])

            # 權限缺失提示
            missing_note = ""
            if missing:
                from core.fb_graph_poster import _REQUIRED_SCOPES
                missing_note = "\n\n⚠️ 缺少的權限：\n"
                for s in missing:
                    desc = _REQUIRED_SCOPES.get(s, "")
                    missing_note += f"  • {s}{' — ' + desc if desc else ''}\n"
                missing_note += "\n缺少 pages_manage_posts 將無法發文！"

            msg = (
                f"✅ Token 有效\n\n"
                f"類型: {info.get('type', 'N/A')}\n"
                f"到期: {exp_str}\n"
                f"擁有的權限: {scopes}"
                f"{missing_note}"
            )
            self.status_label.config(text=f"✅ {page_id} Token 有效")
            messagebox.showinfo("驗證結果", msg, parent=self)
        else:
            err = info.get("error", "未知錯誤")
            self.status_label.config(text=f"❌ Token 無效: {err}")
            # 加入常見解決方案提示
            help_msg = (
                f"❌ Token 無效\n\n{err}\n\n"
                "常見原因與解決方案：\n"
                "1. Token 已過期 → 重新取得 Token\n"
                "2. Token 複製不完整 → 確認從「EAA」開頭完整複製\n"
                "3. App 未上線 → 在 developers.facebook.com 將 App 設為上線\n"
                "4. Token 類型錯誤 → 需使用 Page Access Token，非 User Token\n\n"
                "取得 Token 步驟：\n"
                "• 前往 https://developers.facebook.com/tools/explorer/\n"
                "• 選取你的 App → 取得 User Token\n"
                "• 再選取粉絲專頁 → 取得 Page Access Token"
            )
            messagebox.showerror("驗證結果", help_msg, parent=self)

    def _on_test_post(self):
        """測試發文：發送純文字貼文到選取的粉絲專頁"""
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("警告", "請先選取要測試的粉絲專頁", parent=self)
            return
        values = self.tree.item(sel[0], "values")
        page_id = values[1]
        page_name = values[0]

        cfg = self._page_mgr.get(page_id)
        if not cfg or not cfg.access_token_encrypted:
            messagebox.showwarning("警告", "此 Page 沒有設定 Token", parent=self)
            return

        self.status_label.config(text="⏳ 測試發文中...")
        self.config(cursor="watch")
        self.update()

        def do_test():
            try:
                api = FBGraphAPI(page_id, cfg.access_token)
                result = api.post_text(f"[測試貼文] API 模式運作正常 — {datetime.now().strftime('%H:%M:%S')}")
                post_id = result.get("id", "")
                self.after(0, lambda: self.status_label.config(
                    text=f"✅ 測試成功！Post ID: {post_id}"
                ))
                self.after(0, lambda: messagebox.showinfo(
                    "測試結果", f"✅ 發文成功！\n\n粉絲專頁: {page_name}\nPost ID: {post_id}",
                    parent=self,
                ))
            except FBGraphAPIError as e:
                self.after(0, lambda: self.status_label.config(text=f"❌ 測試失敗: {str(e)[:60]}"))
                self.after(0, lambda: messagebox.showerror(
                    "測試失敗", f"❌ {e}\n\n(錯誤碼: {e.code})",
                    parent=self,
                ))
            except Exception as e:
                self.after(0, lambda: self.status_label.config(text=f"❌ 測試異常: {str(e)[:60]}"))
            finally:
                self.after(0, lambda: self.config(cursor=""))

        threading.Thread(target=do_test, daemon=True).start()

    def _toggle_token_show(self):
        self._token_shown = not self._token_shown
        self.token_entry.config(show="" if self._token_shown else "*")
        self.show_token_btn.config(text="🙈" if self._token_shown else "👁")

    def _clear_form(self):
        self.page_id_var.set("")
        self.page_name_var.set("")
        self.token_var.set("")
        # 不重置 link combo

    def _get_selected_page_config(self) -> tuple[str, str]:
        """回傳 (page_id, access_token)，若無選取則 ('', '')"""
        sel = self.tree.selection()
        if not sel:
            return ("", "")
        values = self.tree.item(sel[0], "values")
        page_id = values[1]
        cfg = self._page_mgr.get(page_id)
        if not cfg:
            return ("", "")
        return (page_id, cfg.access_token)


