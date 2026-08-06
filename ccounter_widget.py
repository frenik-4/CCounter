#!/usr/bin/env python3
"""
CCounter skrivbordswidget — passager, FPS, stream-status och senaste skyltar.
Körs fristående: python3 /home/lucky9/CCounter/ccounter_widget.py
"""

import json
import os
import sqlite3
from datetime import date, datetime, timedelta

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, Gdk

DB_PATH       = "/home/lucky9/CCounter/data/ccounter.db"
STATUS_PATH   = "/home/lucky9/CCounter/data/status.json"
POS_PATH      = os.path.expanduser("~/.config/ccounter_widget_pos.json")
REFRESH_SECONDS      = 10
STATUS_STALE_SECONDS = 90

BG       = "#0f172a"
FG_HEAD  = "#f1f5f9"
FG_VALUE = "#ffffff"
FG_LABEL = "#94a3b8"
FG_PLATE = "#38bdf8"
FG_TIME  = "#94a3b8"
GREEN    = "#22c55e"
RED      = "#ef4444"
YELLOW   = "#eab308"


def query_db():
    try:
        con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        today = date.today().isoformat()

        cur.execute("""
            SELECT COUNT(*) AS cnt FROM events
            WHERE date(timestamp) = ?
              AND event_type = 'road_passage'
              AND (final_category IS NULL OR final_category = 'road_traffic')
        """, (today,))
        count = cur.fetchone()["cnt"]

        cur.execute("""
            SELECT COUNT(*) AS cnt FROM events
            WHERE date(timestamp) = ?
              AND event_type = 'road_passage'
              AND (final_category IS NULL OR final_category = 'road_traffic')
              AND plate_text IS NOT NULL AND plate_text != ''
        """, (today,))
        plates_read = cur.fetchone()["cnt"]

        cur.execute("""
            SELECT COUNT(*) AS cnt FROM events
            WHERE plate_detected = 0
              AND anpr_attempted = 0
              AND snapshot_path IS NOT NULL AND snapshot_path != ''
        """)
        anpr_queue = cur.fetchone()["cnt"]

        # Uptime idag: andel av 06:00–22:00 som strömmen varit uppe
        window_start = f"{today}T06:00:00"
        window_end   = f"{today}T22:00:00"
        cur.execute("""
            SELECT timestamp, status FROM stream_events
            WHERE timestamp >= ? AND timestamp <= ?
            ORDER BY timestamp
        """, (window_start, window_end))
        events = cur.fetchall()
        uptime_pct = _calc_uptime(events, window_start, window_end)

        cur.execute("""
            SELECT plate_text, MAX(timestamp) AS seen_at
            FROM events
            WHERE plate_text IS NOT NULL AND plate_text != ''
            GROUP BY plate_text
            ORDER BY seen_at DESC
            LIMIT 5
        """)
        plates = cur.fetchall()
        con.close()
        return count, plates_read, anpr_queue, uptime_pct, plates
    except Exception:
        return None, None, None, None, []


def _calc_uptime(events, window_start, window_end):
    """Beräknar uptime-procent för ett tidsfönster baserat på stream_events."""
    def to_ts(s):
        return datetime.fromisoformat(s)

    ws = to_ts(window_start)
    we = to_ts(window_end)
    total = (we - ws).total_seconds()
    if total <= 0:
        return None

    # Anta att strömmen var uppe innan första event om det första är "down"
    up_seconds = 0.0
    current_up_since = ws

    for row in events:
        t = to_ts(row["timestamp"])
        t = max(ws, min(we, t))
        if row["status"] == "down":
            if current_up_since is not None:
                up_seconds += (t - current_up_since).total_seconds()
                current_up_since = None
        elif row["status"] == "up":
            if current_up_since is None:
                current_up_since = t

    if current_up_since is not None:
        up_seconds += (we - current_up_since).total_seconds()

    return round(100 * up_seconds / total, 1)


def read_status():
    """Läser status.json skriven av app.py. Returnerar (fps, stream_ok)."""
    try:
        with open(STATUS_PATH) as f:
            data = json.load(f)
        updated = datetime.fromisoformat(data["updated_at"])
        age = (datetime.now() - updated).total_seconds()
        if age > STATUS_STALE_SECONDS:
            return None, False
        return data.get("fps"), data.get("stream") == "up"
    except Exception:
        return None, False


