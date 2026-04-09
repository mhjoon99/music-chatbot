import sqlite3
import uuid
import json
from datetime import datetime
from app.config import SQLITE_DB_PATH

class ConversationManager:
    def __init__(self, db_path: str = None):
        self.db_path = db_path or SQLITE_DB_PATH
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            created_at TEXT,
            psychological_profile TEXT DEFAULT '{}'
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS conversations (
            conv_id TEXT PRIMARY KEY,
            user_id TEXT,
            created_at TEXT,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS messages (
            msg_id TEXT PRIMARY KEY,
            conv_id TEXT,
            role TEXT,
            content TEXT,
            metadata TEXT DEFAULT '{}',
            timestamp TEXT,
            FOREIGN KEY (conv_id) REFERENCES conversations(conv_id)
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS summaries (
            summary_id TEXT PRIMARY KEY,
            conv_id TEXT,
            summary_text TEXT,
            turn_range TEXT,
            created_at TEXT,
            FOREIGN KEY (conv_id) REFERENCES conversations(conv_id)
        )""")
        conn.commit()
        conn.close()

    def get_or_create_user(self, user_id: str = None) -> str:
        if not user_id:
            user_id = str(uuid.uuid4())
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO users (user_id, created_at) VALUES (?, ?)",
                  (user_id, datetime.now().isoformat()))
        conn.commit()
        conn.close()
        return user_id

    def create_conversation(self, user_id: str) -> str:
        conv_id = str(uuid.uuid4())
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("INSERT INTO conversations (conv_id, user_id, created_at) VALUES (?, ?, ?)",
                  (conv_id, user_id, datetime.now().isoformat()))
        conn.commit()
        conn.close()
        return conv_id

    def save_message(self, conv_id: str, role: str, content: str, metadata: dict = None):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        meta_json = json.dumps(metadata, ensure_ascii=False) if metadata else "{}"
        c.execute("INSERT INTO messages (msg_id, conv_id, role, content, metadata, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                  (str(uuid.uuid4()), conv_id, role, content, meta_json, datetime.now().isoformat()))
        conn.commit()
        conn.close()

    def get_messages(self, conv_id: str, limit: int = 10) -> list:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT role, content, metadata FROM messages WHERE conv_id = ? ORDER BY timestamp DESC LIMIT ?",
                  (conv_id, limit))
        rows = c.fetchall()
        conn.close()
        messages = []
        for r in reversed(rows):
            msg = {"role": r[0], "content": r[1]}
            if r[2] and r[2] != "{}":
                try:
                    meta = json.loads(r[2])
                    msg.update(meta)
                except (json.JSONDecodeError, TypeError):
                    pass
            messages.append(msg)
        return messages

    def get_message_count(self, conv_id: str) -> int:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM messages WHERE conv_id = ?", (conv_id,))
        count = c.fetchone()[0]
        conn.close()
        return count

    def save_summary(self, conv_id: str, summary: str, turn_range: str):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("INSERT INTO summaries (summary_id, conv_id, summary_text, turn_range, created_at) VALUES (?, ?, ?, ?, ?)",
                  (str(uuid.uuid4()), conv_id, summary, turn_range, datetime.now().isoformat()))
        conn.commit()
        conn.close()

    def get_latest_summary(self, conv_id: str) -> str:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT summary_text FROM summaries WHERE conv_id = ? ORDER BY created_at DESC LIMIT 1",
                  (conv_id,))
        row = c.fetchone()
        conn.close()
        return row[0] if row else ""

    def get_latest_conversation(self, user_id: str) -> str | None:
        """사용자의 가장 최근 대화 ID를 반환 (없으면 None)"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT conv_id FROM conversations WHERE user_id = ? ORDER BY created_at DESC LIMIT 1",
                  (user_id,))
        row = c.fetchone()
        conn.close()
        return row[0] if row else None

    def get_user_summary(self, user_id: str) -> str:
        """사용자의 모든 대화에서 가장 최근 요약을 가져옴 (재접속 시 컨텍스트 복원용)"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""
            SELECT s.summary_text FROM summaries s
            JOIN conversations c ON s.conv_id = c.conv_id
            WHERE c.user_id = ?
            ORDER BY s.created_at DESC LIMIT 1
        """, (user_id,))
        row = c.fetchone()
        conn.close()
        return row[0] if row else ""

    def get_summary_and_recent_messages(self, conv_id: str) -> dict:
        """요약된 범위는 요약 텍스트로, 이후 메시지는 원본으로 반환.
        Returns: {"summary": str|None, "messages": list}
        """
        # 최신 요약의 turn_range 가져오기
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(
            "SELECT summary_text, turn_range FROM summaries WHERE conv_id = ? ORDER BY created_at DESC LIMIT 1",
            (conv_id,))
        row = c.fetchone()
        conn.close()

        if not row or not row[0] or not row[0].strip():
            # 요약 없음 → 전체 메시지 반환
            return {"summary": None, "messages": self.get_messages(conv_id, limit=50)}

        summary_text = row[0]
        turn_range = row[1]  # e.g. "1-10"

        # 요약된 메시지 수 파싱
        try:
            summarized_count = int(turn_range.split("-")[-1])
        except (ValueError, IndexError):
            return {"summary": None, "messages": self.get_messages(conv_id, limit=50)}

        # 요약 이후 메시지만 가져오기 (ASC 정렬 + OFFSET)
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(
            "SELECT role, content, metadata FROM messages WHERE conv_id = ? ORDER BY timestamp ASC LIMIT -1 OFFSET ?",
            (conv_id, summarized_count))
        rows = c.fetchall()
        conn.close()

        recent_messages = []
        for r in rows:
            msg = {"role": r[0], "content": r[1]}
            if r[2] and r[2] != "{}":
                try:
                    meta = json.loads(r[2])
                    msg.update(meta)
                except (json.JSONDecodeError, TypeError):
                    pass
            recent_messages.append(msg)

        return {"summary": summary_text, "messages": recent_messages}

    def get_conversation_count(self, user_id: str) -> int:
        """사용자의 총 대화 세션 수"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM conversations WHERE user_id = ?", (user_id,))
        count = c.fetchone()[0]
        conn.close()
        return count
