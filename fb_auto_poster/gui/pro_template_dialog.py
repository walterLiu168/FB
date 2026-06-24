"""Pro Template Editor Dialog — 編輯/新增 房屋/土地/廠房模板"""
import tkinter as tk
from tkinter import ttk, messagebox

from gui.dark_theme import create_styled_button, create_styled_entry, create_styled_label, create_styled_frame
from core.pro_templates import save_template


class TemplateEditorDialog(tk.Toplevel):
    """模板編輯對話框"""

    def __init__(self, parent, template: dict, on_save=None):
        super().__init__(parent)
        self.title(f"✏️ 編輯模板 - {template['name']}")
        self.geometry("650x520")
        self.transient(parent)
        self.grab_set()
        self.configure(bg="#2b2b2b")

        self.template = template
        self.on_save = on_save

        # ── 名稱 ──
        name_row = create_styled_frame(self)
        name_row.pack(fill=tk.X, padx=10, pady=(10, 5))
        create_styled_label(name_row, text="名稱:", font=("Arial", 9, "bold")).pack(side=tk.LEFT)
        self.name_var = tk.StringVar(value=template["name"])
        self.name_entry = create_styled_entry(name_row, width=25, textvariable=self.name_var)
        self.name_entry.pack(side=tk.LEFT, padx=10)

        # ── 類型 ──
        type_row = create_styled_frame(self)
        type_row.pack(fill=tk.X, padx=10, pady=5)
        create_styled_label(type_row, text="類型:", font=("Arial", 9, "bold")).pack(side=tk.LEFT)
        self.type_var = tk.StringVar(value=template.get("type", "house"))
        ttk.Combobox(
            type_row, textvariable=self.type_var,
            values=["house", "land", "factory", "custom"],
            state="readonly", width=12,
        ).pack(side=tk.LEFT, padx=10)

        # ── 模板文字 ──
        create_styled_label(self, text="模板 (使用 {欄位名} 作為佔位符):", font=("Arial", 9, "bold")).pack(anchor=tk.W, padx=10, pady=(10, 0))
        self.tmpl_text = tk.Text(self, height=10, bg="#2b2b2b", fg="#ffffff", insertbackground="white",
                                 font=("Consolas", 9))
        self.tmpl_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.tmpl_text.insert("1.0", template["template"])

        # ── 欄位定義 ──
        create_styled_label(self, text="欄位定義 (key: label, required):", font=("Arial", 9, "bold")).pack(anchor=tk.W, padx=10, pady=(10, 0))

        field_frame = create_styled_frame(self)
        field_frame.pack(fill=tk.X, padx=10, pady=5)

        self.field_list = tk.Listbox(field_frame, height=5, bg="#2b2b2b", fg="#ffffff",
                                     selectbackground="#0078d4", font=("Consolas", 9))
        self.field_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        fbtn_frame = create_styled_frame(field_frame)
        fbtn_frame.pack(side=tk.LEFT, padx=5)
        create_styled_button(fbtn_frame, text="➕", command=self._add_field, bootstyle="success").pack(pady=2, fill=tk.X)
        create_styled_button(fbtn_frame, text="✏️", command=self._edit_field, bootstyle="warning").pack(pady=2, fill=tk.X)
        create_styled_button(fbtn_frame, text="❌", command=self._remove_field, bootstyle="danger").pack(pady=2, fill=tk.X)

        self._editable_fields = list(template.get("fields", []))
        self._refresh_field_list()

        # ── 按鈕 ──
        btn_frame = create_styled_frame(self)
        btn_frame.pack(pady=10)
        create_styled_button(btn_frame, text="💾 儲存", command=self._do_save, bootstyle="success").pack(side=tk.LEFT, padx=5)
        create_styled_button(btn_frame, text="取消", command=self.destroy, bootstyle="secondary").pack(side=tk.LEFT, padx=5)

    def _refresh_field_list(self):
        self.field_list.delete(0, tk.END)
        for f in self._editable_fields:
            req = "🔴" if f.get("required") else "  "
            multi = "📝" if f.get("multiline") else "  "
            self.field_list.insert(tk.END, f"{req}{multi} {f['key']}: {f.get('label', f['key'])}")

    def _add_field(self):
        d = FieldDialog(self, title="新增欄位")
        if d.result:
            self._editable_fields.append(d.result)
            self._refresh_field_list()

    def _edit_field(self):
        sel = self.field_list.curselection()
        if not sel:
            return
        idx = sel[0]
        d = FieldDialog(self, title="編輯欄位", field=self._editable_fields[idx])
        if d.result:
            self._editable_fields[idx] = d.result
            self._refresh_field_list()

    def _remove_field(self):
        sel = self.field_list.curselection()
        if sel:
            del self._editable_fields[sel[0]]
            self._refresh_field_list()

    def _do_save(self):
        name = self.name_var.get().strip()
        if not name:
            messagebox.showwarning("警告", "請輸入模板名稱")
            return
        tmpl_text = self.tmpl_text.get("1.0", tk.END).strip()
        if not tmpl_text:
            messagebox.showwarning("警告", "請輸入模板內容")
            return

        save_template(name, self.type_var.get(), tmpl_text, self._editable_fields)
        if self.on_save:
            self.on_save(name)
        self.destroy()


class FieldDialog(tk.Toplevel):
    """單一欄位編輯對話框"""

    def __init__(self, parent, title="欄位設定", field: dict = None):
        super().__init__(parent)
        self.title(title)
        self.geometry("300x200")
        self.transient(parent)
        self.grab_set()
        self.configure(bg="#2b2b2b")
        self.result = None

        field = field or {}

        create_styled_label(self, text="Key (佔位符):", font=("Arial", 9)).pack(anchor=tk.W, padx=10, pady=(10, 0))
        self.key_var = tk.StringVar(value=field.get("key", ""))
        self.key_entry = create_styled_entry(self, width=30, textvariable=self.key_var)
        self.key_entry.pack(padx=10, pady=2)

        create_styled_label(self, text="Label (顯示名稱):", font=("Arial", 9)).pack(anchor=tk.W, padx=10, pady=(5, 0))
        self.label_var = tk.StringVar(value=field.get("label", ""))
        create_styled_entry(self, width=30, textvariable=self.label_var).pack(padx=10, pady=2)

        self.req_var = tk.BooleanVar(value=field.get("required", False))
        ttk.Checkbutton(self, text="必填 (required)", variable=self.req_var).pack(anchor=tk.W, padx=10, pady=2)

        self.ml_var = tk.BooleanVar(value=field.get("multiline", False))
        ttk.Checkbutton(self, text="多行 (multiline)", variable=self.ml_var).pack(anchor=tk.W, padx=10, pady=2)

        btn_frame = create_styled_frame(self)
        btn_frame.pack(pady=10)
        create_styled_button(btn_frame, text="確定", command=self._ok, bootstyle="success").pack(side=tk.LEFT, padx=5)
        create_styled_button(btn_frame, text="取消", command=self.destroy, bootstyle="secondary").pack(side=tk.LEFT, padx=5)

    def _ok(self):
        key = self.key_var.get().strip()
        label = self.label_var.get().strip()
        if not key or not label:
            messagebox.showwarning("警告", "Key 和 Label 都必須填寫")
            return
        self.result = {
            "key": key,
            "label": label,
            "required": self.req_var.get(),
            "multiline": self.ml_var.get(),
        }
        self.destroy()