class Widget(Gtk.Window):
    def __init__(self):
        super().__init__()
        self.set_title("CCounter")
        self.set_decorated(False)
        self.set_keep_above(True)
        self.set_resizable(False)
        self.set_default_size(230, 10)
        self.stick()

        self.connect("button-press-event", self._on_press)
        self.connect("configure-event", self._on_configure)

        # Återställ sparad position
        try:
            with open(POS_PATH) as f:
                pos = json.load(f)
            self.move(pos["x"], pos["y"])
        except Exception:
            self.move(40, 40)

        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            self.set_visual(visual)
        self.set_app_paintable(True)
        self.connect("draw", self._draw_bg)

        css = f"""
        window {{
            background-color: {BG};
            border-radius: 10px;
            border: 1px solid #1e293b;
        }}
        label.head {{
            color: {FG_HEAD};
            font-size: 10px;
            font-weight: bold;
            letter-spacing: 1px;
        }}
        label.count {{
            color: {FG_VALUE};
            font-size: 40px;
            font-weight: bold;
        }}
        label.sublabel {{
            color: {FG_LABEL};
            font-size: 10px;
        }}
        label.uptime {{
            color: {FG_LABEL};
            font-size: 11px;
        }}
        label.fps {{
            color: {FG_LABEL};
            font-size: 11px;
        }}
        label.plate {{
            color: {FG_PLATE};
            font-size: 14px;
            font-weight: bold;
            font-family: monospace;
        }}
        label.time {{
            color: {FG_TIME};
            font-size: 10px;
        }}
        label.status-ok {{
            color: {GREEN};
            font-size: 11px;
            font-weight: bold;
        }}
        label.status-err {{
            color: {RED};
            font-size: 11px;
            font-weight: bold;
        }}
        separator {{
            background-color: #1e293b;
            min-height: 1px;
        }}
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css.encode())
        Gtk.StyleContext.add_provider_for_screen(
            screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        box.set_margin_top(14)
        box.set_margin_bottom(14)
        box.set_margin_start(16)
        box.set_margin_end(16)
        self.add(box)

        # --- Rubrikrad med status-prick ---
        hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        lbl_head = Gtk.Label(label="CCOUNTER")
        lbl_head.get_style_context().add_class("head")
        lbl_head.set_halign(Gtk.Align.START)
        lbl_head.set_hexpand(True)
        self.lbl_status = Gtk.Label(label="● LIVE")
        self.lbl_status.get_style_context().add_class("status-ok")
        hdr.pack_start(lbl_head, True, True, 0)
        hdr.pack_end(self.lbl_status, False, False, 0)
        box.pack_start(hdr, False, False, 0)

        # --- Räknare ---
        self.lbl_count = Gtk.Label(label="—")
        self.lbl_count.get_style_context().add_class("count")
        self.lbl_count.set_halign(Gtk.Align.START)
        box.pack_start(self.lbl_count, False, False, 0)

        lbl_sub = Gtk.Label(label="passager idag")
        lbl_sub.get_style_context().add_class("sublabel")
        lbl_sub.set_halign(Gtk.Align.START)
        box.pack_start(lbl_sub, False, False, 2)

        # --- Skyltar idag + ANPR-kö ---
        plates_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self.lbl_plates_read = Gtk.Label(label="Skyltar: —")
        self.lbl_plates_read.get_style_context().add_class("fps")
        self.lbl_plates_read.set_halign(Gtk.Align.START)
        self.lbl_plates_read.set_hexpand(True)
        self.lbl_queue = Gtk.Label(label="Kö: —")
        self.lbl_queue.get_style_context().add_class("uptime")
        self.lbl_queue.set_halign(Gtk.Align.END)
        plates_row.pack_start(self.lbl_plates_read, True, True, 0)
        plates_row.pack_end(self.lbl_queue, False, False, 0)
        box.pack_start(plates_row, False, False, 2)

        # --- FPS + Uptime rad ---
        meta = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self.lbl_fps = Gtk.Label(label="FPS: —")
        self.lbl_fps.get_style_context().add_class("fps")
        self.lbl_fps.set_halign(Gtk.Align.START)
        self.lbl_fps.set_hexpand(True)
        self.lbl_uptime = Gtk.Label(label="Uptime: —")
        self.lbl_uptime.get_style_context().add_class("uptime")
        self.lbl_uptime.set_halign(Gtk.Align.END)
        meta.pack_start(self.lbl_fps, True, True, 0)
        meta.pack_end(self.lbl_uptime, False, False, 0)
        box.pack_start(meta, False, False, 4)

        # --- Separator ---
        sep = Gtk.Separator()
        box.pack_start(sep, False, False, 10)

        # --- Skyltar ---
        lbl_plates_head = Gtk.Label(label="SENASTE SKYLTAR")
        lbl_plates_head.get_style_context().add_class("head")
        lbl_plates_head.set_halign(Gtk.Align.START)
        box.pack_start(lbl_plates_head, False, False, 0)

        self.plate_rows = []
        for _ in range(5):
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
            lbl_p = Gtk.Label(label="")
            lbl_p.get_style_context().add_class("plate")
            lbl_p.set_halign(Gtk.Align.START)
            lbl_p.set_hexpand(True)
            lbl_t = Gtk.Label(label="")
            lbl_t.get_style_context().add_class("time")
            lbl_t.set_halign(Gtk.Align.END)
            row.pack_start(lbl_p, True, True, 0)
            row.pack_end(lbl_t, False, False, 0)
            box.pack_start(row, False, False, 3)
            self.plate_rows.append((lbl_p, lbl_t))

        self.connect("destroy", Gtk.main_quit)
        self.show_all()
        self.refresh()
        GLib.timeout_add_seconds(REFRESH_SECONDS, self.refresh)

    def _draw_bg(self, widget, ctx):
        ctx.set_source_rgba(0, 0, 0, 0)
        ctx.set_operator(1)
        ctx.paint()

    def _on_press(self, widget, event):
        if event.button == 1:
            self.begin_move_drag(event.button, int(event.x_root), int(event.y_root), event.time)

    def _on_configure(self, widget, event):
        try:
            os.makedirs(os.path.dirname(POS_PATH), exist_ok=True)
            with open(POS_PATH, "w") as f:
                json.dump({"x": event.x, "y": event.y}, f)
        except Exception:
            pass

    def refresh(self):
        count, plates_read, anpr_queue, uptime_pct, plates = query_db()
        fps, stream_ok = read_status()

        # Räknare
        self.lbl_count.set_text(str(count) if count is not None else "?")

        # Skyltar idag + kö
        if count is not None and plates_read is not None:
            self.lbl_plates_read.set_text(f"Skyltar: {plates_read}/{count}")
        else:
            self.lbl_plates_read.set_text("Skyltar: —")
        self.lbl_queue.set_text(f"Kö: {anpr_queue}" if anpr_queue is not None else "Kö: —")

        # Status
        sc = self.lbl_status.get_style_context()
        if stream_ok:
            sc.remove_class("status-err")
            sc.add_class("status-ok")
            self.lbl_status.set_text("● LIVE")
        else:
            sc.remove_class("status-ok")
            sc.add_class("status-err")
            self.lbl_status.set_text("● STOPP")

        # FPS
        self.lbl_fps.set_text(f"FPS: {fps:.0f}" if fps is not None else "FPS: —")

        # Uptime
        if uptime_pct is not None:
            self.lbl_uptime.set_text(f"Uptime: {uptime_pct:.0f}%")
        else:
            self.lbl_uptime.set_text("Uptime: —")

        # Skyltar
        for i, (lbl_p, lbl_t) in enumerate(self.plate_rows):
            if i < len(plates):
                row = plates[i]
                lbl_p.set_text(row["plate_text"])
                ts = row["seen_at"] or ""
                lbl_t.set_text(ts[11:16] if len(ts) >= 16 else ts)
            else:
                lbl_p.set_text("")
                lbl_t.set_text("")

        return True


if __name__ == "__main__":
    Widget()
    Gtk.main()
