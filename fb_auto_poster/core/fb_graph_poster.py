"""Facebook Graph API 發文模組 (Enhanced)

取代 Playwright 瀏覽器自動化，直接透過 Facebook Graph API 發文。
支援：
  - POST /{page-id}/feed（純文字貼文、含連結貼文）
  - POST /{page-id}/photos（本機圖片 + 遠端 URL 圖片 + 說明）
  - 多張圖片貼文（本機 + URL 混合，先上傳 media → feed with attached_media）
  - POST /{page-id}/videos（影片上傳，含自動分塊 big file upload）
  - Token 加密儲存（utils/secret_store.py）
  - Token 驗證（/debug_token）
  - Long-lived token 交換
  - 權限範圍分析與中文建議

限制：
  - 僅支援粉絲專頁（Page）發文（Page Access Token）
  - 個人塗鴉牆/社團發文需要 publish_to_groups（Meta 已棄用，不支援）

用法：
    api = FBGraphAPI(page_id="123", access_token="EA...")
    result = api.post_text("Hello World")
    result = api.post_text_with_link("Check this", "https://example.com")
    result = api.post_video("video.mp4", title="My Video")
"""
import json
import os
import time
import tempfile
import uuid
from datetime import datetime, timezone
from typing import Optional

import requests

from utils.config import get_data_path, load_json, save_json
from utils.secret_store import encrypt_secret, decrypt_secret
from utils.logger import log

# ── 常數 ──

GRAPH_API_BASE = "https://graph.facebook.com/v22.0"
GRAPH_VIDEO_BASE = "https://graph-video.facebook.com/v22.0"  # 影片上傳專用端點
DEFAULT_TIMEOUT = 30  # 單次 API 呼叫超時（秒）
VIDEO_UPLOAD_TIMEOUT = 300  # 影片上傳超時（秒）
MAX_RETRIES = 3
RETRY_DELAY = 2  # 重試間隔（秒）
VIDEO_CHUNK_SIZE = 10 * 1024 * 1024  # 影片分塊大小 10MB

# ── 中文錯誤訊息對照表 ──

def _human_error_message(code: int, subcode: int = 0) -> str:
    """將 Graph API 錯誤碼轉換為中文提示"""
    messages = {
        100: "參數錯誤 — 請檢查 Page ID 是否正確",
        102: "Session Key 無效 — Token 已過期或登出，請重新取得 Token",
        190: "Access Token 已過期 — 請重新取得 Token",
        200: "權限不足 — Token 缺少必要權限（需要 pages_manage_posts, pages_read_engagement）",
        4: "API 呼叫次數過多（Rate Limit）— 請稍後再試",
        17: "API 呼叫次數過多 — 請降低發文頻率",
        32: "API 呼叫次數過多 — 請稍後再試",
        341: "請求過多 — 請等待後重試",
        368: "暫時性錯誤 — 請稍後再試",
        10: "API 暫時無法使用 — 請稍後再試",
        2: "服務暫時不可用 — 請稍後再試",
        1: "未知錯誤 — 請稍後再試",
        104: "App 限制 — 此應用程式尚未上線或審核，僅限開發者使用",
        190: "Token 無效 — 請檢查 token 是否正確複製",
        2500: "圖片網址無效或無法存取",
        324: "影片檔案格式不支援或損毀",
        3600: "貼文內容包含被禁止的連結或內容",
    }
    return messages.get(code, f"Graph API 錯誤 (code={code}, subcode={subcode})")

# ── Graph API 必要權限說明 ──

_REQUIRED_SCOPES = {
    "pages_manage_posts": "發文、編輯、刪除貼文（必須）",
    "pages_read_engagement": "讀取貼文互動資料（建議）",
    "pages_show_list": "列出粉絲專頁（首次取得 token 時需要）",
    "pages_manage_metadata": "管理粉絲專頁設定（選用）",
}


# ── 資料模型 ──

