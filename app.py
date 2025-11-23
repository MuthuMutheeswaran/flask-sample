from flask import Flask, jsonify
import psycopg2
import os

app = Flask(__name__)

# ---------- DB CONFIG (Render PostgreSQL) ----------
DB_CONFIG = {
    "dbname": "flask_sample_9uxk",
    "user": "flask_sample_9uxk_user",
    "password": "aoRB8MKQgETZo8gMyB1U39xjplrpycCu",
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
    )
    return conn


def init_db():
    conn = get_db_connection()
    cur = conn.cursor()

    # Only id + total_rooms (NO name column)
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
            (4,)   # starting rooms = 4
        )

    conn.commit()
    cur.close()
    conn.close()


# Run init once at startup
init_db()


@app.route("/")
def home():
    return "Flask + PostgreSQL running on Render ⚡"


# ---------- API 1: all rows ----------
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


# ---------- API 2: current room count ----------
@app.route("/api/room-count", methods=["GET"])
def get_room_count():
    conn = get_db_connection()
    cur = conn.cursor()
    # single row nu assume panrom – first record
    cur.execute("SELECT total_rooms FROM rooms ORDER BY id LIMIT 1;")
    row = cur.fetchone()
    cur.close()
    conn.close()

    if not row:
        return jsonify({"success": False, "message": "No room data found"}), 404

    return jsonify({
        "success": True,
        "total_rooms": row[0]
    })


# ---------- API 3: book room (decrement 1) ----------
@app.route("/api/book-room", methods=["GET"])
def book_room():
    conn = get_db_connection()
    cur = conn.cursor()

    # read current count
    cur.execute("SELECT id, total_rooms FROM rooms ORDER BY id LIMIT 1;")
    row = cur.fetchone()

    if not row:
        cur.close()
        conn.close()
        return jsonify({"success": False, "message": "No room data found"}), 404

    room_id = row[0]
    current = row[1]

    if current <= 0:
        cur.close()
        conn.close()
        return jsonify({"success": False, "message": "No rooms available"}), 400

    new_count = current - 1

    cur.execute("UPDATE rooms SET total_rooms = %s WHERE id = %s;", (new_count, room_id))
    conn.commit()
    cur.close()
    conn.close()

    return jsonify({
        "success": True,
        "message": "Room booked successfully",
        "total_rooms": new_count
    })

@app.route("/api/out-room", methods=["GET"])
def book_room():
    conn = get_db_connection()
    cur = conn.cursor()

    # read current count
    cur.execute("SELECT id, total_rooms FROM rooms ORDER BY id LIMIT 1;")
    row = cur.fetchone()

    if not row:
        cur.close()
        conn.close()
        return jsonify({"success": False, "message": "No room data found"}), 404

    room_id = row[0]
    current = row[1]

    if current >= 5:
        cur.close()
        conn.close()
        return jsonify({"success": False, "message": "No rooms available"}), 400

    new_count = current + 1

    cur.execute("UPDATE rooms SET total_rooms = %s WHERE id = %s;", (new_count, room_id))
    conn.commit()
    cur.close()
    conn.close()

    return jsonify({
        "success": True,
        "message": "Room booked successfully",
        "total_rooms": new_count
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
