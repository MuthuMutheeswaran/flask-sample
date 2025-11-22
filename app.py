import os
import psycopg2
from flask import Flask, jsonify

app = Flask(__name__)

# Render environment variable
DATABASE_URL = os.environ.get("DATABASE_URL")

def get_conn():
    return psycopg2.connect(DATABASE_URL)

# ---------- DB INIT ----------
def init_db():
    conn = get_conn()
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
    conn = get_conn()
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
