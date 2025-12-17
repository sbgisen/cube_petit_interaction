#!/usr/bin/env python

# Copyright (c) 2025 SoftBank Corp.
#
# <<licensetext>>

from dataclasses import dataclass
import sqlite3
import time
from typing import List, Optional
import uuid

# =========================
# Data Class
# =========================


@dataclass
class UserRecord:
    user_id: str  # uuid
    confidence: float  # 0.0 - 1.0
    interaction_count: int
    last_seen: float  # time.time()

    display_name: Optional[str] = None
    name_confidence: float = 0.0


class UserStore:

    def __init__(self, db_path: str = 'users.db'):
        self.db_path = db_path
        self.conn = sqlite3.connect(self.db_path)
        self._create_table()

    # ---------- DB 初期化 ----------
    def _create_table(self):
        cur = self.conn.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            confidence REAL,
            interaction_count INTEGER,
            last_seen REAL,
            display_name TEXT,
            name_confidence REAL
        )
        """)
        self.conn.commit()

    # ---------- 新しい匿名ユーザを作る ----------
    def create_new_user(self) -> UserRecord:
        user_id = str(uuid.uuid4())
        now = time.time()

        user = UserRecord(user_id=user_id,
                          confidence=0.1,
                          interaction_count=1,
                          last_seen=now,
                          display_name=None,
                          name_confidence=0.0)

        cur = self.conn.cursor()
        cur.execute("""
        INSERT INTO users VALUES (?, ?, ?, ?, ?, ?)
        """, (user.user_id, user.confidence, user.interaction_count, user.last_seen, user.display_name,
              user.name_confidence))
        self.conn.commit()

        return user

    # ---------- user_id で取得 ----------
    def get_user(self, user_id: str) -> Optional[UserRecord]:
        cur = self.conn.cursor()
        cur.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        row = cur.fetchone()

        if row is None:
            return None

        return UserRecord(user_id=row[0],
                          confidence=row[1],
                          interaction_count=row[2],
                          last_seen=row[3],
                          display_name=row[4],
                          name_confidence=row[5])

    # ---------- 全ユーザ取得 ----------
    def get_all_users(self) -> List[UserRecord]:
        cur = self.conn.cursor()
        cur.execute('SELECT * FROM users')
        rows = cur.fetchall()

        users = []
        for r in rows:
            users.append(
                UserRecord(user_id=r[0],
                           confidence=r[1],
                           interaction_count=r[2],
                           last_seen=r[3],
                           display_name=r[4],
                           name_confidence=r[5]))
        return users

    # ---------- インタラクション更新 ----------
    def update_interaction(self, user_id: str):
        user = self.get_user(user_id)
        if user is None:
            return

        user.interaction_count += 1
        user.last_seen = time.time()
        user.confidence = min(1.0, user.confidence + 0.05)

        cur = self.conn.cursor()
        cur.execute(
            """
        UPDATE users
        SET interaction_count = ?, last_seen = ?, confidence = ?
        WHERE user_id = ?
        """, (user.interaction_count, user.last_seen, user.confidence, user.user_id))
        self.conn.commit()

    # ---------- 呼び名の候補を保存 ----------
    def set_display_name_candidate(self, user_id: str, name: str):
        user = self.get_user(user_id)
        if user is None:
            return

        user.display_name = name
        user.name_confidence = 0.4

        cur = self.conn.cursor()
        cur.execute(
            """
        UPDATE users
        SET display_name = ?, name_confidence = ?
        WHERE user_id = ?
        """, (user.display_name, user.name_confidence, user.user_id))
        self.conn.commit()

    # ---------- 呼び名を確定 ----------
    def confirm_display_name(self, user_id: str, name: str):
        user = self.get_user(user_id)
        if user is None:
            return

        user.display_name = name
        user.name_confidence = 0.8

        cur = self.conn.cursor()
        cur.execute(
            """
        UPDATE users
        SET display_name = ?, name_confidence = ?
        WHERE user_id = ?
        """, (user.display_name, user.name_confidence, user.user_id))
        self.conn.commit()

    # ---------- DB を閉じる ----------
    def close(self):
        self.conn.close()


# =========================
# 動作確認用
# =========================

if __name__ == '__main__':
    print('=== UserStore test ===')

    store = UserStore('users.db')

    # 新規ユーザ作成
    user = store.create_new_user()
    print('created user:')
    print(user)

    # インタラクションを増やす
    store.update_interaction(user.user_id)
    store.update_interaction(user.user_id)

    # 呼び名を仮登録
    store.set_display_name_candidate(user.user_id, 'テスト')
    print('\nafter name candidate:')
    print(store.get_user(user.user_id))

    # 呼び名を確定
    store.confirm_display_name(user.user_id, 'テスト')
    print('\nafter name confirm:')
    print(store.get_user(user.user_id))

    # 全ユーザ表示
    print('\nall users:')
    for u in store.get_all_users():
        print(u)

    store.close()
