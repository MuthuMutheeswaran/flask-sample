from flask import Flask, jsonify
import psycopg2
import os

app = Flask(__name__)

# ---------- DB CONFIG (Render Postgres) ----------
DB_CONFIG = {
    "dbname": "flask_sample_9uxk",
    "user": "flask_sample_9uxk_user",
    "password": "aoRB8MKQgETZo8gMyB1U39xjplrpycCu",
    "host": "dpg-d4gs8l95pdvs738r1h7g-a",  # need naa later .render.com potruvom
    "port": 5432,
}


def get_db_connection():
    """
    PostgreSQL connection return pannum.
    Normal cursor use pannrom (dict cursor illa).
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

    # Table: id + total_rooms (name illa 🔥)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS rooms (
            id SERIAL PRIMARY KEY,
            total_rooms INT NOT NULL
        );
        """
    )

    # Check already data irukka?
    cur.execute("SELECT COUNT(*) FROM rooms;")
    row = cur.fetchone()   # tuple: (count,)
    count = row[0]

    # Empty na 1 row insert pannuvom
    if count == 0:
        cur.execute(
            "INSERT INTO rooms (total_rooms) VALUES (%s);",
            (4,),   # 4 rooms da inge set pannirukken
        )

    conn.commit()
    cur.close()
    conn.close()


# App start aagumbodhe DB init
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

    # rows => list of tuples → JSON build pannrom
    data = []
    for r in rows:
        data.append(
            {
                "id": r[0],
                "total_rooms": r[1],
            }
        )

    return jsonify(data)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
