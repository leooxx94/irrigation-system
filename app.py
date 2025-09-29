from flask import Flask, request, jsonify, render_template, redirect, url_for
import sqlite3, os
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

TZ_ROME = ZoneInfo("Europe/Rome")

APP_DB = os.path.join(os.path.dirname(__file__), "config.db")
app = Flask(__name__)

manual_relay_state = False

def init_db():
    with sqlite3.connect(APP_DB) as con:
        cur = con.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS schedules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            days TEXT NOT NULL DEFAULT '1,2,3,4,5,6,7'
        )
        """)
        
        cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY CHECK (id=1),
            enabled INTEGER NOT NULL DEFAULT 0,
            on_seconds INTEGER NOT NULL DEFAULT 10,
            off_seconds INTEGER NOT NULL DEFAULT 3600,
            window_start TEXT NOT NULL DEFAULT '00:00',
            window_end TEXT NOT NULL DEFAULT '23:59',
            updated_at TEXT NOT NULL
        )
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS heartbeats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            device TEXT,
            ip TEXT,
            relay_on INTEGER,
            enabled INTEGER
        )
        """)
        # inserisce riga singola se assente
        cur.execute("SELECT 1 FROM settings WHERE id=1")
        if cur.fetchone() is None:
            cur.execute("""
              INSERT INTO settings (id, enabled, on_seconds, off_seconds, window_start, window_end, updated_at)
              VALUES (1, 0, 10, 3600, '00:00', '23:59', ?)
            """, (datetime.utcnow().isoformat(),))
        con.commit()

def get_settings():
    with sqlite3.connect(APP_DB) as con:
        cur = con.cursor()
        cur.execute("SELECT enabled, on_seconds, off_seconds, window_start, window_end, updated_at FROM settings WHERE id=1")
        row = cur.fetchone()
        if not row:
            # crea riga di default se manca
            cur.execute("""INSERT INTO settings (id, enabled, on_seconds, off_seconds, window_start, window_end, updated_at)
                           VALUES (1, 0, 10, 3600, '00:00', '23:59', ?)""",
                        (datetime.utcnow().isoformat(),))
            con.commit()
            return {
                "enabled": False,
                "on_seconds": 10,
                "off_seconds": 3600,
                "window_start": "00:00",
                "window_end": "23:59",
                "updated_at": datetime.utcnow().isoformat()
            }
        return {
            "enabled": bool(row[0]),
            "on_seconds": int(row[1]),
            "off_seconds": int(row[2]),
            "window_start": row[3],
            "window_end": row[4],
            "updated_at": row[5]
        }

def save_settings(enabled, on_seconds, off_seconds, window_start, window_end):
    with sqlite3.connect(APP_DB) as con:
        cur = con.cursor()
        cur.execute("""
        UPDATE settings SET enabled=?, on_seconds=?, off_seconds=?, window_start=?, window_end=?, updated_at=?
        WHERE id=1
        """, (1 if enabled else 0, on_seconds, off_seconds, window_start, window_end, datetime.utcnow().isoformat()))
        con.commit()

@app.route("/toggle_relay", methods=["POST"])
def toggle_relay():
    global manual_relay_state
    data = request.get_json(force=True)
    manual_relay_state = bool(data.get("state", False))
    return jsonify({"ok": True, "state": manual_relay_state})

@app.route("/get_manual_relay", methods=["GET"])
def get_manual_relay():
    return jsonify({"state": manual_relay_state})


@app.route("/", methods=["GET"])
def index():
    s = get_settings()
    with sqlite3.connect(APP_DB) as con:
        cur = con.cursor()
        cur.execute("SELECT ts, device, ip FROM heartbeats ORDER BY ts DESC LIMIT 10")
        rows = cur.fetchall()

    heartbeats = []
    for ts, dev, ip in rows:
        try:
            dt_utc = datetime.fromisoformat(ts)
            # assicuro che sia marcato come UTC
            dt_utc = dt_utc.replace(tzinfo=ZoneInfo("UTC"))
            dt_local = dt_utc.astimezone(TZ_ROME)
            ts_fmt = dt_local.strftime("%d/%m %H:%M")  # es. 19/09 14:37
        except Exception:
            ts_fmt = ts  # fallback se formato non valido
        heartbeats.append((ts_fmt, dev, ip))

    with sqlite3.connect(APP_DB) as con:
        cur = con.cursor()
        cur.execute("SELECT id, start_time, end_time, days FROM schedules ORDER BY start_time")
        schedules = cur.fetchall()

    return render_template("index.html", s=s, schedules=schedules, heartbeats=heartbeats)


