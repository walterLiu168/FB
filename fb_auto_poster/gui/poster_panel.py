"""發文操作界面 — 整合 AI 文案生成、圖片爬取、Header/Footer、自動刪文"""
import json
import os
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime, timedelta

from gui.dark_theme import (
    create_styled_button, create_styled_entry,
    create_styled_label, create_styled_frame
)
from core.ai_writer import generate_ad, is_ollama_running, list_ollama_models, generate_property_post
from core.scraper import scrape_images_from_url, clean_temp_images, get_temp_image_count
from core.scraper import extract_property_info as _legacy_extract
from core.multi_site_scraper import extract_from_url as extract_property_info
from core.templates import TemplateManager
from core.pro_templates import (
    list_templates, get_template, fill_template, generate_post,
    list_group_sets, save_group_set, get_group_set,
)
from core.fb_graph_poster import FBPageManager, post_via_api
from utils.logger import log

# TikTok 模組延遲載入（只在需要時匯入，加速啟動）
_tiktok_imported = False
def _import_tiktok():
    global _tiktok_imported
    if not _tiktok_imported:
        from core import tiktok_slideshow, tiktok_uploader
        tiktok_slideshow.__name__  # no-op to keep import alive
        _tiktok_imported = True
    from core import tiktok_slideshow, tiktok_uploader
    return tiktok_slideshow, tiktok_uploader


