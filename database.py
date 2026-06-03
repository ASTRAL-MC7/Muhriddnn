import sqlite3
import os
from datetime import datetime

DB_PATH = os.getenv("DB_PATH", "bot.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            first_name TEXT,
            username TEXT,
            referred_by INTEGER,
            is_verified INTEGER DEFAULT 0,
            prize_sent INTEGER DEFAULT 0,
            prize_link_sent INTEGER DEFAULT 0,
            joined_at TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id INTEGER,
            referee_id INTEGER,
            created_at TEXT,
            UNIQUE(referrer_id, referee_id)
        )
    """)
    conn.commit()
    conn.close()


def add_user(user_id, first_name, username, referred_by=None):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        INSERT OR IGNORE INTO users (user_id, first_name, username, referred_by, joined_at)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, first_name, username, referred_by, datetime.now().isoformat()))
    # If user already existed with no referrer, set it now (handles returning users clicking a reflink)
    if referred_by:
        c.execute("""
            UPDATE users SET referred_by = ?
            WHERE user_id = ? AND referred_by IS NULL
        """, (referred_by, user_id))
    conn.commit()
    conn.close()


def get_user(user_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None


def verify_user(user_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE users SET is_verified = 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def referral_exists(referrer_id, referee_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "SELECT 1 FROM referrals WHERE referrer_id = ? AND referee_id = ?",
        (referrer_id, referee_id)
    )
    exists = c.fetchone() is not None
    conn.close()
    return exists


def add_referral(referrer_id, referee_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        INSERT OR IGNORE INTO referrals (referrer_id, referee_id, created_at)
        VALUES (?, ?, ?)
    """, (referrer_id, referee_id, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def get_ref_count(user_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (user_id,))
    count = c.fetchone()[0]
    conn.close()
    return count


def mark_prize_notified(user_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE users SET prize_sent = 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def mark_prize_link_sent(user_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE users SET prize_link_sent = 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def get_user_count():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    count = c.fetchone()[0]
    conn.close()
    return count


def get_all_user_ids():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT user_id FROM users")
    users = [row[0] for row in c.fetchall()]
    conn.close()
    return users


def add_fake_refs(user_id, count):
    conn = get_conn()
    c = conn.cursor()
    for i in range(count):
        fake_id = -(abs(user_id) * 10000 + i)
        c.execute("""
            INSERT OR IGNORE INTO referrals (referrer_id, referee_id, created_at)
            VALUES (?, ?, ?)
        """, (user_id, fake_id, datetime.now().isoformat()))
    conn.commit()
    conn.close()


init_db()