class FBPageConfig:
    """粉絲專頁 API 設定"""
    def __init__(
        self,
        page_id: str,
        page_name: str = "",
        access_token_encrypted: str = "",
        linked_account_id: str = "",
        created_at: str = "",
    ):
        self.page_id = page_id
        self.page_name = page_name
        self.access_token_encrypted = access_token_encrypted
        self.linked_account_id = linked_account_id
        self.created_at = created_at or datetime.now(timezone.utc).isoformat()

    @property
    def access_token(self) -> str:
        """解密回傳原始 access token"""
        if not self.access_token_encrypted:
            return ""
        return decrypt_secret(self.access_token_encrypted)

    @access_token.setter
    def access_token(self, raw: str):
        """加密儲存 raw token"""
        self.access_token_encrypted = encrypt_secret(raw)

    def to_dict(self) -> dict:
        return {
            "page_id": self.page_id,
            "page_name": self.page_name,
            "access_token_encrypted": self.access_token_encrypted,
            "linked_account_id": self.linked_account_id,
            "created_at": self.created_at,
        }

    @staticmethod
    def from_dict(d: dict) -> "FBPageConfig":
        return FBPageConfig(
            page_id=d["page_id"],
            page_name=d.get("page_name", ""),
            access_token_encrypted=d.get("access_token_encrypted", ""),
            linked_account_id=d.get("linked_account_id", ""),
            created_at=d.get("created_at", ""),
        )


# ── Page 設定管理 ──

_PAGES_FILE = "fb_pages.json"


class FBPageManager:
    """管理多個粉絲專頁的 API 設定（CRUD + 加密儲存）"""

    def __init__(self):
        self._pages: list[FBPageConfig] = []
        self._load()

    # ── CRUD ──

    def list_all(self) -> list[FBPageConfig]:
        return list(self._pages)

    def list_linked(self, account_id: str) -> list[FBPageConfig]:
        return [p for p in self._pages if p.linked_account_id == account_id]

    def get(self, page_id: str) -> Optional[FBPageConfig]:
        for p in self._pages:
            if p.page_id == page_id:
                return p
        return None

    def add(self, config: FBPageConfig) -> None:
        # 若同 page_id 已存在，取代之
        self._pages = [p for p in self._pages if p.page_id != config.page_id]
        self._pages.append(config)
        self._save()

    def remove(self, page_id: str) -> bool:
        before = len(self._pages)
        self._pages = [p for p in self._pages if p.page_id != page_id]
        if len(self._pages) < before:
            self._save()
            return True
        return False

    def get_token(self, page_id: str) -> str:
        """便利方法：取得解密後的 token"""
        cfg = self.get(page_id)
        return cfg.access_token if cfg else ""

    # ── 持久化 ──

    def _load(self):
        raw = load_json(_PAGES_FILE, [])
        self._pages = [FBPageConfig.from_dict(item) for item in raw]

    def _save(self):
        raw = [p.to_dict() for p in self._pages]
        save_json(_PAGES_FILE, raw)


# ── Graph API 呼叫 ──

class FBGraphAPIError(Exception):
    """Graph API 回傳的錯誤"""
    def __init__(self, message: str, code: int = 0, subcode: int = 0, fbtrace_id: str = ""):
        super().__init__(message)
        self.code = code
        self.subcode = subcode
        self.fbtrace_id = fbtrace_id

    @property
    def human_message(self) -> str:
        """回傳人類可讀的中文錯誤訊息"""
        return _human_error_message(self.code, self.subcode)