class PosterPanel(ttk.Frame):
    """一般發文 + 拍賣發文 操作面板 (V2 with AI + Scraper + Templates)"""

    def __init__(self, parent, account_ids: list[str] = None, account_map: dict = None,
                 engine=None, scheduler=None, **kwargs):
        super().__init__(parent, **kwargs)
        # account_map: {"email (nickname)": "account_id_uuid"}
        # 向後相容：如果傳入 account_ids 但沒有 account_map，自動建立
        if account_map is None:
            self.account_map = {}
            if account_ids:
                for aid in account_ids:
                    self.account_map[aid[:8] + "..."] = aid
        else:
            self.account_map = account_map
        self.account_ids = list(self.account_map.values()) or (account_ids or [])
        self.engine = engine
        self.scheduler = scheduler  # 排程器（供排程發文使用）
        self.selected_images = []
        self.scraped_images = []
        self._group_urls: dict[str, str] = {}  # name → facebook.com/groups/XXXX
        self.template_mgr = TemplateManager()
        # FB Graph API 模式支援
        self._fb_page_mgr = FBPageManager()
        self.fb_api_pages: dict[str, str] = {}  # {display_name: page_id}
        self._refresh_fb_api_pages()
        self._build_ui()

    def _build_ui(self):
        notebook = ttk.Notebook(self)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        general_frame = create_styled_frame(notebook, padding=10)
        notebook.add(general_frame, text="一般發文")
        self._build_general_tab(general_frame)

        market_frame = create_styled_frame(notebook, padding=10)
        notebook.add(market_frame, text="拍賣發文")
        self._build_market_tab(market_frame)

        self.status_var = tk.StringVar(value="就緒")
        ttk.Label(self, textvariable=self.status_var).pack(pady=5)

    def _build_general_tab(self, parent):
        # ── 可捲動容器 ──
        canvas = tk.Canvas(parent, bg="#2b2b2b", highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=canvas.yview)
        self._gen_scroll_frame = create_styled_frame(canvas)

        self._gen_scroll_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=self._gen_scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 滑鼠滾輪支援
        def on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", on_mousewheel, add="+")
        # 切換 tab 時解綁
        parent.bind("<Destroy>", lambda e: canvas.unbind_all("<MouseWheel>"), add="+")

        p = self._gen_scroll_frame  # 後續所有 widget 都建立在這個 frame 內

        # ── 帳號選擇 ──
        create_styled_label(p, text="選擇帳號:").pack(anchor=tk.W)
        display_names = list(self.account_map.keys())
        init_val = display_names[0] if display_names else ""
        self.account_var = tk.StringVar(value=init_val)
        self.account_combo = ttk.Combobox(
            p, textvariable=self.account_var,
            values=display_names, state="readonly", width=40
        )
        self.account_combo.pack(fill=tk.X, pady=5)

        # ── 發文模式切換：Browser（Playwright）vs API（Graph） ──
        mode_frame = create_styled_frame(p)
        mode_frame.pack(fill=tk.X, pady=2)
        create_styled_label(mode_frame, text="發文模式:").pack(side=tk.LEFT)
        self.api_mode_var = tk.BooleanVar(value=False)
        ttk.Radiobutton(
            mode_frame, text="🌐 瀏覽器 (Playwright)",
            variable=self.api_mode_var, value=False,
            command=self._on_mode_change,
        ).pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(
            mode_frame, text="⚡ API (Graph)",
            variable=self.api_mode_var, value=True,
            command=self._on_mode_change,
        ).pack(side=tk.LEFT, padx=5)

        # API 模式下選擇已設定的 FB Page
        self.api_page_frame = create_styled_frame(p)
        self.api_page_frame.pack(fill=tk.X, pady=2)
        create_styled_label(self.api_page_frame, text="API 粉絲專頁:").pack(side=tk.LEFT)
        self.api_page_var = tk.StringVar()
        api_pages = list(self.fb_api_pages.keys()) or ["（無 — 請先設定 FB API）"]
        self.api_page_combo = ttk.Combobox(
            self.api_page_frame, textvariable=self.api_page_var,
            values=api_pages, state="readonly", width=35,
        )
        self.api_page_combo.pack(side=tk.LEFT, padx=5)
        if api_pages:
            self.api_page_combo.current(0)
        self.api_page_frame.pack_forget()  # 預設隱藏（Browser 模式不顯示）

        # ── Header ──
        hf_frame = create_styled_frame(p)
        hf_frame.pack(fill=tk.X, pady=5)

        create_styled_label(hf_frame, text="Header (頁首):", font=("Arial", 9)).pack(anchor=tk.W)
        self.header_var = tk.StringVar()
        self.header_entry = create_styled_entry(hf_frame, width=60, textvariable=self.header_var)
        self.header_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, pady=2)
        create_styled_button(hf_frame, text="⚙️", command=self._on_global_settings, bootstyle="secondary", width=3).pack(side=tk.LEFT, padx=(5, 0))
        create_styled_button(hf_frame, text="↓", command=self._load_global_header, bootstyle="info-outline", width=2).pack(side=tk.LEFT, padx=1)

        # ── 帳號切換時更新 Header/Footer ──
        self.account_combo.bind("<<ComboboxSelected>>", lambda e: self._load_header_footer())

        # ═══════════════════════════════════════════════════════════
        #   Pro 模板區 — 取代舊文案區
        # ═══════════════════════════════════════════════════════════
        # ── 模板選擇列 ──
        tmpl_row = create_styled_frame(p)
        tmpl_row.pack(fill=tk.X, pady=(10, 2))
        create_styled_label(tmpl_row, text="📋 模板:", font=("Arial", 9, "bold")).pack(side=tk.LEFT)
        self.tmpl_names = [t["name"] for t in list_templates()]
        self.tmpl_var = tk.StringVar(value=self.tmpl_names[0] if self.tmpl_names else "")
        self.tmpl_combo = ttk.Combobox(
            tmpl_row, textvariable=self.tmpl_var, values=self.tmpl_names,
            state="readonly", width=16
        )
        self.tmpl_combo.pack(side=tk.LEFT, padx=5)
        self.tmpl_combo.bind("<<ComboboxSelected>>", lambda e: self._on_template_change())
        create_styled_button(tmpl_row, text="✏️ 編輯", command=self._on_edit_template, bootstyle="secondary").pack(side=tk.LEFT, padx=2)
        create_styled_button(tmpl_row, text="🤖 一鍵生成", command=self._on_ai_generate, bootstyle="primary").pack(side=tk.LEFT, padx=5)
        create_styled_button(tmpl_row, text="👤 個人資料", command=self._on_edit_profile, bootstyle="info-outline").pack(side=tk.RIGHT, padx=2)

        # ── 動態欄位區 (scrollable) ──
        self.tmpl_fields_canvas = tk.Canvas(p, height=280, bg="#2b2b2b", highlightthickness=0)
        self.tmpl_fields_canvas.pack(fill=tk.X, pady=2)

        self.tmpl_fields_frame = create_styled_frame(self.tmpl_fields_canvas)
        self.tmpl_fields_canvas.create_window((0, 0), window=self.tmpl_fields_frame, anchor="nw")

        # ── 圖片列 ──
        img_row = create_styled_frame(p)
        img_row.pack(fill=tk.X, pady=3)
        create_styled_label(img_row, text="🖼️ 圖片:").pack(side=tk.LEFT)
        self.scrape_url_var = tk.StringVar()
        self.scrape_entry = create_styled_entry(img_row, width=30, textvariable=self.scrape_url_var)
        self.scrape_entry.pack(side=tk.LEFT, padx=5)
        self.scrape_entry.insert(0, "貼上網址爬取圖片...")
        self.scrape_entry.bind("<FocusIn>", lambda e: self.scrape_entry.delete(0, tk.END) if self.scrape_entry.get() == "貼上網址爬取圖片..." else None)
        ttk.Button(img_row, text="🔗", command=self._on_open_url).pack(side=tk.LEFT, padx=1)
        create_styled_button(img_row, text="🌐 抓取", command=self._on_scrape_images, bootstyle="info").pack(side=tk.LEFT, padx=2)
        create_styled_button(img_row, text="📁 本機選圖", command=self._select_images, bootstyle="secondary").pack(side=tk.LEFT, padx=2)
        self.img_label = create_styled_label(img_row, text="未選圖片")
        self.img_label.pack(side=tk.LEFT, padx=10)

        # ── 即時預覽 ──
        preview_frame = create_styled_frame(p)
        preview_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        create_styled_label(preview_frame, text="📄 預覽:", font=("Arial", 9, "bold")).pack(anchor=tk.W)
        self.preview_text = tk.Text(preview_frame, height=6, bg="#1e1e1e", fg="#d4d4d4",
                                    insertbackground="white", state=tk.DISABLED, font=("Consolas", 9))
        self.preview_text.pack(fill=tk.BOTH, expand=True, pady=2)

        # 初始化模板欄位 (延後初始化，footer_var 尚未建立)
        self.tmpl_field_widgets: dict[str, tk.Widget] = {}

        # ── Footer ──
        ft_frame = create_styled_frame(p)
        ft_frame.pack(fill=tk.X, pady=5)
        create_styled_label(ft_frame, text="Footer (頁尾):", font=("Arial", 9)).pack(anchor=tk.W)
        self.footer_var = tk.StringVar()
        self.footer_entry = create_styled_entry(ft_frame, width=60, textvariable=self.footer_var)
        self.footer_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, pady=2)
        create_styled_button(ft_frame, text="↓", command=self._load_global_footer, bootstyle="info-outline", width=2).pack(side=tk.LEFT, padx=1)
        # 載入 Header/Footer
        self._load_header_footer()

        # 現在 footer_var 已建立，初始化模板欄位 + 預覽
        self._on_template_change()

        # ── 目標社團 (含記憶功能) ──
        # 社團組合快速選取
        gs_row = create_styled_frame(p)
        gs_row.pack(fill=tk.X, pady=(10, 0))
        create_styled_label(gs_row, text="📦 社團組合:", font=("Arial", 9)).pack(side=tk.LEFT)
        self.group_set_var = tk.StringVar(value="Set 1")
        self.group_set_combo = ttk.Combobox(
            gs_row, textvariable=self.group_set_var,
            values=["Set 1", "Set 2", "Set 3"], state="readonly", width=10
        )
        self.group_set_combo.pack(side=tk.LEFT, padx=5)
        self.group_set_combo.bind("<<ComboboxSelected>>", lambda e: self._on_group_set_change())
        create_styled_button(gs_row, text="💾 儲存組合", command=self._on_save_group_set, bootstyle="success").pack(side=tk.LEFT, padx=2)

        create_styled_label(p, text="目標社團 (多選反白 = 發送目標):").pack(anchor=tk.W, pady=(5, 0))

        group_input_frame = create_styled_frame(p)
        group_input_frame.pack(fill=tk.X, pady=2)

        self.groups_entry = create_styled_entry(group_input_frame, width=50)
        self.groups_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self.groups_entry.insert(0, "輸入社團名稱並按 Enter 加入...")
        self.groups_entry.bind("<FocusIn>", lambda e: self.groups_entry.delete(0, tk.END) if "輸入社團名稱" in self.groups_entry.get() else None)
        self.groups_entry.bind("<Return>", lambda e: self._add_group_to_list())

        create_styled_button(group_input_frame, text="➕", command=self._add_group_to_list, bootstyle="success").pack(side=tk.LEFT, padx=1)
        create_styled_button(group_input_frame, text="💾 儲存", command=self._save_groups, bootstyle="info").pack(side=tk.LEFT, padx=1)
        create_styled_button(group_input_frame, text="🔄 載入", command=self._load_groups, bootstyle="secondary").pack(side=tk.LEFT, padx=1)
        create_styled_button(group_input_frame, text="📡 從 FB 載入", command=self._on_fetch_groups_from_fb, bootstyle="primary-outline").pack(side=tk.LEFT, padx=1)

        # 已選社團清單 (多選 Listbox)
        group_list_frame = create_styled_frame(p)
        group_list_frame.pack(fill=tk.X, pady=3)

        self.groups_listbox = tk.Listbox(
            group_list_frame, selectmode=tk.MULTIPLE,
            height=5, bg="#2b2b2b", fg="#ffffff",
            selectbackground="#0078d4", selectforeground="#ffffff",
            font=("Arial", 9),
        )
        self.groups_listbox.pack(side=tk.LEFT, fill=tk.X, expand=True)

        group_btn_frame = create_styled_frame(group_list_frame)
        group_btn_frame.pack(side=tk.LEFT, padx=5)
        create_styled_button(group_btn_frame, text="☑️ 全選", command=self._select_all_groups, bootstyle="info").pack(pady=2, fill=tk.X)
        create_styled_button(group_btn_frame, text="◻️ 全不選", command=self._deselect_all_groups, bootstyle="secondary").pack(pady=2, fill=tk.X)
        create_styled_button(group_btn_frame, text="❌", command=self._remove_selected_group, bootstyle="danger").pack(pady=2, fill=tk.X)
        create_styled_button(group_btn_frame, text="🗑️ 清空", command=self._clear_groups, bootstyle="secondary").pack(pady=2, fill=tk.X)

        # 選取計數器
        self.group_sel_label = create_styled_label(p, text="📋 已選 0 個社團（發文僅發送至反白選取者）", font=("Arial", 7))
        self.group_sel_label.pack(anchor=tk.W, pady=(0, 2))
        # 在 Listbox 點選時自動更新計數
        self.groups_listbox.bind("<<ListboxSelect>>", lambda e: self._update_group_selection_count())

        # 提示
        self.group_hint = create_styled_label(p, text="💡 輸入社團名 → Enter 或按「從 FB 載入」自動抓取 → 多選 (Ctrl+點選) → 儲存供日後使用", font=("Arial", 7))
        self.group_hint.pack(anchor=tk.W, pady=(0, 5))

        # 載入已儲存的社團
        self._load_groups()

        # ── 連結 (API 模式) ──
        link_frame = create_styled_frame(p)
        link_frame.pack(fill=tk.X, pady=2)
        create_styled_label(link_frame, text="附加連結 (選填, API 模式):").pack(side=tk.LEFT)
        self.link_url_var = tk.StringVar()
        self.link_entry = create_styled_entry(link_frame, width=50, textvariable=self.link_url_var)
        self.link_entry.pack(side=tk.LEFT, padx=5)
        self.link_note = create_styled_label(link_frame, text="(FB 會自動產生預覽卡片)", font=("Arial", 8))
        self.link_note.pack(side=tk.LEFT)

        # ── 影片 (API 模式) ──
        video_frame = create_styled_frame(p)
        video_frame.pack(fill=tk.X, pady=2)
        create_styled_label(video_frame, text="影片路徑 (選填, API 模式):").pack(side=tk.LEFT)
        self.video_path_var = tk.StringVar()
        self.video_entry = create_styled_entry(video_frame, width=40, textvariable=self.video_path_var)
        self.video_entry.pack(side=tk.LEFT, padx=5)
        create_styled_button(video_frame, text="📁", command=self._select_video, bootstyle="secondary").pack(side=tk.LEFT)
        self.video_note = create_styled_label(video_frame, text="(支援自動分塊上傳)", font=("Arial", 8))
        self.video_note.pack(side=tk.LEFT, padx=5)

        # ── 自動刪除設定 ──
        auto_del_frame = create_styled_frame(p)
        auto_del_frame.pack(fill=tk.X, pady=5)

        self.auto_delete_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(auto_del_frame, text="啟用自動刪除", variable=self.auto_delete_var).pack(side=tk.LEFT)

        # 發文後自動按讚（需要能取得貼文 URL 才能精準按讚）
        self.auto_like_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(auto_del_frame, text="發文後自動按讚", variable=self.auto_like_var).pack(side=tk.LEFT, padx=(10, 0))

        create_styled_label(auto_del_frame, text="  保留時間:").pack(side=tk.LEFT, padx=(10, 0))
        self.retention_var = tk.StringVar(value="168")
        self.retention_spin = ttk.Spinbox(auto_del_frame, from_=1, to=720, width=5, textvariable=self.retention_var)
        self.retention_spin.pack(side=tk.LEFT)
        create_styled_label(auto_del_frame, text="小時").pack(side=tk.LEFT, padx=2)

        del_info = create_styled_label(auto_del_frame, text="", font=("Arial", 8))
        del_info.pack(side=tk.LEFT, padx=10)
        self.retention_var.trace_add("write", lambda *a: self._update_del_info(del_info))
        self._update_del_info(del_info)

        # ── 按讚工具（指定貼文 URL） ──
        like_frame = create_styled_frame(p)
        like_frame.pack(fill=tk.X, pady=(0, 6))
        create_styled_label(like_frame, text="貼文 URL：").pack(side=tk.LEFT)
        self.like_url_var = tk.StringVar()
        create_styled_entry(like_frame, width=55, textvariable=self.like_url_var).pack(side=tk.LEFT, padx=5)
        create_styled_button(like_frame, text="👍 按讚", command=self._on_like_url, bootstyle="info").pack(side=tk.LEFT)

        # ── 排程發文 (日期時間選擇器) ──
        sch_frame = create_styled_frame(p)
        sch_frame.pack(fill=tk.X, pady=5)
        create_styled_label(sch_frame, text="排程發文:").pack(side=tk.LEFT)
        # 日期 (YYYY-MM-DD)
        today_str = datetime.now().strftime("%Y-%m-%d")
        self.schedule_date_var = tk.StringVar(value=today_str)
        self.schedule_date_entry = create_styled_entry(sch_frame, width=12, textvariable=self.schedule_date_var)
        self.schedule_date_entry.pack(side=tk.LEFT, padx=5)
        # 時間
        self.schedule_hour = ttk.Spinbox(sch_frame, from_=0, to=23, width=3, format="%02.0f")
        self.schedule_hour.pack(side=tk.LEFT)
        self.schedule_hour.set("09")
        ttk.Label(sch_frame, text=":").pack(side=tk.LEFT)
        self.schedule_min = ttk.Spinbox(sch_frame, from_=0, to=59, width=3, format="%02.0f")
        self.schedule_min.pack(side=tk.LEFT)
        self.schedule_min.set("00")
        self.schedule_note = create_styled_label(sch_frame, text="  (社團間隔 1~15 分鐘)", font=("Arial", 8))
        self.schedule_note.pack(side=tk.LEFT, padx=5)

        # ── 發送按鈕 ──
        btn_frame = create_styled_frame(p)
        btn_frame.pack(pady=15)
        create_styled_button(btn_frame, text="📤 立即發文", command=self._on_post_general, bootstyle="success").pack(side=tk.LEFT, padx=5)
        create_styled_button(btn_frame, text="🕐 排程發文", command=self._on_schedule_post, bootstyle="info").pack(side=tk.LEFT, padx=5)
        create_styled_button(btn_frame, text="🗑️ 清除全部", command=self._clear_all, bootstyle="secondary").pack(side=tk.LEFT, padx=5)

        # ── TikTok 幻燈片上傳 ──
        self._build_tiktok_section(p)

    def _build_tiktok_section(self, parent):
        """TikTok 幻燈片產生 + 官方 API 上傳區塊"""
        tk_frame = ttk.LabelFrame(parent, text="TikTok Upload")
        tk_frame.pack(fill=tk.X, pady=(15, 5))
        tk_inner = ttk.Frame(tk_frame, padding=8)
        tk_inner.pack(fill=tk.X)

        # 帳號選擇
        row1 = create_styled_frame(tk_frame)
        row1.pack(fill=tk.X, pady=3)
        create_styled_label(row1, text="TikTok 帳號:").pack(side=tk.LEFT)
        self.tiktok_account_var = tk.StringVar()
        self.tiktok_account_combo = ttk.Combobox(
            row1, textvariable=self.tiktok_account_var, state="readonly", width=25
        )
        self.tiktok_account_combo.pack(side=tk.LEFT, padx=5)
        create_styled_button(
            row1, text="🔄", command=self._refresh_tiktok_accounts, bootstyle="secondary"
        ).pack(side=tk.LEFT)
        self._refresh_tiktok_accounts()

        # Hashtag + 每張秒數
        row2 = create_styled_frame(tk_frame)
        row2.pack(fill=tk.X, pady=3)
        create_styled_label(row2, text="Hashtags:").pack(side=tk.LEFT)
        self.tiktok_tags_var = tk.StringVar()
        create_styled_entry(row2, width=30, textvariable=self.tiktok_tags_var).pack(side=tk.LEFT, padx=5)
        create_styled_label(row2, text="每張秒數:").pack(side=tk.LEFT, padx=(10, 0))
        self.tiktok_duration_var = tk.StringVar(value="3")
        ttk.Spinbox(row2, from_=1, to=15, width=5, textvariable=self.tiktok_duration_var).pack(side=tk.LEFT)

        # 動作按鈕 + 狀態
        row3 = create_styled_frame(tk_inner)
        row3.pack(fill=tk.X, pady=3)
        self.tiktok_btn = create_styled_button(
            row3, text="🎬 產生幻燈片並上傳 TikTok",
            command=self._on_tiktok_upload, bootstyle="info",
        )
        self.tiktok_btn.pack(side=tk.LEFT, padx=2)
        self.tiktok_status_var = tk.StringVar(value="就緒")
        ttk.Label(row3, textvariable=self.tiktok_status_var, font=("Arial", 9)).pack(side=tk.LEFT, padx=10)

    def _refresh_tiktok_accounts(self):
        """重新載入 TikTok 帳號清單"""
        _, uploader = _import_tiktok()
        names = [a["nickname"] for a in uploader.list_accounts()]
        self.tiktok_account_combo["values"] = names
        if names and self.tiktok_account_var.get() not in names:
            self.tiktok_account_var.set(names[0])
        elif not names:
            self.tiktok_account_var.set("")

    # ── FB Graph API 模式 ──

    def _on_mode_change(self):
        """切換發文模式時，顯示/隱藏 API Page 選擇器"""
        if self.api_mode_var.get():
            self.api_page_frame.pack(fill=tk.X, pady=2)
        else:
            self.api_page_frame.pack_forget()

    def _refresh_fb_api_pages(self):
        """重新載入 FB Graph API 已設定的粉絲專頁"""
        self._fb_page_mgr = FBPageManager()
        linked_account_id = ""
        if hasattr(self, 'account_var'):
            linked_account_id = self._get_selected_account_id()
        pages = self._fb_page_mgr.list_linked(linked_account_id)
        if not pages:
            # 若無連結的，顯示全部
            pages = self._fb_page_mgr.list_all()
        self.fb_api_pages = {}
        for p in pages:
            label = f"{p.page_name} ({p.page_id})" if p.page_name else p.page_id
            self.fb_api_pages[label] = p.page_id
        vals = list(self.fb_api_pages.keys())
        if hasattr(self, 'api_page_combo'):
            self.api_page_combo["values"] = vals or ["（無 — 請先設定 FB API）"]
            if vals and self.api_page_var.get() not in vals:
                self.api_page_combo.current(0)

    def _post_via_api(self, content: str, image_paths: list[str] = None,
                      video_path: str = "", link_url: str = "",
                      groups: list[str] = None) -> dict:
        """透過 Graph API 發文（背景執行緒安全）"""
        page_display = self.api_page_var.get()
        page_id = self.fb_api_pages.get(page_display, "")
        if not page_id:
            return {"success": False, "error": "未選取 API 粉絲專頁，請先在「檔案 → FB API 設定」中設定"}

        result = post_via_api(page_id, content, image_paths,
                              video_path=video_path, link_url=link_url, groups=groups)
        if result.get("success"):
            ptype = result.get("type", "post")
            log("GRAPH", page_id, f"API 發文成功 ({ptype}) post_id={result.get('post_id', '')}", "✅")
        else:
            log("GRAPH", page_id, f"API 發文失敗: {result.get('error', '')}", "❌")
        return result

    def _build_market_tab(self, parent):
        create_styled_label(parent, text="選擇帳號:").pack(anchor=tk.W)
        market_display = list(self.account_map.keys())
        init_market = market_display[0] if market_display else ""
        self.market_account_var = tk.StringVar(value=init_market)
        ttk.Combobox(
            parent, textvariable=self.market_account_var,
            values=market_display, state="readonly", width=40
        ).pack(fill=tk.X, pady=5)

        fields = [("商品標題:", "title"), ("價格:", "price"), ("地區:", "location")]
        self.market_entries = {}
        for label_text, key in fields:
            create_styled_label(parent, text=label_text).pack(anchor=tk.W, pady=(10, 0))
            entry = create_styled_entry(parent, width=50)
            entry.pack(fill=tk.X, pady=2)
            self.market_entries[key] = entry

        create_styled_label(parent, text="商品描述:").pack(anchor=tk.W, pady=(10, 0))
        self.market_desc = tk.Text(parent, height=4, bg="#2b2b2b", fg="#ffffff", insertbackground="white")
        self.market_desc.pack(fill=tk.BOTH, pady=5)

        # Marketplace 也加 AI 工具列
        tool_row = create_styled_frame(parent)
        tool_row.pack(fill=tk.X, pady=5)
        create_styled_button(tool_row, text="🤖 AI 生成描述", command=self._on_market_ai_generate, bootstyle="primary").pack(side=tk.LEFT, padx=2)
        create_styled_button(tool_row, text="📁 選圖片", command=self._select_images, bootstyle="secondary").pack(side=tk.LEFT, padx=2)
        self.market_img_label = create_styled_label(tool_row, text="未選圖片")
        self.market_img_label.pack(side=tk.LEFT, padx=10)

        btn_frame = create_styled_frame(parent)
        btn_frame.pack(pady=15)
        create_styled_button(btn_frame, text="📤 發布到 Marketplace", command=self._on_post_marketplace, bootstyle="success").pack(side=tk.LEFT, padx=5)

    # ── Helper Methods ──

    def _get_selected_account_id(self) -> str:
        """從下拉選單的顯示名稱查出 account_id"""
        display = self.account_var.get()
        return self.account_map.get(display, display)

    def _load_header_footer(self):
        """載入當前帳號的 Header/Footer（若無帳號專屬設定則用全域預設）"""
        acc_id = self._get_selected_account_id()
        settings = self._load_global_settings()
        global_h = settings.get("header", "")
        global_f = settings.get("footer", "")

        if acc_id and acc_id != "無帳號":
            acc_h = self.template_mgr.get_header(acc_id) or global_h
            acc_f = self.template_mgr.get_footer(acc_id) or global_f
            self.header_var.set(acc_h)
            self.footer_var.set(acc_f)
        else:
            self.header_var.set(global_h)
            self.footer_var.set(global_f)

    # ── 全域 Header/Footer 設定 ──

    def _get_global_settings_path(self):
        data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
        os.makedirs(data_dir, exist_ok=True)
        return os.path.join(data_dir, "global_settings.json")

    def _load_global_settings(self) -> dict:
        path = self._get_global_settings_path()
        if not os.path.exists(path):
            return {}
        try:
            import json
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_global_settings(self, settings: dict):
        path = self._get_global_settings_path()
        try:
            import json
            with open(path, "w", encoding="utf-8") as f:
                json.dump(settings, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _load_global_header(self):
        """將全域 Header 填入目前輸入框"""
        settings = self._load_global_settings()
        if settings.get("header"):
            self.header_var.set(settings["header"])

    def _load_global_footer(self):
        """將全域 Footer 填入目前輸入框"""
        settings = self._load_global_settings()
        if settings.get("footer"):
            self.footer_var.set(settings["footer"])

    def _on_global_settings(self):
        """開啟全域 Header/Footer 設定對話框"""
        settings = self._load_global_settings()

        dialog = tk.Toplevel(self)
        dialog.title("⚙️ 全域 Header / Footer 設定")
        dialog.geometry("550x320")
        dialog.transient(self)
        dialog.grab_set()
        dialog.configure(bg="#2b2b2b")

        # 說明
        create_styled_label(
            dialog,
            text="設定後，每次開啟 App 或載入文案時會自動填入。\n"
                 "帳號專屬 Header/Footer 會優先於此全域設定。",
            font=("Arial", 8),
        ).pack(pady=(10, 5))

        # Header
        create_styled_label(dialog, text="全域 Header (頁首):", font=("Arial", 9, "bold")).pack(anchor=tk.W, padx=10)
        header_var = tk.StringVar(value=settings.get("header", ""))
        header_ent = create_styled_entry(dialog, width=60, textvariable=header_var)
        header_ent.pack(fill=tk.X, padx=10, pady=(2, 8))

        # Footer
        create_styled_label(dialog, text="全域 Footer (頁尾):", font=("Arial", 9, "bold")).pack(anchor=tk.W, padx=10)
        footer_var = tk.StringVar(value=settings.get("footer", ""))
        footer_ent = create_styled_entry(dialog, width=60, textvariable=footer_var)
        footer_ent.pack(fill=tk.X, padx=10, pady=(2, 8))

        # Checkboxes for auto-behavior
        auto_apply_var = tk.BooleanVar(value=settings.get("auto_apply", True))
        auto_apply_cb = ttk.Checkbutton(
            dialog,
            text="一鍵生成物件文案時自動使用全域 Header/Footer",
            variable=auto_apply_var,
        )
        auto_apply_cb.pack(anchor=tk.W, padx=10, pady=5)

        # Save button
        def do_save():
            settings["header"] = header_var.get().strip()
            settings["footer"] = footer_var.get().strip()
            settings["auto_apply"] = auto_apply_var.get()
            self._save_global_settings(settings)
            log("POST", "global_settings", "已儲存全域 Header/Footer", "💾")
            self.status_var.set("✅ 全域 Header/Footer 已儲存")
            # 立即套用
            self._load_header_footer()
            dialog.destroy()

        btn_frame = create_styled_frame(dialog)
        btn_frame.pack(pady=15)
        create_styled_button(btn_frame, text="💾 儲存並套用", command=do_save, bootstyle="success").pack(padx=5)
        create_styled_button(btn_frame, text="取消", command=dialog.destroy, bootstyle="secondary").pack(padx=5)

    # ═══════════════════════════════════════════════════════════
    #   Pro 模板區 — 欄位渲染 / 預覽 / 群組組合
    # ═══════════════════════════════════════════════════════════

    def _on_template_change(self):
        """切換模板時重建欄位"""
        tmpl_name = self.tmpl_var.get()
        tmpl = get_template(tmpl_name)
        if not tmpl:
            return

        # 清除舊欄位
        for w in self.tmpl_field_widgets.values():
            w.destroy()
        self.tmpl_field_widgets.clear()
        for child in self.tmpl_fields_frame.winfo_children():
            child.destroy()

        # 建立新欄位
        fields = tmpl.get("fields", [])
        for i, fdef in enumerate(fields):
            row = i // 2
            col = i % 2
            key = fdef["key"]
            label = fdef.get("label", key)
            multiline = fdef.get("multiline", False)

            if multiline:
                # intro: 放整行 + AI 按鈕
                f = create_styled_frame(self.tmpl_fields_frame)
                f.grid(row=row + 1, column=0, columnspan=2, sticky="ew", pady=2, padx=5)
                lbl_row = create_styled_frame(f)
                lbl_row.pack(fill=tk.X)
                create_styled_label(lbl_row, text=f"{label}:").pack(side=tk.LEFT)
                create_styled_button(lbl_row, text="🧠 AI 生成", command=self._on_ai_intro, bootstyle="warning", width=10).pack(side=tk.LEFT, padx=10)
                txt = tk.Text(f, height=5, bg="#2b2b2b", fg="#ffffff", insertbackground="white", font=("Arial", 9))
                txt.pack(fill=tk.X, pady=1)
                txt.bind("<KeyRelease>", lambda e: self._update_preview())
                txt.bind("<<Modified>>", lambda e: self._on_text_modified(e))
                self.tmpl_field_widgets[key] = txt
            else:
                f = create_styled_frame(self.tmpl_fields_frame)
                f.grid(row=row, column=col, sticky="ew", padx=(5, 15), pady=2)
                f.columnconfigure(1, weight=1)
                create_styled_label(f, text=f"{label}:", font=("Arial", 8)).pack(side=tk.LEFT)
                var = tk.StringVar()
                entry = create_styled_entry(f, width=18, textvariable=var)
                entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 0))
                var.trace_add("write", lambda *a, k=key: self.after(50, self._update_preview))
                self.tmpl_field_widgets[key] = var

        self._update_preview()

    def _get_template_data(self) -> dict:
        """從 UI 欄位讀取模板 data"""
        data = {}
        for key, widget in self.tmpl_field_widgets.items():
            if isinstance(widget, tk.StringVar):
                data[key] = widget.get().strip()
            elif isinstance(widget, tk.Text):
                data[key] = widget.get("1.0", tk.END).strip()
        return data

    def _set_template_data(self, data: dict):
        """將 dict 填入 UI 欄位"""
        for key, val in data.items():
            w = self.tmpl_field_widgets.get(key)
            if isinstance(w, tk.StringVar):
                w.set(str(val))
            elif isinstance(w, tk.Text):
                w.delete("1.0", tk.END)
                w.insert("1.0", str(val))
        # 填入後等 50ms 讓 Text widget 更新 → refresh preview
        self.after(50, self._update_preview)

    def _on_text_modified(self, event):
        """Text widget 內容變更時 (含程式設定) → 更新預覽"""
        widget = event.widget
        if hasattr(widget, 'edit_modified') and widget.edit_modified():
            widget.edit_modified(False)
            self._update_preview()

    def _update_preview(self):
        """即時更新預覽面板"""
        tmpl_name = self.tmpl_var.get()
        data = self._get_template_data()
        header = self.header_var.get().strip()
        footer = self.footer_var.get().strip()
        post = generate_post(data, tmpl_name, header=header, footer=footer)
        text = post.get("text", "")

        self.preview_text.config(state=tk.NORMAL)
        self.preview_text.delete("1.0", tk.END)
        self.preview_text.insert("1.0", text)
        self.preview_text.config(state=tk.DISABLED)

    def _on_ai_intro(self):
        """🧠 AI 生成介紹：讀取已填欄位 → 用 Ollama 生成吸引人的介紹段落"""
        data = self._get_template_data()
        title = data.get("title", "").strip()
        if not title:
            self.status_var.set("⚠️ 請先填寫標題再生成介紹")
            return

        self.status_var.set("⏳ AI 正在生成介紹...")
        self.update()

        def worker():
            try:
                prompt = _build_intro_prompt(data)
                intro = ""
                ollama_ok = is_ollama_running()
                if ollama_ok:
                    try:
                        import requests
                        resp = requests.post(
                            "http://localhost:11434/api/generate",
                            json={"model": "llama3.2", "prompt": prompt, "stream": False, "temperature": 0.8},
                            timeout=45,
                        )
                        if resp.status_code == 200:
                            intro = resp.json().get("response", "").strip()
                    except Exception:
                        pass

                if not intro:
                    # Fallback: 根據欄位組合
                    parts = []
                    if title:
                        parts.append(f"{title}，" if "，" not in title else title)
                    loc = data.get("location", "").strip()
                    if loc:
                        loc_short = loc.replace("桃園市", "").replace("中壢區", "")
                        if loc_short:
                            parts.append(f"位於{loc_short}，")
                    rooms = data.get("rooms", "").strip()
                    size = data.get("size", "").strip()
                    if rooms and size:
                        parts.append(f"{size}{rooms}，")
                    ptype = data.get("type", "").strip()
                    if ptype:
                        parts.append(f"{ptype}物件，")
                    parking = data.get("parking", "").strip()
                    if parking and parking != "無車位":
                        parts.append("附車位，")
                    age = data.get("age", "").strip()
                    if age:
                        parts.append(f"屋齡{age}，")
                    parts.append("生活機能完善，歡迎預約賞屋。")
                    intro = "".join(parts)

                final = intro.strip()
                self.after(0, lambda: self._set_template_data({"intro": final}))
                self.after(0, self._update_preview)
                self.after(0, lambda: self.status_var.set("✅ 介紹已生成"))

            except Exception as e:
                self.after(0, lambda: self.status_var.set(f"❌ {str(e)[:40]}"))

        threading.Thread(target=worker, daemon=True).start()

    def _on_edit_template(self):
        """編輯目前模板"""
        from gui.pro_template_dialog import TemplateEditorDialog
        tmpl_name = self.tmpl_var.get()
        tmpl = get_template(tmpl_name)
        if not tmpl:
            return
        TemplateEditorDialog(self, tmpl, on_save=self._on_template_saved)

    def _on_edit_profile(self):
        """開啟經紀人資料編輯器"""
        from gui.agent_profile_dialog import AgentProfileDialog
        AgentProfileDialog(self)

    def _on_template_saved(self, name: str):
        """模板存檔後回呼 — 更新下拉選單"""
        self.tmpl_names = [t["name"] for t in list_templates()]
        self.tmpl_combo["values"] = self.tmpl_names
        self.tmpl_var.set(name)
        self._on_template_change()

    def _on_save_group_set(self):
        """將目前選取的社團存成組合"""
        set_name = self.group_set_var.get()
        selected = [self.groups_listbox.get(i) for i in self.groups_listbox.curselection()]
        save_group_set(set_name, selected)
        self.status_var.set(f"✅ {set_name} 已儲存 ({len(selected)} 個社團)")

    def _on_group_set_change(self):
        """選取社團組合 → 自動勾選對應社團"""
        set_name = self.group_set_var.get()
        targets = get_group_set(set_name)
        self.groups_listbox.selection_clear(0, tk.END)
        for i in range(self.groups_listbox.size()):
            if self.groups_listbox.get(i) in targets:
                self.groups_listbox.selection_set(i)
        self._update_group_selection_count()

    def _update_del_info(self, label):
        hours = self.retention_var.get()
        try:
            h = int(hours)
            del_time = datetime.now() + timedelta(hours=h)
            days = h // 24
            if days >= 1:
                label.config(text=f"預計刪除: {del_time.strftime('%m/%d %H:%M')} ({days} 天後)")
            else:
                label.config(text=f"預計刪除: {del_time.strftime('%m/%d %H:%M')} ({h} 小時後)")
        except ValueError:
            pass

    def _on_ai_generate(self):
        """一鍵生成：貼網址 → 提取物件資訊 → 自動填入模板欄位

        如果有 URL → 自動提取 + 填入
        無 URL → 開對話框讓用戶手動輸入
        """
        url = self.scrape_url_var.get().strip()
        has_url = bool(url) and url != "貼上網址爬取圖片..." and url.startswith("http")

        if has_url:
            settings = self._load_global_settings()
            if settings.get("auto_apply", True):
                if not self.header_var.get().strip() and settings.get("header"):
                    self.header_var.set(settings["header"])
                if not self.footer_var.get().strip() and settings.get("footer"):
                    self.footer_var.set(settings["footer"])

            self.status_var.set("⏳ 正在提取物件資訊...")
            self.update()

            def worker():
                try:
                    info = extract_property_info(url)
                    if not info or not any(info.values()):
                        self.after(0, lambda: self.status_var.set("❌ 無法提取物件資訊"))
                        return

                    # 映射 scraper keys → template keys
                    # 舊版 scraper: "description" → template uses "intro"
                    # 新版 multi_site_scraper: already returns "intro"
                    if "description" in info and not info.get("intro"):
                        info["intro"] = str(info.pop("description"))
                    elif "description" in info:
                        del info["description"]

                    # 自動偵測模板類型：依關鍵字切換
                    ptype = (info.get("type") or "").lower()
                    title_lower = (info.get("title") or "").lower()
                    if any(w in title_lower for w in ("土地","農地","建地","工業地","山坡地")):
                        self.after(0, lambda: self.tmpl_var.set("土地"))
                        self.after(0, self._on_template_change)
                    elif any(w in title_lower for w in ("廠房","工廠","廠辨")) or any(w in ptype for w in ("廠房","工廠")):
                        self.after(0, lambda: self.tmpl_var.set("廠房"))
                        self.after(0, self._on_template_change)

                    # 填入模板欄位（只填存在的 key）
                    self.after(0, lambda: self._set_template_data(info))
                    self.after(0, self._update_preview)

                    filled = len([v for v in info.values() if v])
                    self.after(0, lambda: self.status_var.set(f"✅ 已提取 {filled} 項，請檢查預覽"))

                    # 順便爬取圖片
                    self.after(0, lambda: self._on_scrape_images())

                except Exception as e:
                    self.after(0, lambda: self.status_var.set(f"❌ 錯誤: {str(e)[:50]}"))

            threading.Thread(target=worker, daemon=True).start()
        else:
            self._show_manual_ai_dialog()

    def _on_market_ai_generate(self):
        """Marketplace 的 AI 生成"""
        title = self.market_entries["title"].get().strip()
        price = self.market_entries["price"].get().strip()
        loc = self.market_entries["location"].get().strip()
        desc = self.market_desc.get("1.0", tk.END).strip()

        if not title or not price:
            messagebox.showwarning("警告", "請先輸入商品標題和價格")
            return

        result = generate_ad(title, price, loc, desc)
        text = result.get("text", "")
        self.market_desc.delete("1.0", tk.END)
        self.market_desc.insert("1.0", text)

    def _show_manual_ai_dialog(self):
        """無 URL 時顯示手動輸入對話框 — 填寫標題/價格/地點後生成文案"""
        dialog = tk.Toplevel(self)
        dialog.title("手動輸入 — AI 生成文案")
        dialog.geometry("450x350")
        dialog.transient(self)
        dialog.grab_set()
        dialog.configure(bg="#2b2b2b")

        create_styled_label(dialog, text="商品標題:").pack(pady=(10, 0))
        title_ent = create_styled_entry(dialog, width=45)
        title_ent.pack(pady=2)

        create_styled_label(dialog, text="價格:").pack(pady=(5, 0))
        price_ent = create_styled_entry(dialog, width=45)
        price_ent.pack(pady=2)

        create_styled_label(dialog, text="地點:").pack(pady=(5, 0))
        loc_ent = create_styled_entry(dialog, width=45)
        loc_ent.pack(pady=2)

        create_styled_label(dialog, text="描述 (選填):").pack(pady=(5, 0))
        desc_text = tk.Text(dialog, height=4, bg="#2b2b2b", fg="#ffffff", insertbackground="white")
        desc_text.pack(pady=2, padx=10, fill=tk.X)

        ollama_ok = is_ollama_running()
        status_txt = "✅ Ollama 連線中" if ollama_ok else "⚠️ Ollama 離線 (將使用模板)"
        create_styled_label(dialog, text=status_txt, font=("Arial", 8)).pack(pady=5)

        def do_generate():
            title = title_ent.get().strip()
            price = price_ent.get().strip()
            loc = loc_ent.get().strip()
            desc = desc_text.get("1.0", tk.END).strip()
            if not title or not price:
                messagebox.showwarning("警告", "請至少輸入標題和價格")
                return

            result = generate_ad(title, price, loc, desc)
            text = result.get("text", "")

            self.content_text.delete("1.0", tk.END)
            self.content_text.insert("1.0", text)

            fallback = result.get("fallback", False)
            self.ai_status_label.config(text="✅ 已生成" if not fallback else "⚠️ 使用模板")
            self.status_var.set(f"✅ AI 文案已生成 ({'Ollama' if not fallback else '模板'})")
            dialog.destroy()

        create_styled_button(dialog, text="✨ 生成文案", command=do_generate, bootstyle="success").pack(pady=15)

    def _on_open_url(self):
        """用系統瀏覽器打開網址（讓用戶確認內容）"""
        url = self.scrape_url_var.get().strip()
        if not url or url == "貼上網址爬取圖片...":
            messagebox.showwarning("警告", "請先貼上網址")
            return
        import webbrowser
        webbrowser.open(url)

    def _on_scrape_images(self, event=None):
        """從網址爬取圖片（背景執行緒不卡 UI）"""
        url = self.scrape_url_var.get().strip()
        if not url or url == "貼上網址爬取圖片...":
            messagebox.showwarning("警告", "請貼上網址")
            return

        self.status_var.set("⏳ 正在爬取圖片...")
        self.update()

        def worker():
            try:
                images = scrape_images_from_url(url, max_images=5)
                if images:
                    self.after(0, lambda: setattr(self, 'scraped_images', images))
                    self.after(0, self._update_img_label)
                    self.after(0, lambda: self.status_var.set(f"✅ 成功爬取 {len(images)} 張圖片"))
                else:
                    self.after(0, lambda: self.status_var.set("❌ 無法爬取圖片 — 網頁可能沒有圖片、防盜連，或網址無效"))
            except Exception as e:
                self.after(0, lambda: self.status_var.set(f"❌ 爬取失敗: {str(e)[:50]}"))

        threading.Thread(target=worker, daemon=True).start()

    def _select_images(self):
        """選擇本機圖片"""
        files = filedialog.askopenfilenames(
            title="選擇圖片",
            filetypes=[("圖片檔案", "*.jpg *.jpeg *.png *.gif *.webp")],
        )
        if files:
            self.selected_images = list(files)
            self._update_img_label()

    def _select_video(self):
        """選擇影片檔案"""
        file = filedialog.askopenfilename(
            title="選擇影片",
            filetypes=[("影片檔案", "*.mp4 *.mov *.avi *.mkv *.webm")],
        )
        if file:
            self.video_path_var.set(file)

    def _update_img_label(self):
        local = len(self.selected_images)
        scraped = len(self.scraped_images)
        parts = []
        if local:
            parts.append(f"本機 {local} 張")
        if scraped:
            parts.append(f"爬取 {scraped} 張")
        total = local + scraped
        text = f"已選 {total} 張圖片" + (f" ({', '.join(parts)})" if parts else "")
        self.img_label.config(text=text)
        if hasattr(self, 'market_img_label'):
            self.market_img_label.config(text=text)

    def _get_all_images(self) -> list:
        """取得所有圖片（本機 + 爬取）"""
        return self.selected_images + self.scraped_images

    def _on_tiktok_upload(self):
        """產生幻燈片並透過官方 API 上傳 TikTok（背景執行緒）"""
        nickname = self.tiktok_account_var.get().strip()
        if not nickname:
            messagebox.showwarning("警告", "請先在「檔案 → TikTok 設定」新增帳號")
            return

        text = self.content_text.get("1.0", tk.END).strip()
        images = self._get_all_images()
        if not images:
            messagebox.showwarning("警告", "請先選擇或爬取至少一張圖片")
            return
        if len(images) > 5:
            images = images[:5]

        try:
            duration = int(self.tiktok_duration_var.get())
        except ValueError:
            duration = 3

        tags_raw = self.tiktok_tags_var.get().strip()
        tags = [t for t in tags_raw.replace("，", " ").split() if t] if tags_raw else []
        title = text.split("\n")[0][:100] if text else "分享"

        self.tiktok_btn.config(state=tk.DISABLED)
        self._set_tiktok_status("⏳ 正在產生幻燈片...")

        def worker():
            slideshow, uploader = _import_tiktok()
            try:
                video_path = slideshow.create_slideshow(images, text, duration)
                self._set_tiktok_status("⏳ 正在上傳 TikTok...")
                result = uploader.upload_video(
                    nickname=nickname, video_path=video_path,
                    title=title, tags=tags,
                )
                if result.get("success"):
                    pid = result.get("publish_id", "")
                    log("TIKTOK", nickname, f"上傳: {title}", "✅ 已送出", detail=f"publish_id={pid}")
                    self._set_tiktok_status(f"✅ 已送出 (publish_id: {pid[:12]}...)")
                else:
                    err = result.get("error", "未知錯誤")
                    log("TIKTOK", nickname, f"上傳: {title}", "❌ 失敗", detail=err)
                    # 顯示完整錯誤資訊（不截斷）
                    short_err = err[:80]
                    # 給用戶可操作的建議
                    if "log_pb" in err:
                        short_err += " — session_id 可能過期，請重新取得"
                    elif "403" in err or "401" in err:
                        short_err += " — 權限不足，session_id 可能無效"
                    self._set_tiktok_status(f"❌ {short_err}")
            except Exception as e:
                log("TIKTOK", nickname, f"上傳: {title}", "❌ 失敗", detail=str(e))
                self._set_tiktok_status(f"❌ 錯誤: {str(e)[:60]}")
            finally:
                self.after(0, lambda: self.tiktok_btn.config(state=tk.NORMAL))

        threading.Thread(target=worker, daemon=True).start()

    def _set_tiktok_status(self, text: str):
        """執行緒安全地更新 TikTok 狀態標籤"""
        self.after(0, lambda: self.tiktok_status_var.set(text))

    def _on_post_general(self):
        """執行發文 — 立即發送"""
        self._do_post(schedule=False)

    def _on_schedule_post(self):
        """排程發文 — 在指定日期時間自動發送"""
        self._do_post(schedule=True)

    def _on_like_url(self):
        """立即對指定貼文 URL 按讚（使用目前選取的帳號）"""
        url = (getattr(self, "like_url_var", tk.StringVar()).get() or "").strip()
        if not url:
            messagebox.showwarning("警告", "請先貼上要按讚的貼文 URL")
            return

        account_id = self._get_selected_account_id()
        if not self.engine:
            self.status_var.set("⚠️ 發文引擎未啟動，無法按讚")
            return

        self.status_var.set("⏳ 正在按讚...")

        def on_ok(result):
            if result and result.get("success"):
                self.status_var.set("✅ 已按讚")
                log("INTERACT", account_id, f"按讚: {url[:60]}", "✅")
            else:
                self.status_var.set(f"❌ 按讚失敗: {(result or {}).get('error', '未知')}")
                log("INTERACT", account_id, f"按讚失敗: {url[:60]}", "❌")

        def on_err(result):
            self.status_var.set(f"❌ 按讚失敗: {(result or {}).get('error', '未知')}")
            log("INTERACT", account_id, f"按讚失敗: {url[:60]}", "❌")

        self.engine.like_now(account_id=account_id, post_url=url, callback=on_ok, error_callback=on_err)

    def _do_post(self, schedule: bool = False):
        """發文共用邏輯（立即 / 排程）— 使用 Pro 模板"""
        account_id = self._get_selected_account_id()
        header = self.header_var.get().strip()
        footer = self.footer_var.get().strip()

        # 從模板欄位產生文案
        tmpl_name = self.tmpl_var.get()
        data = self._get_template_data()
        if not data.get("title", "").strip() and not data.get("price", "").strip():
            messagebox.showwarning("警告", "請至少填入標題和價格")
            return

        post = generate_post(data, tmpl_name, header=header, footer=footer)
        full_text = post.get("text", "")
        if not full_text:
            messagebox.showwarning("警告", "無法生成文案")
            return

        # 從 listbox 讀取已選取的社團（有 URL 的優先）
        selected_idx = self.groups_listbox.curselection()
        if not selected_idx:
            # 沒選任何社團 → 發到個人頁面
            groups = None
        else:
            groups = self._get_group_urls()
            if not groups:
                messagebox.showwarning("警告", "請在社團清單中選取要發送的社團，或取消選取發到個人頁面")
                return
        images = self._get_all_images()

        # 計算預計刪除時間
        delete_at = ""
        if self.auto_delete_var.get():
            try:
                hours = int(self.retention_var.get())
                del_time = datetime.now() + timedelta(hours=hours)
                delete_at = del_time.strftime("%Y-%m-%d %H:%M")
            except ValueError:
                pass

        # ════════════════════════════════════════════════════
        # 模式 A: API (Graph) 發文
        # ════════════════════════════════════════════════════
        if self.api_mode_var.get():
            video_path = self.video_path_var.get().strip()
            link_url = self.link_url_var.get().strip()

            self.status_var.set("⏳ 正在透過 Graph API 發送...")
            self.update()

            def worker():
                result = self._post_via_api(full_text, images,
                                            video_path=video_path,
                                            link_url=link_url,
                                            groups=groups)
                self.after(0, lambda: self._on_api_post_result(result, delete_at))

            import threading
            threading.Thread(target=worker, daemon=True).start()
            return

        # ════════════════════════════════════════════════════
        # 排程發文：一組文案 → N 個社團 → N 個 CronJob (間隔 1-15min)
        # ════════════════════════════════════════════════════
        if schedule:
            if self.api_mode_var.get():
                messagebox.showwarning("警告", "排程發文目前僅支援瀏覽器模式")
                return

            try:
                date_str = self.schedule_date_var.get()
                hour = int(self.schedule_hour.get())
                minute = int(self.schedule_min.get())
                # 解析日期
                sch_date = datetime.strptime(date_str, "%Y-%m-%d")
                base_time = sch_date.replace(hour=hour, minute=minute)
                now = datetime.now()

                # 如果排程時間已過，設為明天
                if base_time <= now:
                    messagebox.showwarning("警告", "排程時間已過，請選擇未來時間")
                    return
            except Exception as e:
                messagebox.showwarning("警告", f"排程時間格式錯誤: {e}")
                return

            # 記錄日誌
            group_str = ", ".join(groups) if groups else "個人頁面"
            detail = f"排程發送 →「{group_str}」@ {base_time.strftime('%m/%d %H:%M')}"
            log("POST", account_id, detail, "🕐 已排程", schedule_delete_at=delete_at)

            if self.engine:
                from core.engine import PostTask
                import uuid, random as _random
                import json as _json

                # 儲存排程參數到檔案（供每個子任務讀取）
                schedule_data = {
                    "account_id": account_id,
                    "content": full_text,
                    "images": images,
                    "groups": groups or [],
                    "delete_at": delete_at,
                    "retention_hours": int(self.retention_var.get()) if self.auto_delete_var.get() else 0,
                    "auto_like": bool(self.auto_like_var.get()),
                }
                data_path = os.path.join(
                    os.path.dirname(os.path.dirname(__file__)), "data", "pending_schedule.json"
                )

                try:
                    with open(data_path, "r", encoding="utf-8") as f:
                        pending = _json.load(f)
                except (FileNotFoundError, _json.JSONDecodeError):
                    pending = []

                pending.append(schedule_data)
                with open(data_path, "w", encoding="utf-8") as f:
                    _json.dump(pending, f, ensure_ascii=False, indent=2)

                batch_id = str(uuid.uuid4())[:8]

                if groups:
                    # 每個社團一個 cron job，間隔 1~15 分鐘隨機
                    offset_min = 0
                    for g in groups:
                        job_min = (minute + offset_min) % 60
                        job_hour = hour + (minute + offset_min) // 60
                        job_day = sch_date.day
                        job_month = sch_date.month

                        # Handle hour overflow
                        if job_hour >= 24:
                            job_hour = job_hour % 24
                            job_day += 1

                        cron = f"{job_min} {job_hour} {job_day} {job_month} *"
                        job_id = f"sch_{batch_id}_{job_hour:02d}{job_min:02d}"
                        # 寫入排程任務
                        job = ScheduleJob(
                            job_id=job_id,
                            account_id=account_id,
                            job_type="post",
                            cron_expr=cron,
                            params={
                                "content": full_text,
                                "images": images,
                                "groups": [g],  # 單一社團
                                "delete_at": delete_at,
                                "retention_hours": int(self.retention_var.get()) if self.auto_delete_var.get() else 0,
                                "auto_like": bool(self.auto_like_var.get()),
                                "job_id": job_id,  # 供回呼自動移除
                            },
                        )
                        self.scheduler.add_job(job)

                        offset_min += _random.randint(1, 15)
                
                else:
                    # 個人頁面只有一個 job
                    job_id = f"sch_{batch_id}_wall"
                    cron = f"{minute} {hour} {sch_date.day} {sch_date.month} *"
                    job = ScheduleJob(
                        job_id=job_id,
                        account_id=account_id,
                        job_type="post",
                        cron_expr=cron,
                        params={
                            "content": full_text,
                            "images": images,
                            "groups": None,
                            "delete_at": delete_at,
                            "retention_hours": int(self.retention_var.get()) if self.auto_delete_var.get() else 0,
                            "auto_like": bool(self.auto_like_var.get()),
                            "job_id": job_id,  # 供回呼自動移除
                        },
                    )
                    self.scheduler.add_job(job)

                group_count = len(groups) if groups else 1
                total_min = ((group_count - 1) * _random.randint(1, 15)) if groups else 0
                self.status_var.set(
                    f"🕐 已排程 {group_count} 篇貼文 (首篇@{base_time.strftime('%m/%d %H:%M')}, 總長約{total_min}分)"
                )
                self._clear_all()
            else:
                self.status_var.set("⚠️ 排程引擎未啟動")
            return

        # ════════════════════════════════════════════════════
        # 模式 B: Browser (Playwright) 立即發文
        # ════════════════════════════════════════════════════
        # 記錄日誌
        group_str = ", ".join(groups) if groups else "個人頁面"
        detail = f"發送到「{group_str}」"
        log("POST", account_id, detail, "✅ 已佇列", schedule_delete_at=delete_at)

        # 儲存活頁簿待刪除記錄
        if delete_at and self.auto_delete_var.get():
            from core.auto_cleaner import add_pending_delete
            for g in (groups or [None]):
                gurl = ""
                gdetail = detail
                if g:
                    # 如果是 URL 就直接存，是名稱就留空
                    if "facebook.com/groups/" in g:
                        gurl = g
                    gdetail = f"發送到「{g}」"
                add_pending_delete(
                    account_id=account_id,
                    delete_at=delete_at,
                    detail=gdetail,
                    group_url=gurl,
                    retention_hours=int(self.retention_var.get()),
                )

        self.status_var.set(f"⏳ 正在發送中... (將於 {delete_at or '手動'} 刪除)")

        if self.engine:
            def on_success(result):
                self.status_var.set(f"✅ 發送成功! (將於 {delete_at or '手動'} 刪除)")
                self._add_to_website(data, tmpl_name, images)
                self._clear_all()

            def on_error(result):
                self.status_var.set(f"❌ 發送失敗: {result.get('error', '未知錯誤')}")

            self.engine.post_now(
                account_id=account_id,
                content=full_text,
                images=images,
                groups=groups,
                delete_at=delete_at,
                detail=detail,
                auto_like=bool(self.auto_like_var.get()),
                callback=on_success,
                error_callback=on_error,
            )
        else:
            self.status_var.set(f"✅ 發文指令已排入佇列 (將於 {delete_at or '手動'} 刪除)")

    def _add_to_website(self, data: dict, tmpl_name: str, images: list):
        """發文成功後 → 將物件加入個人網站 listings.json + 複製圖片"""
        import shutil
        site_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "fb_property_site")
        listings_path = os.path.join(site_dir, "data", "listings.json")
        images_dir = os.path.join(site_dir, "images")
        os.makedirs(images_dir, exist_ok=True)

        # 讀取現有 listings
        listings = []
        if os.path.exists(listings_path):
            try:
                with open(listings_path, "r", encoding="utf-8") as f:
                    listings = json.load(f)
            except Exception:
                listings = []

        # 複製第一張圖片 (如果有)
        image_file = ""
        if images:
            src = images[0]
            if os.path.isfile(src):
                ext = os.path.splitext(src)[1] or ".jpg"
                dst_name = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{len(listings)}{ext}"
                dst = os.path.join(images_dir, dst_name)
                try:
                    shutil.copy2(src, dst)
                    image_file = dst_name
                except Exception:
                    pass

        # 建立 listing entry
        entry = {
            "template": tmpl_name,
            "title": data.get("title", ""),
            "price": data.get("price", ""),
            "location": data.get("location", ""),
            "size": data.get("size", ""),
            "rooms": data.get("rooms", ""),
            "type": data.get("type", ""),
            "floor": data.get("floor", ""),
            "age": data.get("age", ""),
            "parking": data.get("parking", ""),
            "orientation": data.get("orientation", ""),
            "road_width": data.get("road_width", ""),
            "land_size": data.get("land_size", ""),
            "intro": data.get("intro", ""),
            "image": image_file,
            "date": datetime.now().isoformat(),
        }
        # 移除空白值
        entry = {k: v for k, v in entry.items() if v}

        listings.append(entry)

        try:
            with open(listings_path, "w", encoding="utf-8") as f:
                json.dump(listings, f, ensure_ascii=False, indent=2)
            log("WEBSITE", tmpl_name, f"已加入網站 listings ({entry.get('title','')})", "🌐")
        except Exception as e:
            log("WEBSITE", tmpl_name, f"寫入失敗: {e}", "❌")

    def _on_api_post_result(self, result: dict, delete_at: str):
        """API 發文完成後的 UI 更新"""
        if result.get("success"):
            post_id = result.get("post_id", "")
            self.status_var.set(f"✅ Graph API 發送成功! (ID: {post_id}) (將於 {delete_at or '手動'} 刪除)")
            self._add_to_website(self._get_template_data(), self.tmpl_var.get(), self._get_all_images())
            self._clear_all()
        else:
            err = result.get("error", "未知錯誤")
            self.status_var.set(f"❌ Graph API 發送失敗: {err}")
            messagebox.showerror("發文失敗", f"Graph API 錯誤:\n{err}")

    def _on_post_marketplace(self):
        """發布到 Marketplace — 透過 SessionManager"""
        display = self.market_account_var.get()
        account_id = self.account_map.get(display, display)
        title = self.market_entries["title"].get().strip()
        price = self.market_entries["price"].get().strip()
        location = self.market_entries["location"].get().strip()
        desc = self.market_desc.get("1.0", tk.END).strip()

        if not title or not price:
            messagebox.showwarning("警告", "請輸入商品標題和價格")
            return

        images = self._get_all_images()
        log("POST", account_id, f"Marketplace: {title} / {price}", "✅ 已佇列")
        self.status_var.set("⏳ 正在發布到 Marketplace...")

        if self.engine:
            def on_success(result):
                self.status_var.set(f"✅ Marketplace 發布成功: {title}")
                self._clear_all()

            def on_error(result):
                self.status_var.set(f"❌ Marketplace 失敗: {result.get('error', '未知錯誤')}")

            self.engine.post_marketplace_now(
                account_id=account_id,
                title=title, price=price, location=location,
                description=desc, images=images,
                callback=on_success,
                error_callback=on_error,
            )
        else:
            self.status_var.set(f"✅ Marketplace 發布指令已排入佇列")

    def _clear_all(self):
        """清除所有輸入"""
        self.content_text.delete("1.0", tk.END)
        self._clear_groups()
        self.link_url_var.set("")
        self.video_path_var.set("")
        self.scrape_url_var.set("")
        self.selected_images = []
        self.scraped_images = []
        self.img_label.config(text="未選圖片")
        self.ai_status_label.config(text="")
        self._load_header_footer()

    # ── 社團管理 ──

    def _add_group_to_list(self):
        """新增社團到清單（支援「名稱||URL」格式）"""
        raw = self.groups_entry.get().strip()
        if not raw or raw == "輸入社團名稱並按 Enter 加入...":
            return
        
        # 解析 name||url 格式
        if "||" in raw:
            parts = raw.split("||", 1)
            name = parts[0].strip()
            url = parts[1].strip()
        else:
            name = raw
            url = ""

        if not name:
            return

        self._add_group(name, url)
        self.groups_entry.delete(0, tk.END)

    def _add_group(self, name: str, url: str = ""):
        """新增一個社團到清單（自動去重）"""
        existing = {self.groups_listbox.get(i) for i in range(self.groups_listbox.size())}
        if name not in existing:
            self.groups_listbox.insert(tk.END, name)
            if url:
                self._group_urls[name] = url
            log("POST", "group_mgr", f"新增社團: {name}" + (f" ({url})" if url else ""), "📋")

    def _remove_selected_group(self):
        """刪除選取的社團"""
        selected = self.groups_listbox.curselection()
        for idx in reversed(selected):
            name = self.groups_listbox.get(idx)
            self.groups_listbox.delete(idx)
            self._group_urls.pop(name, None)
            log("POST", "group_mgr", f"移除社團: {name}", "🗑️")

    def _clear_groups(self):
        """清空社團清單與輸入框"""
        self.groups_listbox.delete(0, tk.END)
        self.groups_entry.delete(0, tk.END)
        self._group_urls.clear()
        self._update_group_selection_count()

    def _select_all_groups(self):
        """全選所有社團"""
        self.groups_listbox.select_set(0, tk.END)
        self._update_group_selection_count()

    def _deselect_all_groups(self):
        """取消選取"""
        self.groups_listbox.selection_clear(0, tk.END)
        self._update_group_selection_count()

    def _update_group_selection_count(self):
        """更新選取計數顯示"""
        sel = self.groups_listbox.curselection()
        total = self.groups_listbox.size()
        if sel:
            self.group_sel_label.config(text=f"📋 已選 {len(sel)}/{total} 個社團（發文僅發送至反白選取者）")
        else:
            self.group_sel_label.config(text=f"📋 未選取任何社團（將發送至個人頁面）")

    def _get_group_urls(self) -> list[str]:
        """回傳已選取的社團發文目標。有 URL 用 URL，否則用名稱。
        只回傳在 Listbox 中被選取 (highlighted) 的項目。
        """
        result = []
        selected = self.groups_listbox.curselection()
        for idx in selected:
            name = self.groups_listbox.get(idx)
            url = self._group_urls.get(name, "")
            result.append(url if url else name)
        return result

    def _get_groups_path(self):
        """取得社團儲存檔案路徑"""
        import os
        data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
        os.makedirs(data_dir, exist_ok=True)
        return os.path.join(data_dir, "saved_groups.json")

    def _save_groups(self):
        """儲存社團清單到檔案（含 URL）"""
        items = []
        for i in range(self.groups_listbox.size()):
            name = self.groups_listbox.get(i)
            url = self._group_urls.get(name, "")
            items.append({"name": name, "url": url})
        path = self._get_groups_path()
        try:
            import json
            with open(path, "w", encoding="utf-8") as f:
                json.dump(items, f, ensure_ascii=False, indent=2)
            msg = f"✅ 已儲存 {len(items)} 個社團"
            if hasattr(self, 'status_var') and self.status_var:
                self.status_var.set(msg)
            log("POST", "group_mgr", f"儲存 {len(items)} 個社團到 saved_groups.json", "💾")
        except Exception as e:
            err = f"❌ 儲存失敗: {e}"
            if hasattr(self, 'status_var') and self.status_var:
                self.status_var.set(err)

    def _load_groups(self, *_):
        """從檔案載入社團清單（含 URL）"""
        path = self._get_groups_path()
        if not os.path.exists(path):
            return
        try:
            import json
            with open(path, "r", encoding="utf-8") as f:
                items = json.load(f)
            self.groups_listbox.delete(0, tk.END)
            self._group_urls.clear()
            for item in items:
                if isinstance(item, dict):
                    name = item.get("name", "").strip()
                    url = item.get("url", "").strip()
                elif isinstance(item, str):
                    name = item.strip()
                    url = ""
                else:
                    continue
                if name:
                    self.groups_listbox.insert(tk.END, name)
                    if url:
                        self._group_urls[name] = url
            count = self.groups_listbox.size()
            msg = f"📋 已載入 {count} 個社團"
            if hasattr(self, 'status_var') and self.status_var:
                self.status_var.set(msg)
            else:
                log("POST", "group_mgr", msg, "📋")
        except Exception as e:
            err = f"⚠️ 載入社團失敗: {e}"
            if hasattr(self, 'status_var') and self.status_var:
                self.status_var.set(err)
            else:
                log("POST", "group_mgr", err, "⚠️")

    # ── 從 FB 載入社團 ──

    def _on_fetch_groups_from_fb(self):
        """點擊「從 FB 載入」— 使用引擎的共享瀏覽器爬取社團（不開新瀏覽器）"""
        if not self.engine:
            self.status_var.set("⚠️ 引擎未啟動")
            return

        browser = self.engine.get_browser()
        if not browser:
            self.status_var.set("⚠️ 瀏覽器尚未就緒，請稍候再試")
            return

        account_id = self._get_selected_account_id()
        self.status_var.set("⏳ 正在從 FB 載入社團 (約 8 秒)...")
        self.update()

        def worker():
            import asyncio
            try:
                loop = getattr(self.engine, '_loop', None)
                if not loop:
                    self.after(0, lambda: self.status_var.set("⚠️ 引擎未就緒"))
                    return

                future = asyncio.run_coroutine_threadsafe(
                    _fb_fetch_groups_async(browser, account_id),
                    loop,
                )
                items = future.result(timeout=25)
                if items:
                    self.after(0, lambda: self._merge_groups_from_fb(items))
                    self.after(0, lambda: self.status_var.set(f"✅ 已從 FB 載入 {len(items)} 個社團"))
                else:
                    self.after(0, lambda: self.status_var.set("⚠️ 未找到任何社團（可能未登入或 cookie 過期）"))
            except Exception as e:
                self.after(0, lambda: self.status_var.set(f"❌ 載入失敗: {str(e)[:40]}"))

        threading.Thread(target=worker, daemon=True).start()

    def _merge_groups_from_fb(self, items: list[dict]):
        """將 FB 載入的社團（含 URL）合併到現有清單（不重複）"""
        for item in items:
            name = item.get("name", "").strip()
            url = item.get("url", "").strip()
            if name:
                self._add_group(name, url)

    # ── 文案 Bank ──

    def _get_content_bank_path(self) -> str:
        data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
        os.makedirs(data_dir, exist_ok=True)
        return os.path.join(data_dir, "content_bank.json")

    def _load_content_bank(self) -> list[dict]:
        path = self._get_content_bank_path()
        if not os.path.exists(path):
            return []
        try:
            import json
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def _save_content_bank(self, items: list[dict]):
        path = self._get_content_bank_path()
        try:
            import json
            with open(path, "w", encoding="utf-8") as f:
                json.dump(items, f, ensure_ascii=False, indent=2)
        except Exception as e:
            messagebox.showerror("錯誤", f"儲存文案 Bank 失敗: {e}")

    def _on_content_bank(self):
        """開啟文案 Bank 管理對話框"""
        dialog = tk.Toplevel(self)
        dialog.title("📋 文案 Bank")
        dialog.geometry("550x400")
        dialog.transient(self)
        dialog.grab_set()
        dialog.configure(bg="#2b2b2b")

        create_styled_label(dialog, text="已儲存的文案", font=("Arial", 11)).pack(pady=(10, 5))

        # 文案清單 + 預覽
        main_frame = create_styled_frame(dialog)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # 左邊清單
        list_frame = create_styled_frame(main_frame)
        list_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        bank_items = self._load_content_bank()
        listbox = tk.Listbox(
            list_frame, height=12,
            bg="#2b2b2b", fg="#ffffff",
            selectbackground="#0078d4",
            font=("Arial", 10),
        )
        listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        for item in bank_items:
            name = item.get("name", "未命名")
            listbox.insert(tk.END, name)

        # 右邊按鈕
        btn_frame = create_styled_frame(main_frame)
        btn_frame.pack(side=tk.LEFT, padx=10, fill=tk.Y)

        def _save_current():
            """儲存目前 Header/Body/Footer 到 Bank"""
            header = self.header_var.get().strip()
            body = self.content_text.get("1.0", tk.END).strip()
            footer = self.footer_var.get().strip()
            if not body:
                messagebox.showwarning("警告", "請先輸入文案內容")
                return

            # 取名對話框
            name_dialog = tk.Toplevel(dialog)
            name_dialog.title("儲存文案")
            name_dialog.geometry("350x120")
            name_dialog.transient(dialog)
            name_dialog.grab_set()
            name_dialog.configure(bg="#2b2b2b")
            create_styled_label(name_dialog, text="文案名稱:").pack(pady=(10, 5))
            name_var = tk.StringVar()
            name_entry = create_styled_entry(name_dialog, width=40, textvariable=name_var)
            name_entry.pack(pady=5)

            def do_save():
                name = name_var.get().strip()
                if not name:
                    name = f"文案 {len(bank_items) + 1}"
                bank_items.append({
                    "name": name,
                    "header": header,
                    "body": body,
                    "footer": footer,
                })
                self._save_content_bank(bank_items)
                listbox.insert(tk.END, name)
                log("POST", "content_bank", f"儲存文案: {name}", "💾")
                self.status_var.set(f"✅ 已儲存: {name}")
                name_dialog.destroy()

            create_styled_button(name_dialog, text="💾 儲存", command=do_save, bootstyle="success").pack(pady=5)

        def _load_selected():
            """載入選取的文案到編輯區"""
            sel = listbox.curselection()
            if not sel:
                messagebox.showwarning("警告", "請先選取一個文案")
                return
            idx = sel[0]
            item = bank_items[idx]
            if item.get("header"):
                self.header_var.set(item["header"])
            if item.get("body"):
                self.content_text.delete("1.0", tk.END)
                self.content_text.insert("1.0", item["body"])
            if item.get("footer"):
                self.footer_var.set(item["footer"])
            self.status_var.set(f"✅ 已載入: {item.get('name', '')}")
            dialog.destroy()

        def _delete_selected():
            """刪除選取的文案"""
            sel = listbox.curselection()
            if not sel:
                return
            idx = sel[0]
            name = bank_items[idx].get("name", "")
            if messagebox.askyesno("確認刪除", f"刪除「{name}」？"):
                bank_items.pop(idx)
                self._save_content_bank(bank_items)
                listbox.delete(idx)
                log("POST", "content_bank", f"刪除: {name}", "🗑️")

        create_styled_button(btn_frame, text="💾 儲存目前文案", command=_save_current, bootstyle="success").pack(pady=5, fill=tk.X)
        create_styled_button(btn_frame, text="📤 載入選取", command=_load_selected, bootstyle="primary").pack(pady=5, fill=tk.X)
        create_styled_button(btn_frame, text="🗑️ 刪除選取", command=_delete_selected, bootstyle="danger").pack(pady=5, fill=tk.X)


