"""養號設定界面"""
import tkinter as tk
from tkinter import ttk, messagebox

from gui.dark_theme import (
    create_styled_button, create_styled_entry,
    create_styled_label, create_styled_frame
)


class NurturerPanel(ttk.Frame):
    """養號操作面板"""

    def __init__(self, parent, account_ids: list[str], engine=None, **kwargs):
        super().__init__(parent, **kwargs)
        self.account_ids = account_ids
        self.engine = engine
        self._build_ui()

    def _build_ui(self):
        # 帳號選擇
        row1 = create_styled_frame(self)
        row1.pack(fill=tk.X, padx=10, pady=10)

        create_styled_label(row1, text="選擇帳號:").pack(side=tk.LEFT)
        self.account_var = tk.StringVar(value=self.account_ids[0] if self.account_ids else "")
        ttk.Combobox(
            row1, textvariable=self.account_var,
            values=self.account_ids, state="readonly", width=40
        ).pack(side=tk.LEFT, padx=5)

        # 功能卡片
        cards_frame = create_styled_frame(self)
        cards_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # 瀏覽貼文
        card1 = create_styled_frame(cards_frame, padding=10, bootstyle="secondary")
        card1.pack(fill=tk.X, pady=5)

        create_styled_label(card1, text="模擬瀏覽貼文", font=("Arial", 12)).pack(anchor=tk.W)
        browse_frame = create_styled_frame(card1)
        browse_frame.pack(fill=tk.X, pady=5)
        create_styled_label(browse_frame, text="瀏覽篇數:").pack(side=tk.LEFT)
        self.browse_count = ttk.Spinbox(browse_frame, from_=1, to=10, width=5)
        self.browse_count.set(5)
        self.browse_count.pack(side=tk.LEFT, padx=5)
        create_styled_button(browse_frame, text="開始瀏覽", command=self._on_browse, bootstyle="primary").pack(side=tk.LEFT, padx=10)

        # 加入社團
        card2 = create_styled_frame(cards_frame, padding=10, bootstyle="secondary")
        card2.pack(fill=tk.X, pady=5)

        create_styled_label(card2, text="自動加入社團", font=("Arial", 12)).pack(anchor=tk.W)
        group_frame = create_styled_frame(card2)
        group_frame.pack(fill=tk.X, pady=5)
        create_styled_label(group_frame, text="關鍵字 (逗號分隔):").pack(side=tk.LEFT)
        self.group_keywords = create_styled_entry(group_frame, width=30)
        self.group_keywords.insert(0, "房地產,房屋,買房")
        self.group_keywords.pack(side=tk.LEFT, padx=5)
        create_styled_label(group_frame, text=" 加入數量:").pack(side=tk.LEFT)
        self.join_count = ttk.Spinbox(group_frame, from_=1, to=10, width=5)
        self.join_count.set(5)
        self.join_count.pack(side=tk.LEFT, padx=5)
        create_styled_button(group_frame, text="開始加入", command=self._on_join_groups, bootstyle="primary").pack(side=tk.LEFT, padx=10)

        # 轉發新聞
        card3 = create_styled_frame(cards_frame, padding=10, bootstyle="secondary")
        card3.pack(fill=tk.X, pady=5)

        create_styled_label(card3, text="轉發新聞到個人頁面", font=("Arial", 12)).pack(anchor=tk.W)
        news_frame = create_styled_frame(card3)
        news_frame.pack(fill=tk.X, pady=5)
        create_styled_label(news_frame, text="新聞標題:").pack(side=tk.LEFT)
        self.news_title = create_styled_entry(news_frame, width=30)
        self.news_title.pack(side=tk.LEFT, padx=5)
        create_styled_label(news_frame, text="網址:").pack(side=tk.LEFT)
        self.news_url = create_styled_entry(news_frame, width=30)
        self.news_url.pack(side=tk.LEFT, padx=5)
        create_styled_button(news_frame, text="轉發", command=self._on_post_news, bootstyle="primary").pack(side=tk.LEFT, padx=10)

        # 狀態
        self.status_var = tk.StringVar(value="就緒")
        ttk.Label(self, textvariable=self.status_var).pack(pady=10)

    def _get_account_id(self) -> str:
        return self.account_var.get()

    def _on_browse(self):
        if not self.engine:
            self.status_var.set("⚠️ 引擎未連線")
            return
        account_id = self._get_account_id()
        try:
            count = int(self.browse_count.get())
        except ValueError:
            count = 5
        self.status_var.set(f"⏳ 開始模擬瀏覽 {count} 篇貼文...")
        self.engine.nurture_now(
            account_id=account_id,
            action="browse",
            params={"count": count},
            callback=lambda r: self.status_var.set(f"✅ 瀏覽完成"),
            error_callback=lambda r: self.status_var.set(f"❌ 瀏覽失敗: {r.get('error','')}")
        )

    def _on_join_groups(self):
        if not self.engine:
            self.status_var.set("⚠️ 引擎未連線")
            return
        account_id = self._get_account_id()
        keywords_raw = self.group_keywords.get().strip()
        if not keywords_raw:
            self.status_var.set("⚠️ 請輸入關鍵字")
            return
        keywords = [k.strip() for k in keywords_raw.split(",") if k.strip()]
        try:
            max_groups = int(self.join_count.get())
        except ValueError:
            max_groups = 5
        self.status_var.set(f"⏳ 搜尋並加入 {max_groups} 個社團... ({', '.join(keywords[:3])}...)")

        def on_done(result):
            joined = result.get("joined", 0)
            self.status_var.set(f"✅ 已加入 {joined} 個新社團")

        def on_error(result):
            self.status_var.set(f"❌ 加入失敗: {result.get('error','')}")

        self.engine.nurture_now(
            account_id=account_id,
            action="join_groups",
            params={"keywords": keywords, "max": max_groups},
            callback=on_done,
            error_callback=on_error,
        )

    def _on_post_news(self):
        if not self.engine:
            self.status_var.set("⚠️ 引擎未連線")
            return
        account_id = self._get_account_id()
        title = self.news_title.get().strip()
        url = self.news_url.get().strip()
        if not title:
            self.status_var.set("⚠️ 請輸入新聞標題")
            return
        self.status_var.set(f"⏳ 轉發新聞: {title[:20]}...")
        self.engine.nurture_now(
            account_id=account_id,
            action="post_news",
            params={"title": title, "url": url},
            callback=lambda r: self.status_var.set("✅ 新聞已轉發"),
            error_callback=lambda r: self.status_var.set(f"❌ 轉發失敗: {r.get('error','')}")
        )
