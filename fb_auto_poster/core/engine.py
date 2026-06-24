"""發文引擎橋接層 — GUI 同步層 ↔ Playwright 非同步層 + Graph API

架構:
  GUI (Tkinter, sync)               Background Thread (async)
  ┌──────────────┐                  ┌─────────────────────┐
  │ poster_panel │                  │ SessionManager      │
  │              │                  │                     │
  │ post_now() ──┼───queue──→       │ _worker_loop()      │
  │              │                  │   browser.start()   │
  │ update_ui() ←┼──after()───     │   login(cookie)     │
  │              │                  │   poster.post()     │
  └──────────────┘                  │   或 API 直接發文     │
                                    │   log()             │
                                    └─────────────────────┘

支援兩種發文模式:
  1. Browser 模式 (Playwright): 模擬瀏覽器操作，可發個人頁面/社團
  2. API 模式 (Graph API): 直接呼叫 FB Graph API，僅限粉絲專頁
"""
import asyncio
import json
import os
import queue
import threading
import traceback
from datetime import datetime, timedelta
from typing import Callable, Optional

from core.account import AccountManager
from core.browser import BrowserManager
from core.poster import Poster
from core.nurturer import Nurturer
from core.deleter import Deleter
from core.interactor import Interactor
from core.fb_graph_poster import FBPageManager, FBGraphAPI, FBGraphAPIError, post_via_api
from core.threads_poster import ThreadsPoster
from core.threads_replier import ThreadsReplier, search_and_reply
from core.instagram_poster import InstagramPoster
from core.instagram_replier import InstagramReplier, ig_patrol_and_comment
from core.warmup import get_daily_plan, advance_day, record_session_done, load_warmup_state
from core.warmup_executor import run_warmup_session
from utils.logger import log


class PostTask:
    """發文任務描述"""
    def __init__(
        self,
        account_id: str,
        task_type: str,  # "post_general", "post_marketplace", "nurture_browse", etc.
        params: dict,
        callback: Optional[Callable] = None,
        error_callback: Optional[Callable] = None,
    ):
        self.account_id = account_id
        self.task_type = task_type
        self.params = params
        self.callback = callback
        self.error_callback = error_callback

    def __repr__(self):
        return f"PostTask({self.task_type}, account={self.account_id[:8]}...)"