class FBGraphAPI:
    """Facebook Graph API 發文引擎 (Enhanced)

    支援：
      - 純文字發文
      - 文字 + 連結發文
      - 本機圖片發文（單張/多張）
      - 遠端 URL 圖片發文（支援混合本機+URL）
      - 影片發文（含自動分塊上傳）
    """

    def __init__(self, page_id: str, access_token: str):
        self.page_id = page_id
        self.access_token = access_token
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "FB-Auto-Poster/3.0",
        })

    # ════════════════════════════════════════════════════
    # 純文字發文
    # ════════════════════════════════════════════════════

    def post_text(self, content: str) -> dict:
        """純文字貼文 → /{page-id}/feed"""
        data = {
            "message": content,
            "access_token": self.access_token,
        }
        return self._call("POST", f"/{self.page_id}/feed", data=data)

    # ════════════════════════════════════════════════════
    # 文字 + 連結發文
    # ════════════════════════════════════════════════════

    def post_text_with_link(self, content: str, link_url: str) -> dict:
        """文字 + 連結貼文 → /{page-id}/feed

        FB 會自動抓取連結的 og:title / og:image 產生預覽卡片。

        Args:
            content: 貼文文字
            link_url: 要分享的連結（會自動產生預覽）

        Returns:
            {"id": "post_id", ...}
        """
        data = {
            "message": content,
            "link": link_url,
            "access_token": self.access_token,
        }
        return self._call("POST", f"/{self.page_id}/feed", data=data)

    # ════════════════════════════════════════════════════
    # 圖片發文
    # ════════════════════════════════════════════════════

    def post_photo(self, image_path_or_url: str, caption: str = "") -> dict:
        """單張圖片貼文 → /{page-id}/photos

        支援本機路徑和遠端 URL。

        Args:
            image_path_or_url: 本機圖片路徑 或 遠端圖片 URL
            caption: 圖片說明（選填）
        """
        is_url = image_path_or_url.startswith(("http://", "https://"))
        return self._post_single_photo(image_path_or_url, caption, is_url=is_url)

    def post_remote_photo(self, image_url: str, caption: str = "") -> dict:
        """從遠端 URL 發佈圖片 → /{page-id}/photos

        FB 會直接從提供的 URL 下載圖片，無需先下載到本機。
        """
        return self._post_single_photo(image_url, caption, is_url=True)

    def _post_single_photo(self, source: str, caption: str = "", is_url: bool = False) -> dict:
        """內部方法：發佈單張圖片"""
        url = f"{GRAPH_API_BASE}/{self.page_id}/photos"
        params = {
            "access_token": self.access_token,
            "caption": caption,
            "published": "true",
        }

        if is_url:
            # 遠端 URL 模式：直接傳 url 參數
            data = {"url": source}
            resp = self._session.post(
                url, params=params, data=data, timeout=DEFAULT_TIMEOUT
            )
        else:
            # 本機檔案模式
            try:
                with open(source, "rb") as f:
                    files = {"source": f}
                    resp = self._session.post(
                        url, params=params, files=files, timeout=DEFAULT_TIMEOUT
                    )
            except FileNotFoundError:
                raise FBGraphAPIError(f"圖片檔案不存在: {source}")

        return self._handle_response(resp)

    def post_with_images(self, content: str, image_paths: list[str]) -> dict:
        """多張圖片貼文（先上傳 media → feed with attached_media）

        支援本機路徑和遠端 URL 混合。
        若只有一張圖片，直接用 post_photo() 更單純。
        """
        if not image_paths:
            return self.post_text(content)

        if len(image_paths) == 1:
            return self.post_photo(image_paths[0], caption=content)

        # 多張圖片：先上傳每張，取得 media_fbid
        media_ids = []
        for path in image_paths:
            try:
                is_url = path.startswith(("http://", "https://"))
                media = self._upload_photo_unpublished(path, is_url=is_url)
                media_ids.append(media["id"])
            except Exception as e:
                log("GRAPH", self.page_id, f"上傳圖片失敗 {path}: {e}", "⚠️")

        if not media_ids:
            # 全部上傳失敗，退回落文字
            return self.post_text(content)

        # 貼文時帶 attached_media
        attached = [{"media_fbid": mid} for mid in media_ids]
        data = {
            "message": content,
            "attached_media": json.dumps(attached),
            "access_token": self.access_token,
        }
        return self._call("POST", f"/{self.page_id}/feed", data=data)

    # ════════════════════════════════════════════════════
    # 影片發文
    # ════════════════════════════════════════════════════

    def post_video(
        self,
        video_path: str,
        title: str = "",
        description: str = "",
        thumb_path: str = "",
    ) -> dict:
        """影片發文 → /{page-id}/videos

        支援自動分塊上傳（大於 10MB 的影片自動分塊）。
        支援自訂縮圖。

        Args:
            video_path: 本機影片檔案路徑
            title: 影片標題（選填）
            description: 影片說明（選填）
            thumb_path: 縮圖路徑（選填）

        Returns:
            {"id": "video_id", ...}
        """
        if not os.path.isfile(video_path):
            raise FBGraphAPIError(f"影片檔案不存在: {video_path}")

        file_size = os.path.getsize(video_path)

        # 小檔案直接上傳，大檔案走分塊上傳
        if file_size <= VIDEO_CHUNK_SIZE:
            return self._upload_video_simple(video_path, title, description, thumb_path)
        else:
            return self._upload_video_chunked(video_path, file_size, title, description, thumb_path)

    def _upload_video_simple(
        self, video_path: str, title: str, description: str, thumb_path: str
    ) -> dict:
        """簡單影片上傳（< 10MB，單次 POST）"""
        url = f"{GRAPH_VIDEO_BASE}/{self.page_id}/videos"
        data = {
            "access_token": self.access_token,
            "title": title,
            "description": description,
        }
        try:
            with open(video_path, "rb") as f:
                files = {"source": f}
                if thumb_path and os.path.isfile(thumb_path):
                    files["thumb"] = open(thumb_path, "rb")
                resp = self._session.post(
                    url, data=data, files=files, timeout=VIDEO_UPLOAD_TIMEOUT
                )
            return self._handle_response(resp)
        except Exception as e:
            raise FBGraphAPIError(f"影片上傳失敗: {e}")

    def _upload_video_chunked(
        self, video_path: str, file_size: int,
        title: str, description: str, thumb_path: str,
    ) -> dict:
        """分塊影片上傳（≥ 10MB，Resumable Upload）

        FB 分塊上傳流程：
        1. POST /{page-id}/videos 啟動上傳（不帶 source）
        2. POST /{upload_session_id} 逐塊上傳
        3. POST /{upload_session_id} 完成上傳
        """
        # Step 1: 啟動上傳 session
        init_url = f"{GRAPH_VIDEO_BASE}/{self.page_id}/videos"
        init_data = {
            "access_token": self.access_token,
            "upload_phase": "start",
            "file_size": file_size,
            "title": title,
            "description": description,
        }

        log("GRAPH", self.page_id, f"影片 {os.path.basename(video_path)} ({file_size/1024/1024:.1f}MB) 啟動分塊上傳...", "⏳")

        try:
            init_resp = self._session.post(
                init_url, data=init_data, timeout=DEFAULT_TIMEOUT
            )
            init_result = self._handle_response(init_resp)
            upload_session_id = init_result.get("upload_session_id")
            video_id = init_result.get("video_id", "")

            if not upload_session_id:
                raise FBGraphAPIError("無法取得上傳 session ID")

            log("GRAPH", self.page_id, f"上傳 session: {upload_session_id[:8]}...", "📤")

            # Step 2: 逐塊上傳
            with open(video_path, "rb") as f:
                offset = 0
                while offset < file_size:
                    chunk = f.read(VIDEO_CHUNK_SIZE)
                    chunk_len = len(chunk)
                    end_offset = offset + chunk_len - 1

                    transfer_url = f"{GRAPH_VIDEO_BASE}/{upload_session_id}"
                    transfer_headers = {
                        "Authorization": f"OAuth {self.access_token}",
                        "Content-Range": f"bytes {offset}-{end_offset}/{file_size}",
                        "Content-Type": "application/octet-stream",
                    }

                    transfer_resp = requests.post(
                        transfer_url,
                        data=chunk,
                        headers=transfer_headers,
                        timeout=VIDEO_UPLOAD_TIMEOUT,
                    )

                    if transfer_resp.status_code not in (200, 201):
                        raise FBGraphAPIError(
                            f"影片分塊上傳失敗 (offset={offset}, HTTP {transfer_resp.status_code}): "
                            f"{transfer_resp.text[:200]}"
                        )

                    offset += chunk_len

                    # 進度 log（每 50MB 或最後一塊）
                    if offset >= file_size or offset % (50 * 1024 * 1024) < VIDEO_CHUNK_SIZE:
                        pct = min(100, int(offset / file_size * 100))
                        log("GRAPH", self.page_id, f"影片上傳進度: {pct}%", "📤")

            # Step 3: 完成上傳
            if thumb_path and os.path.isfile(thumb_path):
                # 如果有縮圖，在 finish 時附上
                finish_url = f"{GRAPH_VIDEO_BASE}/{upload_session_id}"
                finish_data = {
                    "access_token": self.access_token,
                    "upload_phase": "finish",
                    "title": title,
                    "description": description,
                }
                try:
                    with open(thumb_path, "rb") as tf:
                        finish_files = {"thumb": tf}
                        finish_resp = requests.post(
                            finish_url, data=finish_data,
                            files=finish_files, timeout=VIDEO_UPLOAD_TIMEOUT,
                        )
                except Exception:
                    # 縮圖失敗不影響主上傳
                    finish_data.pop("thumb", None)
                    finish_resp = requests.post(
                        finish_url, data=finish_data, timeout=VIDEO_UPLOAD_TIMEOUT,
                    )
            else:
                finish_url = f"{GRAPH_VIDEO_BASE}/{upload_session_id}"
                finish_data = {
                    "access_token": self.access_token,
                    "upload_phase": "finish",
                    "title": title,
                    "description": description,
                }
                finish_resp = requests.post(
                    finish_url, data=finish_data, timeout=VIDEO_UPLOAD_TIMEOUT,
                )

            finish_result = self._handle_response(finish_resp)
            log("GRAPH", self.page_id, f"影片上傳成功! video_id={finish_result.get('id', video_id)}", "✅")
            return finish_result

        except FBGraphAPIError:
            raise
        except Exception as e:
            raise FBGraphAPIError(f"影片分塊上傳失敗: {e}")

    # ════════════════════════════════════════════════════
    # 社團發文（通常不可用）
    # ════════════════════════════════════════════════════

    def post_to_group(self, group_id: str, content: str, image_paths: list[str] = None) -> dict:
        """發文到社團（需 publish_to_groups 權限，Meta 已棄用，不可用）"""
        data = {
            "message": content,
            "access_token": self.access_token,
        }
        if image_paths:
            attached = []
            for p in image_paths:
                is_url = p.startswith(("http://", "https://"))
                media = self._upload_photo_unpublished(p, is_url=is_url)
                attached.append({"media_fbid": media["id"]})
            data["attached_media"] = json.dumps(attached)
        return self._call("POST", f"/{group_id}/feed", data=data)

    # ════════════════════════════════════════════════════
    # Page 資訊
    # ════════════════════════════════════════════════════

    def get_page_info(self) -> dict:
        """取得粉絲專頁基本資訊（驗證 token 是否有管理權限）"""
        return self._call("GET", f"/{self.page_id}", params={
            "fields": "id,name,about,link,fan_count",
            "access_token": self.access_token,
        })

    # ════════════════════════════════════════════════════
    # Token 工具
    # ════════════════════════════════════════════════════

    @staticmethod
    def validate_token(access_token: str, app_token: str = "") -> dict:
        """驗證 token 有效性

        Args:
            access_token: 要驗證的 token
            app_token: App 的 access_token (格式: {app_id}|{app_secret})

        Returns:
            {"is_valid": bool, "expires_at": int, "scopes": [...], "type": "...",
             "missing_scopes": [...]}
        """
        params = {
            "input_token": access_token,
            "access_token": app_token or access_token,
        }
        try:
            resp = requests.get(
                f"{GRAPH_API_BASE}/debug_token",
                params=params, timeout=DEFAULT_TIMEOUT,
            )
            data = resp.json()
            if "data" in data:
                d = data["data"]
                scopes = d.get("scopes", [])
                # 分析缺少的權限
                missing = [s for s in _REQUIRED_SCOPES if s not in scopes]
                return {
                    "is_valid": d.get("is_valid", False),
                    "expires_at": d.get("expires_at", 0),
                    "scopes": scopes,
                    "type": d.get("type", ""),
                    "app_id": d.get("app_id", ""),
                    "granular_scopes": d.get("granular_scopes", []),
                    "missing_scopes": missing,
                }
            return {"is_valid": False, "error": data.get("error", {}).get("message", "")}
        except Exception as e:
            return {"is_valid": False, "error": str(e)}

    @staticmethod
    def get_required_scopes_help() -> str:
        """回傳必要權限的中文說明"""
        lines = ["FB Graph API 發文所需權限："]
        for scope, desc in _REQUIRED_SCOPES.items():
            lines.append(f"  • {scope}: {desc}")
        return "\n".join(lines)

    @staticmethod
    def exchange_long_lived_token(short_token: str, app_id: str, app_secret: str) -> dict:
        """將短效 user access token 交換為長效（60 天）

        Returns:
            {"access_token": "...", "token_type": "...", "expires_in": ...}
        """
        params = {
            "grant_type": "fb_exchange_token",
            "client_id": app_id,
            "client_secret": app_secret,
            "fb_exchange_token": short_token,
        }
        try:
            resp = requests.get(
                f"{GRAPH_API_BASE}/oauth/access_token",
                params=params, timeout=DEFAULT_TIMEOUT,
            )
            return resp.json()
        except Exception as e:
            return {"error": str(e)}

    # ════════════════════════════════════════════════════
    # 內部方法
    # ════════════════════════════════════════════════════

    def _upload_photo_unpublished(self, source: str, is_url: bool = False) -> dict:
        """上傳圖片但不發布，回傳 media ID（供 attached_media 使用）

        支援本機路徑和遠端 URL。
        """
        url = f"{GRAPH_API_BASE}/{self.page_id}/photos"
        params = {
            "access_token": self.access_token,
            "published": "false",
        }

        if is_url:
            data = {"url": source}
            resp = self._session.post(url, params=params, data=data, timeout=DEFAULT_TIMEOUT)
        else:
            with open(source, "rb") as f:
                files = {"source": f}
                resp = self._session.post(url, params=params, files=files, timeout=DEFAULT_TIMEOUT)
        return self._handle_response(resp)

    def _call(self, method: str, path: str, data: dict = None, params: dict = None) -> dict:
        """統一 API 呼叫（含 retry + 錯誤處理）"""
        url = f"{GRAPH_API_BASE}{path}"
        params = params or {}
        if "access_token" not in params:
            params["access_token"] = self.access_token

        last_error = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                if method == "GET":
                    resp = self._session.get(url, params=params, timeout=DEFAULT_TIMEOUT)
                else:
                    resp = self._session.post(url, params=params, data=data, timeout=DEFAULT_TIMEOUT)
                return self._handle_response(resp)
            except FBGraphAPIError as e:
                # 如果是 rate limit (code 4, 17, 32) 或暫時性錯誤，重試
                if e.code in (4, 17, 32, 341, 368) and attempt < MAX_RETRIES:
                    log("GRAPH", self.page_id,
                        f"API 錯誤 ({e.code}), {attempt}/{MAX_RETRIES} 重試中...", "⚠️")
                    time.sleep(RETRY_DELAY * attempt)
                    last_error = e
                    continue
                raise
            except requests.exceptions.Timeout as e:
                if attempt < MAX_RETRIES:
                    log("GRAPH", self.page_id,
                        f"Timeout, {attempt}/{MAX_RETRIES} 重試中...", "⚠️")
                    time.sleep(RETRY_DELAY * attempt)
                    last_error = FBGraphAPIError(str(e))
                    continue
                raise FBGraphAPIError(f"API 連線逾時 (嘗試 {MAX_RETRIES} 次): {e}")
            except requests.exceptions.RequestException as e:
                raise FBGraphAPIError(f"HTTP 請求失敗: {e}")

        raise last_error or FBGraphAPIError("API 呼叫失敗（重試已耗盡）")

    def _handle_response(self, resp: requests.Response) -> dict:
        """解析 Graph API 回應，成功回傳 data dict，失敗拋 FBGraphAPIError"""
        try:
            body = resp.json()
        except ValueError:
            raise FBGraphAPIError(f"非 JSON 回應 ({resp.status_code}): {resp.text[:200]}")

        if resp.status_code >= 400 or "error" in body:
            err = body.get("error", {})
            raise FBGraphAPIError(
                message=err.get("message", f"HTTP {resp.status_code}"),
                code=err.get("code", resp.status_code),
                subcode=err.get("error_subcode", 0),
                fbtrace_id=err.get("fbtrace_id", ""),
            )

        return body


