# app.py
from flask import Flask, jsonify
import psycopg2
import os
from psycopg2.extras import RealDictCursor

app = Flask(__name__)

# ---------- DB CONFIG (LOCAL POSTGRES) ----------
DB_CONFIG = {
    "dbname": "flask_sample_9uxk",      # namba create pannadhu
    "user": "flask_sample_9uxk_user",        # un postgres username (default: postgres)
    "password": "aoRB8MKQgETZo8gMyB1U39xjplrpycCu",  # unga password vechchiko
    "host": "dpg-d4gs8l95pdvs738r1h7g-a",
    "port": 5432,
}


def get_db_connection():
    """
    PostgreSQL connection return pannum.
    """
    conn = psycopg2.connect(
        dbname=DB_CONFIG["dbname"],
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"],
        host=DB_CONFIG["host"],
        port=DB_CONFIG["port"],
        cursor_factory=RealDictCursor,
    )
    return conn
def init_db():
    conn = get_db_connection()
    cur = conn.cursor()

    # Only id + total_rooms
    cur.execute("""
        CREATE TABLE IF NOT EXISTS rooms (
            id SERIAL PRIMARY KEY,
            total_rooms INT NOT NULL
        );
    """)

    # Insert sample only if empty
    cur.execute("SELECT COUNT(*) FROM rooms;")
    count = cur.fetchone()[0]

    if count == 0:
        cur.execute(
            "INSERT INTO rooms (total_rooms) VALUES (%s);",
            (4,)   # 🔥 un “4 rooms” inga
        )

    conn.commit()
    cur.close()
    conn.close()

# Run init
init_db()

@app.route("/")
def home():
    return "Flask + PostgreSQL running on Render ⚡"

# ---------- API ----------
@app.route("/api/rooms", methods=["GET"])
def get_rooms():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, total_rooms FROM rooms;")
    rows = cur.fetchall()
    cur.close()
    conn.close()

    data = []
    for r in rows:
        data.append({
            "id": r[0],
            "total_rooms": r[1]
        })

    return jsonify(data)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)