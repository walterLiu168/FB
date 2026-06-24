"""物件儲存後端 — SQLite 可選替代 JSON 檔案儲存

純本地儲存，零外部依賴。提供與 listings.json 相同的存取介面。
當 JSON 檔案變大時 (>100 筆)，SQLite 搜尋/排序效能明顯優於 JSON。
"""
import sqlite3
import json
import os
import threading
from datetime import datetime
from typing import Optional

_lock = threading.Lock()


def _db_path() -> str:
    base = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "listings.db")


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            template TEXT DEFAULT '',
            title TEXT DEFAULT '',
            price TEXT DEFAULT '',
            location TEXT DEFAULT '',
            size TEXT DEFAULT '',
            rooms TEXT DEFAULT '',
            type TEXT DEFAULT '',
            floor TEXT DEFAULT '',
            age TEXT DEFAULT '',
            parking TEXT DEFAULT '',
            orientation TEXT DEFAULT '',
            road_width TEXT DEFAULT '',
            land_size TEXT DEFAULT '',
            intro TEXT DEFAULT '',
            image TEXT DEFAULT '',
            date TEXT DEFAULT '',
            status TEXT DEFAULT 'active',
            extra TEXT DEFAULT '{}'
        )
    """)
    conn.commit()
    return conn


def insert(data: dict) -> int:
    """新增一筆物件
    
    Returns:
        新物件的 id
    """
    with _lock:
        conn = _get_conn()
        fields = [
            "template", "title", "price", "location", "size",
            "rooms", "type", "floor", "age", "parking",
            "orientation", "road_width", "land_size", "intro",
            "image", "date", "status"
        ]
        vals = {f: data.get(f, "") for f in fields}
        vals["date"] = vals["date"] or datetime.now().isoformat()
        vals["status"] = vals["status"] or "active"
        
        columns = ", ".join(vals.keys())
        placeholders = ", ".join([":" + f for f in vals.keys()])
        cursor = conn.execute(
            f"INSERT INTO listings ({columns}) VALUES ({placeholders})",
            vals
        )
        conn.commit()
        row_id = cursor.lastrowid
        conn.close()
        return row_id


def get_all(status: str = None, search: str = None, limit: int = 200) -> list[dict]:
    """讀取所有物件
    
    Args:
        status: None=全部, "active"=上架中, "deleted"=已下架
        search: 文字搜尋 (標題/地點)
        limit: 最大回傳筆數
    """
    conn = _get_conn()
    conditions = []
    params = {}
    
    if status:
        conditions.append("status = :status")
        params["status"] = status
    
    if search:
        conditions.append("(title LIKE :s OR location LIKE :s OR intro LIKE :s)")
        params["s"] = f"%{search}%"
    
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    query = f"SELECT * FROM listings {where} ORDER BY date DESC LIMIT :limit"
    params["limit"] = limit
    
    rows = conn.execute(query, params).fetchall()
    conn.close()
    
    return [dict(r) for r in rows]


def update(listing_id: int, data: dict) -> bool:
    """更新指定物件"""
    with _lock:
        conn = _get_conn()
        allowed = [
            "template", "title", "price", "location", "size",
            "rooms", "type", "floor", "age", "parking",
            "orientation", "road_width", "land_size", "intro",
            "image", "status"
        ]
        updates = {k: v for k, v in data.items() if k in allowed}
        if not updates:
            return False
        
        sets = ", ".join([f"{k} = :{k}" for k in updates])
        updates["_id"] = listing_id
        conn.execute(f"UPDATE listings SET {sets} WHERE id = :_id", updates)
        conn.commit()
        conn.close()
        return True


def delete(listing_id: int, soft: bool = True) -> bool:
    """刪除物件 (預設軟刪除)
    
    軟刪除: status = "deleted"
    硬刪除: 從資料庫移除
    """
    with _lock:
        conn = _get_conn()
        if soft:
            conn.execute("UPDATE listings SET status = 'deleted' WHERE id = ?", (listing_id,))
        else:
            conn.execute("DELETE FROM listings WHERE id = ?", (listing_id,))
        conn.commit()
        affected = conn.total_changes
        conn.close()
        return affected > 0


def get_stats() -> dict:
    """取得統計資訊"""
    conn = _get_conn()
    total = conn.execute("SELECT COUNT(*) FROM listings WHERE status != 'deleted'").fetchone()[0]
    active = conn.execute("SELECT COUNT(*) FROM listings WHERE status = 'active'").fetchone()[0]
    
    # 依類型分組
    type_counts = {}
    for row in conn.execute(
        "SELECT type, COUNT(*) as cnt FROM listings WHERE status != 'deleted' GROUP BY type"
    ).fetchall():
        type_counts[row["type"] or "其他"] = row["cnt"]
    
    conn.close()
    return {
        "total": total,
        "active": active,
        "by_type": type_counts,
    }


def sync_to_json(json_path: str):
    """將 SQLite 內容同步輸出為 JSON 檔案 (供網站使用)"""
    listings = get_all(status="active")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(listings, f, ensure_ascii=False, indent=2)


def migrate_from_json(json_path: str) -> int:
    """從 JSON 檔案遷移到 SQLite
    
    Returns:
        遷移的筆數
    """
    if not os.path.exists(json_path):
        return 0
    
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    if not isinstance(data, list):
        return 0
    
    count = 0
    for item in data:
        if isinstance(item, dict):
            # 避免重複插入
            existing = get_all(search=item.get("title", ""))
            matches = [e for e in existing if e.get("title") == item.get("title") and e.get("date") == item.get("date", "")]
            if not matches:
                insert(item)
                count += 1
    
    return count
