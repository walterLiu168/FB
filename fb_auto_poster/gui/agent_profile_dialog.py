"""Agent Profile Editor — 編輯營業員資料 (同步到個人網站 agent.json)

使用 tkinter 原生元件確保跨主題相容性，避免 ttk.Entry/ttk.Label 的深色主題 bug。
"""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import json
import os
import shutil
import re
from datetime import datetime

# ── 主題配色 ──
BG = "#2b2b2b"
FG = "#ffffff"
ENTRY_BG = "#3c3c3c"
ENTRY_FG = "#ffffff"
ACCENT = "#2d7dd2"
BTN_BG = "#3c3c3c"


def _agent_path():
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "fb_property_site", "data", "agent.json"
    )


def load_profile() -> dict:
    path = _agent_path()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_profile(profile: dict):
    path = _agent_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)


class AgentProfileDialog(tk.Toplevel):

    def __init__(self, parent):
        super().__init__(parent)
        self.title("✏️ 營業員資料")
        self.geometry("580x750")
        self.minsize(480, 500)
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()
        self.configure(bg=BG)

        self.profile = load_profile()
        self._photo_path = self.profile.get("photo", "")
        self._entry_vars = {}

        self._build_ui()

    # ── Helpers ──

    def _label(self, parent, text=None, **kw):
        defaults = {"bg": BG, "fg": FG}
        if text is not None:
            defaults["text"] = text
        defaults.update(kw)
        w = tk.Label(parent, **defaults)
        return w

    def _entry(self, parent, var=None, width=38, **kw):
        if var is None:
            var = tk.StringVar()
        defaults = {
            "width": width, "textvariable": var,
            "bg": ENTRY_BG, "fg": ENTRY_FG, "insertbackground": "white",
            "relief": "flat", "bd": 4, "highlightthickness": 1,
            "highlightbackground": "#555555", "highlightcolor": ACCENT,
            "font": ("Arial", 10),
        }
        defaults.update(kw)
        w = tk.Entry(parent, **defaults)
        return w, var

    def _btn(self, parent, text, cmd, color=ACCENT):
        return tk.Button(
            parent, text=text, command=cmd,
            bg=color, fg="#ffffff", activebackground="#2569b3",
            activeforeground="#ffffff", relief="flat", bd=0,
            padx=14, pady=4, font=("Arial", 9, "bold"),
            cursor="hand2",
        )

    def _sep(self, parent):
        f = tk.Frame(parent, bg="#444444", height=1)
        return f

    def _build_ui(self):
        # ── 捲動區域 ──
        canvas = tk.Canvas(self, bg=BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        scroll_frame = tk.Frame(canvas, bg=BG)

        scroll_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scroll_frame, anchor="nw", width=560)
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True, padx=10, pady=10)
        scrollbar.pack(side="right", fill="y", pady=10)

        # 綁定滑鼠滾輪
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        self._canvas = canvas

        # ═══ 基本資料區塊 ═══

        sec1 = tk.Frame(scroll_frame, bg=BG)
        sec1.pack(fill="x", pady=(0, 10))
        self._label(sec1, text="🪪 營業員基本資料", font=("Arial", 14, "bold")).pack(anchor="w", pady=(0, 10))

        # 照片行
        row = tk.Frame(sec1, bg=BG)
        row.pack(fill="x", pady=3)
        self._label(row, text="大頭照：", font=("Arial", 10), width=9, anchor="w").pack(side="left")
        self.photo_var = tk.StringVar(
            value=self._photo_path if self._photo_path else "（未選擇）"
        )
        self._label(row, textvariable=self.photo_var, font=("Arial", 8),
                     fg="#aaaaaa", anchor="w").pack(side="left", padx=8)
        self._btn(row, "📷 選擇", self._pick_photo, "#4a90d9").pack(side="left", padx=2)
        self._btn(row, "清除", self._clear_photo, "#666666").pack(side="left", padx=2)

        # 分隔
        self._sep(sec1).pack(fill="x", pady=8)

        # 基本欄位
        fields = [
            ("姓名", "name"),
            ("公司", "company"),
            ("電話", "phone"),
            ("證號", "license"),
            ("Email", "email"),
            ("LINE ID", "line_id"),
        ]
        for label, key in fields:
            r = tk.Frame(sec1, bg=BG)
            r.pack(fill="x", pady=2)
            self._label(r, text=f"{label}：", font=("Arial", 10), width=9, anchor="w").pack(side="left")
            e, var = self._entry(r, width=36)
            default = self.profile.get(key, "")
            var.set(default)
            e.pack(side="left", fill="x", expand=True, padx=(0, 0))
            self._entry_vars[key] = var

        # 自我介紹
        self._label(sec1, text="自我介紹：", font=("Arial", 10)).pack(anchor="w", pady=(12, 2))
        self.intro_text = tk.Text(
            sec1, height=5, bg=ENTRY_BG, fg=ENTRY_FG, insertbackground="white",
            font=("Arial", 10), relief="flat", bd=4, highlightthickness=1,
            highlightbackground="#555555", highlightcolor=ACCENT,
            wrap="word",
        )
        self.intro_text.pack(fill="x", pady=2)
        default_intro = self.profile.get("intro", "")
        if default_intro:
            self.intro_text.insert("1.0", default_intro)

        # ═══ 社群連結區塊 ═══

        sec2 = tk.Frame(scroll_frame, bg=BG)
        sec2.pack(fill="x", pady=(10, 10))
        self._label(sec2, text="📱 社群連結", font=("Arial", 14, "bold")).pack(anchor="w", pady=(0, 10))

        social = [
            ("YouTube", "youtube"),
            ("Facebook", "facebook"),
            ("TikTok", "tiktok"),
            ("LINE 網址", "line_url"),
        ]
        for label, key in social:
            r = tk.Frame(sec2, bg=BG)
            r.pack(fill="x", pady=2)
            self._label(r, text=f"{label}：", font=("Arial", 10), width=9, anchor="w").pack(side="left")
            e, var = self._entry(r, width=36)
            var.set(self.profile.get(key, ""))
            e.pack(side="left", fill="x", expand=True)
            self._entry_vars[key] = var

        # ═══ 介紹影片區塊 ═══

        sec3 = tk.Frame(scroll_frame, bg=BG)
        sec3.pack(fill="x", pady=(10, 10))
        self._label(sec3, text="🎬 自我介紹影片", font=("Arial", 14, "bold")).pack(anchor="w", pady=(0, 10))

        r = tk.Frame(sec3, bg=BG)
        r.pack(fill="x", pady=2)
        self._label(r, text="YouTube 網址：", font=("Arial", 10), width=12, anchor="w").pack(side="left")
        self.video_var = tk.StringVar(value=self.profile.get("intro_video", ""))
        e, _ = self._entry(r, var=self.video_var, width=36)
        e.pack(side="left", fill="x", expand=True, padx=(0, 0))
        self._label(sec3, text="💡 貼入完整網址（如 https://youtube.com/watch?v=xxxxx）",
                     font=("Arial", 7), fg="#888888").pack(anchor="w", pady=(2, 0))

        # ═══ 按鈕列 ═══

        btn_row = tk.Frame(self, bg=BG)
        btn_row.pack(pady=(0, 12))
        self._btn(btn_row, "💾 儲存", self._do_save, "#27ae60").pack(side="left", padx=5)
        self._btn(btn_row, "取消", self.destroy, "#666666").pack(side="left", padx=5)

    # ── 動作 ──

    def _pick_photo(self):
        file = filedialog.askopenfilename(
            title="選擇大頭照",
            filetypes=[("圖片", "*.jpg *.jpeg *.png *.webp")],
        )
        if not file:
            return
        site_images = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "fb_property_site", "images"
        )
        os.makedirs(site_images, exist_ok=True)
        ext = os.path.splitext(file)[1] or ".jpg"
        dst_name = f"agent_{datetime.now().strftime('%Y%m%d_%H%M%S')}{ext}"
        dst = os.path.join(site_images, dst_name)
        shutil.copy2(file, dst)
        self._photo_path = f"images/{dst_name}"
        self.photo_var.set(self._photo_path)

    def _clear_photo(self):
        self._photo_path = ""
        self.photo_var.set("（未選擇）")

    def _do_save(self):
        name = self._entry_vars.get("name")
        name_val = name.get().strip() if name else ""
        if not name_val:
            messagebox.showwarning("警告", "請至少填寫姓名", parent=self)
            return

        profile = {
            "name": name_val,
            "company": self._entry_vars.get("company", tk.StringVar()).get().strip(),
            "phone": self._entry_vars.get("phone", tk.StringVar()).get().strip(),
            "license": self._entry_vars.get("license", tk.StringVar()).get().strip(),
            "email": self._entry_vars.get("email", tk.StringVar()).get().strip(),
            "line_id": self._entry_vars.get("line_id", tk.StringVar()).get().strip(),
            "intro": self.intro_text.get("1.0", tk.END).strip(),
            "photo": self._photo_path if self._photo_path else "",
        }

        for key in ("youtube", "facebook", "tiktok", "line_url"):
            var = self._entry_vars.get(key)
            val = (var.get().strip()) if var else ""
            if val:
                profile[key] = val

        video = self.video_var.get().strip()
        if video:
            m = re.search(r'(?:v=|youtu\.be/)([a-zA-Z0-9_-]{11})', video)
            profile["intro_video"] = m.group(1) if m else video

        save_profile(profile)
        messagebox.showinfo("成功", "✅ 營業員資料已儲存，網站會自動更新！", parent=self)
        self.destroy()

    def destroy(self):
        canvas = getattr(self, '_canvas', None)
        if canvas:
            try:
                canvas.unbind_all("<MouseWheel>")
            except Exception:
                pass
        super().destroy()
