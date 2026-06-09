import sqlite3
import os
from datetime import datetime

DB_PATH = "portal.db"

def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cur = conn.cursor()

    # 매입처 테이블
    cur.execute("""
        CREATE TABLE IF NOT EXISTS vendors (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            biz_number  TEXT UNIQUE NOT NULL,   -- 사업자번호
            name        TEXT NOT NULL,           -- 상호명
            category    TEXT,                    -- 분류 (예: IT장비, 소모품 등)
            account_code TEXT,                   -- 계정과목
            memo        TEXT,
            is_active   INTEGER DEFAULT 1,
            created_at  TEXT DEFAULT (datetime('now','localtime')),
            updated_at  TEXT DEFAULT (datetime('now','localtime'))
        )
    """)

    # 세금계산서 처리 이력 테이블
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tax_invoices (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            mail_subject    TEXT,                -- 메일 제목
            mail_date       TEXT,                -- 메일 수신일
            issue_date      TEXT,                -- 발행일
            supplier_name   TEXT,                -- 공급자명
            supplier_biz_no TEXT,                -- 공급자 사업자번호
            supply_amount   INTEGER,             -- 공급가액
            tax_amount      INTEGER,             -- 세액
            total_amount    INTEGER,             -- 합계금액
            item_name       TEXT,                -- 품목
            status          TEXT DEFAULT 'PENDING',  -- PENDING/MATCHED/SUBMITTED/SKIPPED/ERROR
            result_memo     TEXT,                -- 처리 결과 메모
            bizmeka_doc_no  TEXT,                -- 비즈메카 결의서 번호
            created_at      TEXT DEFAULT (datetime('now','localtime'))
        )
    """)

    # 설정 테이블
    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key     TEXT PRIMARY KEY,
            value   TEXT,
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        )
    """)

    # 기본 설정값 삽입
    defaults = [
        ("groupware_url", "https://ngwx.ktbizoffice.com"),
        ("groupware_id", ""),
        ("bizmeka_url", "https://www.bizmeka.com"),
        ("bizmeka_id", ""),
        ("schedule_interval_min", "60"),
        ("openai_api_key", ""),
        ("mail_keyword", "세금계산서"),
        ("auto_submit", "false"),
    ]
    for key, value in defaults:
        cur.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
            (key, value)
        )

    conn.commit()
    conn.close()

def get_setting(key):
    conn = get_connection()
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else None

def set_setting(key, value):
    conn = get_connection()
    conn.execute("""
        INSERT INTO settings (key, value, updated_at)
        VALUES (?, ?, datetime('now','localtime'))
        ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
    """, (key, value))
    conn.commit()
    conn.close()

def get_all_settings():
    conn = get_connection()
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    conn.close()
    return {r["key"]: r["value"] for r in rows}

# --- 매입처 CRUD ---
def get_vendors(active_only=True):
    conn = get_connection()
    query = "SELECT * FROM vendors"
    if active_only:
        query += " WHERE is_active=1"
    query += " ORDER BY name"
    rows = conn.execute(query).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def add_vendor(biz_number, name, category, account_code, memo):
    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO vendors (biz_number, name, category, account_code, memo)
            VALUES (?, ?, ?, ?, ?)
        """, (biz_number, name, category, account_code, memo))
        conn.commit()
        return True, "등록 완료"
    except sqlite3.IntegrityError:
        return False, "이미 등록된 사업자번호입니다."
    finally:
        conn.close()

def update_vendor(vendor_id, name, category, account_code, memo, is_active):
    conn = get_connection()
    conn.execute("""
        UPDATE vendors SET name=?, category=?, account_code=?, memo=?,
        is_active=?, updated_at=datetime('now','localtime')
        WHERE id=?
    """, (name, category, account_code, memo, 1 if is_active else 0, vendor_id))
    conn.commit()
    conn.close()

def delete_vendor(vendor_id):
    conn = get_connection()
    conn.execute("UPDATE vendors SET is_active=0 WHERE id=?", (vendor_id,))
    conn.commit()
    conn.close()

def find_vendor_by_biz_no(biz_no):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM vendors WHERE biz_number=? AND is_active=1", (biz_no,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None

# --- 세금계산서 이력 CRUD ---
def get_invoices(status=None, limit=100):
    conn = get_connection()
    if status:
        rows = conn.execute(
            "SELECT * FROM tax_invoices WHERE status=? ORDER BY created_at DESC LIMIT ?",
            (status, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM tax_invoices ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_invoice_stats():
    conn = get_connection()
    stats = {}
    for status in ["PENDING", "MATCHED", "SUBMITTED", "SKIPPED", "ERROR"]:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM tax_invoices WHERE status=?", (status,)
        ).fetchone()
        stats[status] = row["cnt"]
    total = conn.execute("SELECT COUNT(*) as cnt FROM tax_invoices").fetchone()
    stats["TOTAL"] = total["cnt"]
    conn.close()
    return stats

def add_invoice(data: dict):
    conn = get_connection()
    conn.execute("""
        INSERT INTO tax_invoices
        (mail_subject, mail_date, issue_date, supplier_name, supplier_biz_no,
         supply_amount, tax_amount, total_amount, item_name, status, result_memo)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data.get("mail_subject"), data.get("mail_date"), data.get("issue_date"),
        data.get("supplier_name"), data.get("supplier_biz_no"),
        data.get("supply_amount"), data.get("tax_amount"), data.get("total_amount"),
        data.get("item_name"), data.get("status", "PENDING"), data.get("result_memo")
    ))
    conn.commit()
    conn.close()

def update_invoice_status(invoice_id, status, memo=None, doc_no=None):
    conn = get_connection()
    conn.execute("""
        UPDATE tax_invoices SET status=?, result_memo=?, bizmeka_doc_no=?
        WHERE id=?
    """, (status, memo, doc_no, invoice_id))
    conn.commit()
    conn.close()
    """회사명 키워드로 매입처 검색"""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM vendors WHERE name LIKE ? AND is_active=1",
        (f"%{name_keyword}%",)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM vendors WHERE is_active = 1')
    vendors = cursor.fetchall()
    conn.close()
    for v in vendors:
        if vendor_name in search_name or search_name in vendor_name:
            return dict(v)
    return None

def find_vendor_by_name(name):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM vendors WHERE is_active = 1")
    vendors = cursor.fetchall()
    conn.close()
    for v in vendors:
        vname = v["name"].replace(u"(주)", "").replace(u"주식회사", "").strip()
        sname = name.replace(u"(주)", "").replace(u"주식회사", "").strip()
        if vname in sname or sname in vname:
            return dict(v)
    return None
