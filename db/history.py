import sqlite3
import json
import os
from datetime import datetime

_DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'history.db')


def init_db():
    con = sqlite3.connect(_DB_PATH)
    con.execute("""
        CREATE TABLE IF NOT EXISTS history (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            filename    TEXT NOT NULL,
            uploaded_at DATETIME NOT NULL,
            status      TEXT NOT NULL,
            result_json TEXT,
            error_msg   TEXT
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS feedback (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            history_id INTEGER NOT NULL,
            field_name TEXT NOT NULL,
            is_correct INTEGER NOT NULL,
            correction TEXT,
            created_at DATETIME NOT NULL,
            FOREIGN KEY (history_id) REFERENCES history(id)
        )
    """)
    con.commit()
    con.close()


def save_history(filename: str, status: str, result_json: dict = None, error_msg: str = None) -> int:
    con = sqlite3.connect(_DB_PATH)
    cur = con.execute(
        "INSERT INTO history (filename, uploaded_at, status, result_json, error_msg) VALUES (?,?,?,?,?)",
        (filename, datetime.now().isoformat(), status,
         json.dumps(result_json, ensure_ascii=False) if result_json else None,
         error_msg)
    )
    row_id = cur.lastrowid
    con.commit()
    con.close()
    return row_id


def check_duplicate(filename: str) -> bool:
    con = sqlite3.connect(_DB_PATH)
    row = con.execute(
        "SELECT id FROM history WHERE filename=? AND status='success' LIMIT 1",
        (filename,)
    ).fetchone()
    con.close()
    return row is not None


def get_history() -> list:
    con = sqlite3.connect(_DB_PATH)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT id, filename, uploaded_at, status, result_json, error_msg FROM history ORDER BY uploaded_at DESC"
    ).fetchall()
    con.close()
    return [dict(r) for r in rows]


def get_history_record(record_id: int) -> dict:
    con = sqlite3.connect(_DB_PATH)
    con.row_factory = sqlite3.Row
    row = con.execute("SELECT * FROM history WHERE id=?", (record_id,)).fetchone()
    con.close()
    return dict(row) if row else {}


def save_feedback(history_id: int, field_name: str, is_correct: bool, correction: str = ''):
    con = sqlite3.connect(_DB_PATH)
    con.execute(
        "INSERT INTO feedback (history_id, field_name, is_correct, correction, created_at) VALUES (?,?,?,?,?)",
        (history_id, field_name, 1 if is_correct else 0, correction, datetime.now().isoformat())
    )
    con.commit()
    con.close()


def get_stats() -> dict:
    con = sqlite3.connect(_DB_PATH)
    total = con.execute("SELECT COUNT(*) FROM history").fetchone()[0]
    success = con.execute("SELECT COUNT(*) FROM history WHERE status='success'").fetchone()[0]
    error = con.execute("SELECT COUNT(*) FROM history WHERE status='error'").fetchone()[0]
    partial = con.execute("SELECT COUNT(*) FROM history WHERE status='partial'").fetchone()[0]

    monthly = con.execute("""
        SELECT strftime('%Y-%m', uploaded_at) as month, COUNT(*) as cnt
        FROM history
        GROUP BY month
        ORDER BY month DESC
        LIMIT 12
    """).fetchall()

    feedback_stats = con.execute("""
        SELECT field_name,
               SUM(is_correct) as correct,
               COUNT(*) - SUM(is_correct) as incorrect
        FROM feedback
        GROUP BY field_name
    """).fetchall()

    con.close()
    return {
        'total': total,
        'success': success,
        'error': error,
        'partial': partial,
        'monthly': [{'month': r[0], 'count': r[1]} for r in monthly],
        'feedback': [{'field': r[0], 'correct': r[1], 'incorrect': r[2]} for r in feedback_stats],
    }


def export_history_csv() -> str:
    import csv
    import io
    rows = get_history()
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=['id', 'filename', 'uploaded_at', 'status', 'error_msg'])
    writer.writeheader()
    for r in rows:
        writer.writerow({k: r.get(k, '') for k in writer.fieldnames})
    return buf.getvalue()