# ════════════════════════════════════════════════════
# 便利函式
# ════════════════════════════════════════════════════

def get_stored_pages() -> list[dict]:
    """取得所有已儲存的 FB Page 設定（供 UI 使用）"""
    mgr = FBPageManager()
    return [{
        "page_id": p.page_id,
        "page_name": p.page_name,
        "linked_account_id": p.linked_account_id,
        "created_at": p.created_at,
        "has_token": bool(p.access_token_encrypted),
    } for p in mgr.list_all()]


def post_via_api(
    page_id: str,
    content: str,
    image_paths: list[str] = None,
    video_path: str = "",
    link_url: str = "",
    groups: list[str] = None,
) -> dict:
    """便利函式：用 Graph API 發文，自動讀取已儲存的 token

    Args:
        page_id: FB Page ID
        content: 貼文內容
        image_paths: 圖片路徑列表（支援本機路徑和遠端 URL，選填）
        video_path: 影片檔案路徑（選填）
        link_url: 要附加的連結（選填）
        groups: 目標社團 ID 列表（選填，需 publish_to_groups 權限）

    Returns:
        {"success": True/False, "post_id": "...", "error": "...", "type": "text"/"image"/"video"/"link"}
    """
    mgr = FBPageManager()
    cfg = mgr.get(page_id)
    if not cfg or not cfg.access_token_encrypted:
        return {"success": False, "error": f"Page {page_id} 尚未設定 API token — 請在「檔案 → FB API 設定」新增"}

    token = cfg.access_token
    if not token:
        return {"success": False, "error": f"Page {page_id} token 解密失敗 — 請重新設定"}

    api = FBGraphAPI(page_id, token)

    try:
        # 優先級：影片 > 圖片 > 連結 > 純文字
        if video_path:
            result = api.post_video(video_path, title=content.split("\n")[0][:100],
                                   description=content)
            post_id = result.get("id", "")
            log("GRAPH", page_id, f"影片發文成功 video_id={post_id}", "✅")
            return {"success": True, "post_id": post_id, "type": "video"}

        if groups:
            results = []
            for gid in groups:
                result = api.post_to_group(gid, content, image_paths)
                results.append({"group": gid, "post_id": result.get("id", "")})
            log("GRAPH", page_id, f"社團發文完成: {len(groups)} 個", "✅")
            return {"success": True, "results": results, "type": "group"}

        if image_paths:
            result = api.post_with_images(content, image_paths)
            post_id = result.get("id", "")
            img_count = len(image_paths)
            log("GRAPH", page_id, f"圖片發文成功 ({img_count} 張) post_id={post_id}", "✅")
            return {"success": True, "post_id": post_id, "type": "image"}

        if link_url:
            result = api.post_text_with_link(content, link_url)
            post_id = result.get("id", "")
            log("GRAPH", page_id, f"連結貼文成功 post_id={post_id}", "✅")
            return {"success": True, "post_id": post_id, "type": "link"}

        # 純文字
        result = api.post_text(content)
        post_id = result.get("id", "")
        log("GRAPH", page_id, f"文字發文成功 post_id={post_id}", "✅")
        return {"success": True, "post_id": post_id, "type": "text"}

    except FBGraphAPIError as e:
        err_msg = f"{e.human_message}\n原始錯誤: {str(e)}"
        log("GRAPH", page_id, f"發文失敗: {err_msg}", "❌")
        return {"success": False, "error": err_msg}
    except Exception as e:
        err_msg = f"發文異常: {e}"
        log("GRAPH", page_id, err_msg, "❌")
        return {"success": False, "error": err_msg}
