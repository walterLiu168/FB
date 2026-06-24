"""貼文資料庫（PostStore）— 儲存貼文 URL / 刪除排程 / 狀態

目標：
1) 每篇貼文都有獨立的 delete_at（到點精準刪除）
2) 仍保留每週補漏刪（掃描超過 N 天仍未刪掉或沒有 URL 的紀錄）
3) 純本機 SQLite，零外部依賴
"""

from __future__ import annotations

import os
import sqlite3
import threading
from datetime import datetime, timedelta
from typing import Optional

_lock = threading.Lock()


def _db_path() -> str:
    base = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "posts.db")


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id TEXT NOT NULL,
            target_type TEXT NOT NULL DEFAULT 'wall',   -- wall | group
            target_url TEXT DEFAULT '',                 -- group url (若為 group)
            post_url TEXT DEFAULT '',                   -- permalink（若抓得到）
            detail TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            delete_at TEXT DEFAULT '',                  -- YYYY-MM-DD HH:MM
            status TEXT NOT NULL DEFAULT 'active',      -- active | deleted | failed
            retry_count INTEGER NOT NULL DEFAULT 0,
            last_error TEXT DEFAULT ''
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_posts_delete_at ON posts(delete_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_posts_status ON posts(status)")
    conn.commit()
    return conn


def add_post(
    account_id: str,
    target_type: str,
    target_url: str = "",
    post_url: str = "",
    detail: str = "",
    delete_at: str = "",
) -> int:
    """新增貼文紀錄，回傳 row id"""
    with _lock:
        conn = _get_conn()
        created_at = datetime.now().isoformat(timespec="seconds")
        cur = conn.execute(
            """
            INSERT INTO posts (account_id, target_type, target_url, post_url, detail, created_at, delete_at, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'active')
            """,
            (account_id, target_type, target_url or "", post_url or "", detail or "", created_at, delete_at or ""),
        )
        conn.commit()
        rid = cur.lastrowid
        conn.close()
        return int(rid or 0)


def mark_deleted(post_id: int) -> bool:
    with _lock:
        conn = _get_conn()
        conn.execute("UPDATE posts SET status='deleted', last_error='' WHERE id=?", (post_id,))
        conn.commit()
        ok = conn.total_changes > 0
        conn.close()
        return ok


def mark_failed(post_id: int, error: str) -> bool:
    with _lock:
        conn = _get_conn()
        conn.execute(
            "UPDATE posts SET status='failed', retry_count=retry_count+1, last_error=? WHERE id=?",
            (error[:200], post_id),
        )
        conn.commit()
        ok = conn.total_changes > 0
        conn.close()
        return ok


def get_due(now: Optional[datetime] = None, limit: int = 50) -> list[dict]:
    """取得已到期要刪除的貼文（delete_at <= now）"""
    now = now or datetime.now()
    now_s = now.strftime("%Y-%m-%d %H:%M")
    conn = _get_conn()
    rows = conn.execute(
        """
        SELECT * FROM posts
        WHERE status != 'deleted'
          AND delete_at != ''
          AND delete_at <= ?
        ORDER BY delete_at ASC
        LIMIT ?
        """,
        (now_s, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_weekly_candidates(days: int = 7, limit: int = 50) -> list[dict]:
    """每週補漏刪：抓出超過 N 天仍未刪的貼文

    條件：
    - status != deleted
    - created_at <= now - days
    """
    cutoff = datetime.now() - timedelta(days=max(1, int(days)))
    cutoff_s = cutoff.isoformat(timespec="seconds")
    conn = _get_conn()
    rows = conn.execute(
        """
        SELECT * FROM posts
        WHERE status != 'deleted'
          AND created_at <= ?
        ORDER BY created_at ASC
        LIMIT ?
        """,
        (cutoff_s, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

