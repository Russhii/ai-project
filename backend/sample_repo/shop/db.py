import sqlite3

_conn = sqlite3.connect(":memory:")
_conn.execute("CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY, total REAL, status TEXT)")


def save_order(total, status):
    cursor = _conn.cursor()
    cursor.execute("INSERT INTO orders (total, status) VALUES (?, ?)", (total, status))
    _conn.commit()
    return cursor.lastrowid


def find_order(order_id):
    cursor = _conn.cursor()
    cursor.execute("SELECT id, total, status FROM orders WHERE id = ?", (order_id,))
    return cursor.fetchone()