@app.route("/api/config", methods=["GET"])
def api_config():
    return jsonify(get_settings())

@app.route("/api/heartbeat", methods=["POST"])
def api_heartbeat():
    data = request.get_json(force=True, silent=True) or {}
    with sqlite3.connect(APP_DB) as con:
        cur = con.cursor()
        cur.execute("""
        INSERT INTO heartbeats (ts, device, ip, relay_on, enabled)
        VALUES (?, ?, ?, ?, ?)
        """, (
            datetime.utcnow().isoformat(),
            data.get("device"),
            data.get("ip"),
            1 if data.get("relay_on") else 0,
            1 if data.get("enabled") else 0
        ))
        
        # pulizia automatica: elimina i record più vecchi di 7 giorni
        cur.execute("""
            DELETE FROM heartbeats
            WHERE ts < datetime('now', '-7 days')
        """)

    return jsonify({"ok": True})

@app.route("/api/schedule", methods=["GET"])
def api_schedule():
    with sqlite3.connect(APP_DB) as con:
        cur = con.cursor()
        cur.execute("SELECT start_time, end_time, days FROM schedules ORDER BY start_time")
        rows = cur.fetchall()
    return jsonify([
        {
            "start": s,
            "end": e,
            "days": [int(d) for d in days.split(",")]
        }
        for (s, e, days) in rows
    ])

@app.route("/add_schedule", methods=["POST"])
def add_schedule():
    data = request.json
    start_time = data.get("start_time")
    end_time   = data.get("end_time")
    days = data.get("days", "1,2,3,4,5,6,7")  # default string

    # normalizza formato
    try:
        datetime.strptime(start_time, "%H:%M:%S")
        datetime.strptime(end_time, "%H:%M:%S")
    except ValueError:
        return "Formato orario non valido (usa HH:MM:SS)", 400

    if isinstance(days, list):
        days_str = ",".join(str(d) for d in days)
    else:
        days_str = str(days)

    with sqlite3.connect(APP_DB) as con:
        cur = con.cursor()
        cur.execute(
            "INSERT INTO schedules (start_time, end_time, days) VALUES (?, ?, ?)",
            (start_time, end_time, days_str)
        )
        con.commit()
    return redirect(url_for("index"))


@app.route("/delete_schedule/<int:sched_id>")
def delete_schedule(sched_id):
    with sqlite3.connect(APP_DB) as con:
        cur = con.cursor()
        cur.execute("DELETE FROM schedules WHERE id=?",(sched_id,))
        con.commit()
    return redirect(url_for("index"))

@app.route("/toggle", methods=["POST"])
def toggle():
    enabled = 1 if "enabled" in request.form else 0
    with sqlite3.connect(APP_DB) as con:
        cur = con.cursor()
        cur.execute("SELECT id FROM settings WHERE id=1")
        if cur.fetchone():
            cur.execute("UPDATE settings SET enabled=?, updated_at=? WHERE id=1",
                        (enabled, datetime.utcnow().isoformat()))
        else:
            cur.execute("INSERT INTO settings (id, enabled, updated_at) VALUES (1, ?, ?)",
                        (enabled, datetime.utcnow().isoformat()))
        con.commit()
    return redirect(url_for("index"))


if __name__ == "__main__":
    init_db()
    # DEV: app.run(host="0.0.0.0", port=5000, debug=True)
    # PROD (semplice): flask run con waitress
    from waitress import serve
    init_db()
    serve(app, host="0.0.0.0", port=5000)
