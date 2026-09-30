import os
import sqlite3
import threading
from datetime import datetime, timezone

from config import DB_FILE


# ============================================================
# SQLite Lock
# ============================================================
_db_lock = threading.Lock()


# ============================================================
# 获取数据库连接
# ============================================================
def get_connection():
    db_dir = os.path.dirname(os.path.abspath(DB_FILE))

    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    return sqlite3.connect(
        DB_FILE,
        timeout=30,
    )


# ============================================================
# 初始化数据库
# ============================================================
def init_database():
    with _db_lock:
        conn = get_connection()

        try:
            cursor = conn.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS group_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    user_name TEXT,
                    text TEXT,
                    created_at TEXT
                )
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_group_messages_chat
                ON group_messages(chat_id)
            """)

            # 不修改现有表结构；额外索引只用于加快重复 Update 检查。
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_group_messages_chat_message
                ON group_messages(chat_id, message_id)
            """)

            conn.commit()

        finally:
            conn.close()


# ============================================================
# 保存群聊消息
# ============================================================
def save_message(
    chat_id,
    message_id,
    user_name,
    text,
):
    if not text:
        return

    with _db_lock:
        conn = get_connection()

        try:
            cursor = conn.cursor()

            # Telegram 更新在重试/网络异常时可能重复到达。
            # 不改表结构，用 NOT EXISTS 避免同一群的同一 message_id 重复保存。
            cursor.execute("""
                INSERT INTO group_messages
                (
                    chat_id,
                    message_id,
                    user_name,
                    text,
                    created_at
                )
                SELECT ?, ?, ?, ?, ?
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM group_messages
                    WHERE chat_id = ? AND message_id = ?
                )
            """, (
                chat_id,
                message_id,
                user_name,
                text,
                datetime.now(timezone.utc).isoformat(),
                chat_id,
                message_id,
            ))

            conn.commit()

        finally:
            conn.close()


# ============================================================
# 获取群聊消息数量
# ============================================================
def get_message_count(chat_id):
    with _db_lock:
        conn = get_connection()

        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*)
                FROM group_messages
                WHERE chat_id = ?
            """, (chat_id,))

            row = cursor.fetchone()
            return row[0] if row else 0

        finally:
            conn.close()


# ============================================================
# 获取群聊消息
# ============================================================
def get_messages(chat_id):
    with _db_lock:
        conn = get_connection()

        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    message_id,
                    user_name,
                    text,
                    created_at
                FROM group_messages
                WHERE chat_id = ?
                ORDER BY id ASC
            """, (chat_id,))

            rows = cursor.fetchall()

        finally:
            conn.close()

    return [
        {
            "message_id": row[0],
            "user": row[1],
            "text": row[2],
            "created_at": row[3],
        }
        for row in rows
    ]


# ============================================================
# 删除已经总结的消息
# ============================================================
def clear_messages(chat_id):
    with _db_lock:
        conn = get_connection()

        try:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM group_messages
                WHERE chat_id = ?
            """, (chat_id,))

            conn.commit()

        finally:
            conn.close()


# ============================================================
# 原子获取并清空群聊消息
# ============================================================
def get_and_clear_messages(chat_id):
    """Return all messages for a chat and clear them in one transaction."""
    with _db_lock:
        conn = get_connection()

        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    message_id,
                    user_name,
                    text,
                    created_at
                FROM group_messages
                WHERE chat_id = ?
                ORDER BY id ASC
            """, (chat_id,))

            rows = cursor.fetchall()

            cursor.execute("""
                DELETE FROM group_messages
                WHERE chat_id = ?
            """, (chat_id,))

            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    return [
        {
            "message_id": row[0],
            "user": row[1],
            "text": row[2],
            "created_at": row[3],
        }
        for row in rows
    ]
