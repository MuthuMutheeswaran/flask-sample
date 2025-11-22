# app.py
from flask import Flask, jsonify
import psycopg2
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


@app.route("/api/room-count", methods=["GET"])
def room_count():
    """
    hotel_config table la irukkura number_of_rooms column value read pannum.
    Example: 4 -> JSON la return.
    """
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # table la first row la irukkura number_of_rooms
        cur.execute("SELECT number_of_rooms FROM hotel_config LIMIT 1;")
        row = cur.fetchone()

        cur.close()
        conn.close()

        if not row:
            # table empty na
            return jsonify({
                "success": False,
                "message": "No row found in hotel_config table"
            }), 404

        # row['number_of_rooms'] la 4 irukkum
        return jsonify({
            "success": True,
            "total_rooms": row["number_of_rooms"]
        })

    except Exception as e:
        # error aana case
        return jsonify({
            "success": False,
            "message": "Server error",
            "error": str(e)
        }), 500


if __name__ == "__main__":
    # local la run panna:
    # python app.py
    app.run(host="0.0.0.0", port=5000, debug=True)
