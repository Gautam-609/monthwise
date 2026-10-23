import math
import re
import sqlite3
from contextlib import closing
from datetime import date, datetime
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory


BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "monthwise.db"
CATEGORIES = {
    "Utilities",
    "Housing",
    "Subscriptions",
    "Insurance",
    "Transport",
    "Health",
    "Other",
}

app = Flask(__name__)


def connect_db():
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_db():
    with closing(connect_db()) as connection, connection:
        table_exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'bills'"
        ).fetchone()
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS bills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL CHECK(length(trim(name)) BETWEEN 1 AND 70),
                amount REAL NOT NULL CHECK(amount > 0),
                due_date TEXT NOT NULL,
                category TEXT NOT NULL,
                paid INTEGER NOT NULL DEFAULT 0 CHECK(paid IN (0, 1))
            )
            """
        )
        if not table_exists:
            current_month = date.today().replace(day=1)
            examples = [
                ("Home rent", 18000, 3, "Housing", 1),
                ("Electricity", 1480, 8, "Utilities", 1),
                ("Internet", 999, 12, "Utilities", 0),
                ("Music subscription", 149, 18, "Subscriptions", 0),
                ("Health insurance", 2200, 25, "Insurance", 0),
            ]
            connection.executemany(
                """
                INSERT INTO bills (name, amount, due_date, category, paid)
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        name,
                        amount,
                        current_month.replace(day=day).isoformat(),
                        category,
                        paid,
                    )
                    for name, amount, day, category, paid in examples
                ],
            )


def bill_to_dict(row):
    return {
        "id": row["id"],
        "name": row["name"],
        "amount": row["amount"],
        "due": row["due_date"],
        "category": row["category"],
        "paid": bool(row["paid"]),
    }


def valid_due_date(value):
    if not isinstance(value, str):
        return False
    try:
        return date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


@app.get("/")
def index():
    return send_from_directory(BASE_DIR, "index.html")


@app.get("/api/bills")
def list_bills():
    month = request.args.get("month", "")
    if not re.fullmatch(r"\d{4}-\d{2}", month):
        return jsonify(error="Month must use YYYY-MM format."), 400
    try:
        datetime.strptime(month, "%Y-%m")
    except ValueError:
        return jsonify(error="Choose a valid month."), 400

    with closing(connect_db()) as connection, connection:
        rows = connection.execute(
            """
            SELECT id, name, amount, due_date, category, paid
            FROM bills
            WHERE substr(due_date, 1, 7) = ?
            ORDER BY due_date, name
            """,
            (month,),
        ).fetchall()
    return jsonify([bill_to_dict(row) for row in rows])


@app.post("/api/bills")
def create_bill():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error="Send bill details as JSON."), 400

    name = data.get("name")
    amount = data.get("amount")
    due = data.get("due")
    category = data.get("category")
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 70:
        return jsonify(error="Bill name must be between 1 and 70 characters."), 400
    if (
        isinstance(amount, bool)
        or not isinstance(amount, (int, float))
        or not math.isfinite(amount)
        or amount <= 0
    ):
        return jsonify(error="Amount must be a number greater than zero."), 400
    if not valid_due_date(due):
        return jsonify(error="Due date must be a valid YYYY-MM-DD date."), 400
    if not isinstance(category, str) or category not in CATEGORIES:
        return jsonify(error="Choose a valid bill category."), 400

    with closing(connect_db()) as connection, connection:
        cursor = connection.execute(
            """
            INSERT INTO bills (name, amount, due_date, category)
            VALUES (?, ?, ?, ?)
            """,
            (name.strip(), amount, due, category),
        )
        row = connection.execute(
            """
            SELECT id, name, amount, due_date, category, paid
            FROM bills WHERE id = ?
            """,
            (cursor.lastrowid,),
        ).fetchone()
    return jsonify(bill_to_dict(row)), 201


@app.patch("/api/bills/<int:bill_id>")
def update_bill(bill_id):
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get("paid"), bool):
        return jsonify(error="Paid status must be true or false."), 400

    with closing(connect_db()) as connection, connection:
        cursor = connection.execute(
            "UPDATE bills SET paid = ? WHERE id = ?",
            (int(data["paid"]), bill_id),
        )
        if cursor.rowcount == 0:
            return jsonify(error="Bill not found."), 404
        row = connection.execute(
            """
            SELECT id, name, amount, due_date, category, paid
            FROM bills WHERE id = ?
            """,
            (bill_id,),
        ).fetchone()
    return jsonify(bill_to_dict(row))


@app.delete("/api/bills/<int:bill_id>")
def delete_bill(bill_id):
    with closing(connect_db()) as connection, connection:
        cursor = connection.execute("DELETE FROM bills WHERE id = ?", (bill_id,))
    if cursor.rowcount == 0:
        return jsonify(error="Bill not found."), 404
    return jsonify(message="Bill deleted.")


initialize_db()


if __name__ == "__main__":
    app.run()