async def _fb_fetch_groups_async(browser, account_id: str) -> list[dict]:
    """使用引擎的共享瀏覽器從 FB 爬取用戶社團（不開新瀏覽器）

    回傳: [{"name": "社團名稱", "url": "https://www.facebook.com/groups/XXXXX/"}, ...]
    """
    import asyncio
    from core.account import AccountManager

    am = AccountManager()
    acc = am.get(account_id)
    if not acc:
        return []

    cookie_json = am.get_cookie_json(account_id)
    if not cookie_json:
        return []

    page = await browser.get_page(account_id)
    if not page:
        await browser.create_context(account_id, cookie_str=cookie_json)
        page = await browser.get_page(account_id)

    items = []

    # 前往社團頁
    await page.goto(
        "https://www.facebook.com/groups/?category=membership",
        wait_until="domcontentloaded", timeout=30000,
    )
    await asyncio.sleep(4)

    # 滑動載入更多
    for _ in range(5):
        await page.evaluate("window.scrollBy(0, 1500)")
        await asyncio.sleep(2)

    # 擷取
    entries = await page.evaluate("""
        () => {
            const result = [], seen = new Set();
            document.querySelectorAll('a[href*="/groups/"]').forEach(link => {
                const h = link.getAttribute('href') || '';
                if (h.includes('/join') || h.includes('/create') || h.includes('search')) return;
                const m = h.match(/\\/groups\\/[0-9]+/);
                if (!m) return;
                const t = (link.textContent||'').trim();
                if (t.length<2||t.length>100||t.includes('Groups')||t.includes('社團')||t.includes('建立')) return;
                const u = 'https://www.facebook.com'+m[0];
                if (!seen.has(u)) { seen.add(u); result.push({name:t,url:u}); }
            });
            return result;
        }
    """) or []

    for e in entries:
        n = (e.get("name") or "").strip()
        u = (e.get("url") or "").strip()
        if n and u:
            items.append({"name": n, "url": u})

    seen_urls = set()
    return [it for it in items if not (it["url"] in seen_urls or seen_urls.add(it["url"]))]

    def refresh_accounts(self, account_map: dict[str, str]):
        self.account_map = account_map
        self.account_ids = list(account_map.values())
        display_names = list(account_map.keys())
        self.account_combo["values"] = display_names
        if display_names and self.account_var.get() not in display_names:
            self.account_var.set(display_names[0])
        if hasattr(self, 'market_account_var'):
            self.market_account_var.set(display_names[0] if display_names else "")
        # 也重新載入與此帳號關聯的 FB API Page
        self._refresh_fb_api_pages()


# ── 輔助函數 ──

def _build_intro_prompt(data: dict) -> str:
    """從已填欄位建立 AI 介紹生成 prompt"""
    lines = []
    for k, v in data.items():
        if v and k != "intro":
            lines.append(f"- {k}: {v}")
    info_block = "\n".join(lines) if lines else "無資料"

    return f"""你是台灣房仲文案專家。請根據以下物件資訊，寫一段吸引人的介紹（2-3 句，約 40-60 字）。

物件資訊：
{info_block}

要求：
1. 用繁體中文
2. 強調亮點（地點、格局、車位、學區等）
3. 語氣熱情但不過度誇大
4. 不要重複標題
5. 只輸出介紹文字，不要加任何標籤、標題或符號"""