class SessionManager:
    """發文引擎的同步/非同步橋接管理器

    GUI 層透過 post_now() 提交任務，由背景執行緒非同步執行。
    結果透過 Tkinter 的 after() 回呼更新 UI。
    """

    def __init__(self):
        self._account_manager = AccountManager()
        self._browser: Optional[BrowserManager] = None
        self._poster = Poster()
        self._nurturer = Nurturer()
        self._deleter = Deleter()
        self._interactor = Interactor()
        self._threads_poster = ThreadsPoster()
        self._threads_replier = ThreadsReplier()
        self._ig_poster = InstagramPoster()
        self._ig_replier = InstagramReplier()

        self._task_queue: queue.Queue = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None

        # UI callback（Tkinter root 的 after()）
        self._ui_callback: Optional[Callable] = None

        # 狀態
        self._status: dict[str, str] = {}  # account_id → status
        self._browser_error: str = ""  # browser launch error

    # ── GUI 層呼叫的介面 ──

    def set_ui_callback(self, callback: Callable):
        """設定 UI 更新回呼 (root.after)"""
        self._ui_callback = callback

    def start(self):
        """啟動背景發文引擎"""
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """停止背景引擎"""
        self._running = False
        self._task_queue.put(None)

    def is_browser_ready(self) -> bool:
        """檢查瀏覽器是否已初始化完成"""
        return self._browser is not None

    def get_browser_error(self) -> str:
        """取得瀏覽器啟動錯誤訊息"""
        return getattr(self, "_browser_error", "")

    async def _snapshot_post(self, page, task: PostTask) -> str:
        """發文成功後截圖存到本地資料夾

        目錄結構: data/post_snapshots/{platform}/{account_id}_{日期時間}.png
        """
        from datetime import datetime

        _pfm = {
            "post_general": "FB",
            "post_marketplace": "FB_marketplace",
            "threads_post": "Threads",
            "ig_post": "IG",
        }
        pfm = _pfm.get(task.task_type, task.task_type)
        snap_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "data", "post_snapshots", pfm,
        )
        os.makedirs(snap_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"{task.account_id}_{ts}.png"
        path = os.path.join(snap_dir, fname)
        await page.screenshot(path=path, full_page=False)
        log("SNAPSHOT", pfm, f"截圖已儲存: {fname}", "📸")
        return path

    def get_browser(self):
        """取得共享的 BrowserManager 實例（供外部 Playwright 操作使用）。

        回傳 None 如果引擎尚未啟動或瀏覽器尚未初始化。
        """
        return self._browser

    async def _get_page_for_account(self, account_id: str):
        """為指定帳號建立/取得 Playwright Page（給外部同步呼叫使用）"""
        acc = self._account_manager.get(account_id)
        if not acc:
            return None
        cookie_json = self._account_manager.get_cookie_json(account_id)
        if not cookie_json:
            return None
        page = await self._browser.get_page(account_id)
        if not page:
            await self._browser.create_context(account_id, cookie_str=cookie_json)
            page = await self._browser.get_page(account_id)
        return page

    def post_now(
        self,
        account_id: str,
        content: str,
        images: list[str] = None,
        groups: list[str] = None,
        delete_at: str = "",
        detail: str = "",
        auto_like: bool = False,
        callback: Callable = None,
        error_callback: Callable = None,
    ):
        """提交一般發文任務"""
        task = PostTask(
            account_id=account_id,
            task_type="post_general",
            params={
                "content": content,
                "images": images or [],
                "groups": groups,
                "delete_at": delete_at or "",
                "detail": detail or "",
                "auto_like": bool(auto_like),
            },
            callback=callback,
            error_callback=error_callback,
        )
        self._task_queue.put(task)

    def like_now(
        self,
        account_id: str,
        post_url: str,
        callback: Callable = None,
        error_callback: Callable = None,
    ):
        """提交按讚任務（指定貼文 URL）"""
        task = PostTask(
            account_id=account_id,
            task_type="like",
            params={"post_url": post_url},
            callback=callback,
            error_callback=error_callback,
        )
        self._task_queue.put(task)

    def post_marketplace_now(
        self,
        account_id: str,
        title: str,
        price: str,
        location: str,
        description: str,
        images: list[str] = None,
        callback: Callable = None,
        error_callback: Callable = None,
    ):
        """提交 Marketplace 發文任務"""
        task = PostTask(
            account_id=account_id,
            task_type="post_marketplace",
            params={
                "title": title, "price": price, "location": location,
                "description": description, "images": images or [],
            },
            callback=callback,
            error_callback=error_callback,
        )
        self._task_queue.put(task)

    def post_api_now(
        self,
        page_id: str,
        content: str,
        image_paths: list[str] = None,
        video_path: str = "",
        link_url: str = "",
        groups: list[str] = None,
        callback: Callable = None,
        error_callback: Callable = None,
    ):
        """提交 Graph API 發文任務（不需瀏覽器，直接呼叫 FB API）"""
        task = PostTask(
            account_id=page_id,
            task_type="post_api",
            params={
                "content": content,
                "image_paths": image_paths or [],
                "video_path": video_path,
                "link_url": link_url,
                "groups": groups,
            },
            callback=callback,
            error_callback=error_callback,
        )
        self._task_queue.put(task)

    def nurture_now(
        self,
        account_id: str,
        action: str,  # "browse", "join_groups", "post_news"
        params: dict,
        callback: Callable = None,
        error_callback: Callable = None,
    ):
        """提交養號任務"""
        task = PostTask(
            account_id=account_id,
            task_type=f"nurture_{action}",
            params=params,
            callback=callback,
            error_callback=error_callback,
        )
        self._task_queue.put(task)

    def delete_now(
        self,
        account_id: str,
        target: str,  # "group" | "wall" | "url"
        params: dict,
        callback: Callable = None,
        error_callback: Callable = None,
    ):
        """提交刪文任務

        target="group": params={"group_url": str, "max": int}
        target="wall":  params={"max": int}
        target="url":   params={"post_url": str}
        """
        if target == "url":
            task_type = "delete_url"
        elif target == "group":
            task_type = "delete"
        else:
            task_type = "delete_wall"
        task = PostTask(
            account_id=account_id,
            task_type=task_type,
            params=params,
            callback=callback,
            error_callback=error_callback,
        )
        self._task_queue.put(task)

    def threads_post_now(
        self,
        account_id: str,
        content: str,
        image_paths: list[str] = None,
        callback: Callable = None,
        error_callback: Callable = None,
    ):
        """提交 Threads 發文任務"""
        if not self.is_browser_ready():
            err = self.get_browser_error()
            self._call_ui(error_callback, {"error": f"瀏覽器未就緒: {err}"}) if error_callback else None
            return
        task = PostTask(
            account_id=account_id,
            task_type="threads_post",
            params={
                "content": content,
                "image_paths": image_paths or [],
            },
            callback=callback,
            error_callback=error_callback,
        )
        self._task_queue.put(task)

    def threads_reply_now(
        self,
        account_id: str,
        keywords: list[str],
        max_replies: int = 10,
        dry_run: bool = False,
        callback: Callable = None,
        error_callback: Callable = None,
    ):
        """提交 Threads 海巡回覆任務"""
        if not self.is_browser_ready():
            err = self.get_browser_error()
            self._call_ui(error_callback, {"error": f"瀏覽器未就緒: {err}"}) if error_callback else None
            return
        task = PostTask(
            account_id=account_id,
            task_type="threads_reply",
            params={
                "keywords": keywords,
                "max_replies": max_replies,
                "dry_run": dry_run,
            },
            callback=callback,
            error_callback=error_callback,
        )
        self._task_queue.put(task)

    def instagram_post_now(
        self, account_id: str, caption: str, image_paths: list[str],
        callback=None, error_callback=None,
    ):
        """提交 IG 發文任務"""
        if not self.is_browser_ready():
            self._call_ui(error_callback, {"error": "瀏覽器未就緒"}) if error_callback else None
            return
        self._task_queue.put(PostTask(account_id, "ig_post",
            {"caption": caption, "image_paths": image_paths}, callback, error_callback))

    def instagram_patrol_now(
        self, account_id: str, keywords: list[str], max_comments=10,
        dry_run=False, callback=None, error_callback=None,
    ):
        """提交 IG Hashtag 巡邏留言任務"""
        if not self.is_browser_ready():
            self._call_ui(error_callback, {"error": "瀏覽器未就緒"}) if error_callback else None
            return
        self._task_queue.put(PostTask(account_id, "ig_patrol",
            {"keywords": keywords, "max_comments": max_comments, "dry_run": dry_run},
            callback, error_callback))

    def warmup_now(
        self, account_id: str, callback=None, error_callback=None,
    ):
        """提交暖號任務（執行一個時段）"""
        if not self.is_browser_ready():
            self._call_ui(error_callback, {"error": "瀏覽器未就緒"}) if error_callback else None
            return
        self._task_queue.put(PostTask(account_id, "warmup",
            {}, callback, error_callback))

    def get_status(self, account_id: str) -> str:
        return self._status.get(account_id, "就緒")

    # ── 背景執行緒 ──

    def _worker_loop(self):
        """主工作循環 — 在背景執行緒中運行 asyncio"""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        try:
            self._loop.run_until_complete(self._async_worker())
        except Exception as e:
            traceback.print_exc()
        finally:
            self._loop.close()

    async def _async_worker(self):
        """非同步工作循環"""
        # 初始化瀏覽器
        self._browser = BrowserManager()
        try:
            await self._browser.start()
        except Exception as e:
            self._browser_error = str(e)
            log("ENGINE", "system", f"瀏覽器啟動失敗: {e}", "❌")
            return

        # 註冊到足跡清理系統
        from core.footprint_cleaner import register_browser_manager
        register_browser_manager(self._browser)

        log("ENGINE", "system", "Posting engine started", "✅")

        while self._running:
            try:
                # 非阻塞檢查 queue（每秒 poll 一次）
                try:
                    task = self._task_queue.get_nowait()
                except queue.Empty:
                    await asyncio.sleep(1)
                    continue

                if task is None:
                    break  # 停止信號

                # 執行任務
                await self._execute_task(task)

            except Exception as e:
                traceback.print_exc()
                await asyncio.sleep(1)

        # 清理瀏覽器
        await self._browser.stop()
        log("ENGINE", "system", "Posting engine stopped", "✅")

    async def _execute_task(self, task: PostTask):
        """執行單一任務"""
        # ── Threads 任務用 IG 帳號 ──
        is_threads = task.task_type.startswith("threads_")
        is_ig = task.task_type.startswith("ig_")
        is_warmup = task.task_type == "warmup"

        if is_threads:
            from gui.threads_panel import load_threads_cookie, load_ig_cookie
            cookie_json = load_threads_cookie(task.account_id)
            if not cookie_json:
                cookie_json = load_ig_cookie(task.account_id)  # fallback to IG cookie
            if not cookie_json:
                self._call_ui(task.error_callback, {"error": "找不到 Threads Cookie"}) if task.error_callback else None
                return
            # Fix: Threads export has domain .threads.com but we navigate to threads.net
            # Change cookie domain so Playwright sends them to the right host
            cookies_data = json.loads(cookie_json)
            for c in cookies_data:
                if c.get("domain") == ".threads.com":
                    c["domain"] = ".threads.net"
            cookie_json = json.dumps(cookies_data)
        elif is_ig:
            from gui.threads_panel import load_ig_cookie
            cookie_json = load_ig_cookie(task.account_id)
            if not cookie_json:
                self._call_ui(task.error_callback, {"error": "找不到 IG Cookie"}) if task.error_callback else None
                return
        elif is_warmup:
            from gui.threads_panel import load_ig_cookie
            cookie_json = load_ig_cookie(task.account_id)
            if not cookie_json:
                self._call_ui(task.error_callback, {"error": "找不到 IG Cookie"}) if task.error_callback else None
                return
        else:
            acc = self._account_manager.get(task.account_id)
            if not acc:
                msg = f"帳號不存在: {task.account_id}"
                self._call_ui(task.error_callback, msg) if task.error_callback else None
                return
            cookie_json = self._account_manager.get_cookie_json(task.account_id)
            if not cookie_json:
                msg = f"帳號 {acc.email} 沒有 Cookie，請先匯入 FB Cookie"
                self._call_ui(task.error_callback, msg) if task.error_callback else None
                return

        page = await self._browser.get_page(task.account_id)
        if not page:
            await self._browser.create_context(task.account_id, cookie_str=cookie_json)
            page = await self._browser.get_page(task.account_id)

        # 根據任務類型執行
        try:
            result = None

            if task.task_type == "post_general":
                result = await self._poster.post_general(
                    page,
                    content=task.params["content"],
                    image_paths=task.params.get("images"),
                    groups=task.params.get("groups"),
                )
                # 成功後：寫入 PostStore（含 post_url / delete_at）
                try:
                    delete_at = (task.params.get("delete_at") or "").strip()
                    auto_like = bool(task.params.get("auto_like", False))
                    detail_base = (task.params.get("detail") or "").strip()

                    if delete_at and result and result.get("success"):
                        from core.post_store import add_post
                        posted = result.get("posted_to") or []
                        for r in posted:
                            if not isinstance(r, dict) or not r.get("success"):
                                continue
                            g = r.get("group", "")
                            post_url = (r.get("post_url") or "").strip()
                            target_type = "group" if (g and "facebook.com/groups/" in str(g)) else "wall"
                            target_url = str(g) if target_type == "group" else ""
                            detail = detail_base or f"發送到「{g or '個人頁面'}」"
                            add_post(
                                account_id=task.account_id,
                                target_type=target_type,
                                target_url=target_url,
                                post_url=post_url,
                                detail=detail,
                                delete_at=delete_at,
                            )
                            log("POST", acc.email, "已寫入貼文刪除紀錄", "💾", detail=(post_url[:80] or target_url[:80]), schedule_delete_at=delete_at)

                            # 發文後自動按讚（需要有 URL 才能精準按讚）
                            if auto_like and post_url:
                                self.like_now(task.account_id, post_url)
                except Exception as _store_err:
                    log("POST", acc.email, f"寫入貼文紀錄失敗: {str(_store_err)[:120]}", "⚠️")
            elif task.task_type == "post_api":
                # Graph API 模式：不需要瀏覽器，直接呼叫 API
                result = self._execute_post_api(
                    page_id=task.account_id,
                    content=task.params["content"],
                    image_paths=task.params.get("image_paths"),
                    video_path=task.params.get("video_path", ""),
                    link_url=task.params.get("link_url", ""),
                    groups=task.params.get("groups"),
                )
            elif task.task_type == "post_marketplace":
                result = await self._poster.post_marketplace(
                    page,
                    title=task.params["title"],
                    price=task.params["price"],
                    location=task.params["location"],
                    description=task.params["description"],
                    image_paths=task.params.get("images"),
                )
            elif task.task_type == "nurture_browse":
                result = {"count": await self._nurturer.browse_feed(page, count=task.params.get("count", 5))}
            elif task.task_type == "nurture_join_groups":
                result = {"joined": await self._nurturer.join_groups(page, keywords=task.params["keywords"], max_groups=task.params.get("max", 5))}
            elif task.task_type == "nurture_post_news":
                result = await self._nurturer.post_news_to_wall(page, task.params["title"], task.params["url"])
            elif task.task_type == "delete":
                result = {"deleted": await self._deleter.delete_from_group(page, task.params["group_url"], task.params.get("max", 10))}
            elif task.task_type == "delete_wall":
                result = {"deleted": await self._deleter.delete_all_from_wall(page, task.params.get("max", 50))}
            elif task.task_type == "delete_url":
                result = {"deleted": await self._deleter.delete_by_url(page, task.params["post_url"])}
            elif task.task_type == "interact":
                result = await self._interactor.comment_on_post(page, task.params["post_url"], task.params.get("comment", ""))
            elif task.task_type == "like":
                result = await self._interactor.like_post(page, task.params["post_url"])
            elif task.task_type == "threads_post":
                result = await self._threads_poster.post_thread(
                    page,
                    content=task.params["content"],
                    image_paths=task.params.get("image_paths"),
                )
            elif task.task_type == "threads_reply":
                result = await search_and_reply(
                    page, replier=self._threads_replier,
                    keywords=task.params["keywords"],
                    max_replies=task.params["max_replies"],
                    dry_run=task.params["dry_run"],
                )
            elif task.task_type == "ig_post":
                result = await self._ig_poster.post_carousel(
                    page, caption=task.params["caption"],
                    image_paths=task.params["image_paths"],
                )
            elif task.task_type == "ig_patrol":
                result = await ig_patrol_and_comment(
                    page, replier=self._ig_replier,
                    keywords=task.params["keywords"],
                    max_comments=task.params["max_comments"],
                    dry_run=task.params["dry_run"],
                )
            elif task.task_type == "warmup":
                advance_day(task.account_id)
                plan = get_daily_plan(task.account_id)
                if plan["should_skip"]:
                    result = {"status": "skipped", "reason": "休息日或黑夜時段"}
                else:
                    result = await run_warmup_session(page, plan)
                    record_session_done(task.account_id, result)

            # ── 發文成功時自動截圖存證 ──
            _post_types = {"post_general", "post_marketplace", "threads_post", "ig_post"}
            if task.task_type in _post_types and result and result.get("success"):
                try:
                    await self._snapshot_post(page, task)
                except Exception as _ss_err:
                    log("SNAPSHOT", "system", f"截圖失敗: {_ss_err}", "⚠️")

            # UI 回呼結果
            if task.callback:
                self._call_ui(task.callback, result or {})

            log("POST", acc.email, f"{task.task_type} completed", "✅" if result and result.get("success", True) else "❌")

        except Exception as e:
            err_msg = f"{task.task_type} failed: {e}"
            log("POST", acc.email, err_msg, "❌")
            if task.error_callback:
                self._call_ui(task.error_callback, {"error": str(e)})

    def _execute_post_api(
        self,
        page_id: str,
        content: str,
        image_paths: list[str] = None,
        video_path: str = "",
        link_url: str = "",
        groups: list[str] = None,
    ) -> dict:
        """執行 Graph API 發文（同步，在背景執行緒中呼叫）"""
        result = post_via_api(
            page_id=page_id,
            content=content,
            image_paths=image_paths,
            video_path=video_path,
            link_url=link_url,
            groups=groups,
        )
        return result

    def _call_ui(self, cb: Callable, result):
        """安全地在 UI 執行緒中呼叫回呼"""
        if self._ui_callback:
            self._ui_callback(lambda: cb(result))
        else:
            try:
                cb(result)
            except Exception:
                pass
