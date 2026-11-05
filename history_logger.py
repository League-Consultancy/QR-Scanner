import os
import json
import time
from datetime import datetime, timedelta

LOGS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")

def ensure_logs_dir():
    if not os.path.exists(LOGS_DIR):
        os.makedirs(LOGS_DIR, exist_ok=True)

def get_log_filepath(date_str=None):
    """Returns absolute path to logs/history_YYYY-MM-DD.jsonl"""
    ensure_logs_dir()
    if not date_str:
        date_str = time.strftime("%Y-%m-%d")
    return os.path.join(LOGS_DIR, f"history_{date_str}.jsonl")

def log_event(event_type, code, timestamp_ts=None):
    """
    Appends an ENTER or LEAVE event to today's daily log file.
    event_type: 'ENTER' or 'LEAVE'
    """
    try:
        ensure_logs_dir()
        if timestamp_ts is None:
            timestamp_ts = time.time()
        
        time_struct = time.localtime(timestamp_ts)
        date_str = time.strftime("%Y-%m-%d", time_struct)
        time_str = time.strftime("%H:%M:%S", time_struct)
        iso_str = time.strftime("%Y-%m-%d %H:%M:%S", time_struct)

        record = {
            "time": time_str,
            "datetime": iso_str,
            "ts": round(timestamp_ts, 2),
            "code": str(code).strip(),
            "event": event_type
        }

        filepath = os.path.join(LOGS_DIR, f"history_{date_str}.jsonl")
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except Exception as e:
        print(f"[HistoryLogger] Error writing event {event_type} for {code}: {e}")

def undo_leave_event(code):
    """
    If a code reappeared within 5 seconds of leaving (glitch filter),
    removes the most recent premature LEAVE record from today's JSONL file
    so the session continues uninterrupted.
    """
    try:
        ensure_logs_dir()
        date_str = time.strftime("%Y-%m-%d")
        filepath = os.path.join(LOGS_DIR, f"history_{date_str}.jsonl")
        if not os.path.exists(filepath):
            return

        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()

        target_code = str(code).strip().lower()
        # Find and remove the last LEAVE event for this code
        remove_idx = -1
        for i in range(len(lines) - 1, -1, -1):
            try:
                rec = json.loads(lines[i].strip())
                if rec.get("code", "").strip().lower() == target_code and rec.get("event") == "LEAVE":
                    remove_idx = i
                    break
            except Exception:
                continue

        if remove_idx != -1:
            lines.pop(remove_idx)
            with open(filepath, "w", encoding="utf-8") as f:
                f.writelines(lines)
            print(f"[HistoryLogger] Undid premature LEAVE event for {code} (5s debounce filter)")
    except Exception as e:
        print(f"[HistoryLogger] Error undoing LEAVE event for {code}: {e}")

def parse_duration(seconds):
    if seconds is None:
        return "--"
    sec = int(round(seconds))
    if sec < 60:
        return f"{sec}s"
    minutes = sec // 60
    rem_sec = sec % 60
    if minutes < 60:
        return f"{minutes}m {rem_sec:02d}s"
    hours = minutes // 60
    rem_min = minutes % 60
    return f"{hours}h {rem_min:02d}m"

def query_history(start_date_str, end_date_str, specific_code=None, max_days=62):
    """
    Reads daily log files between start_date and end_date (inclusive),
    pairs ENTER and LEAVE events into coherent sessions,
    and returns a sorted list of session objects.
    """
    ensure_logs_dir()
    try:
        start_dt = datetime.strptime(start_date_str, "%Y-%m-%d").date()
        end_dt = datetime.strptime(end_date_str, "%Y-%m-%d").date()
    except Exception as e:
        return {"error": f"Invalid date format (must be YYYY-MM-DD): {e}", "sessions": []}

    if start_dt > end_dt:
        start_dt, end_dt = end_dt, start_dt

    days_diff = (end_dt - start_dt).days + 1
    if days_diff > max_days:
        return {
            "error": f"Date range ({days_diff} days) exceeds maximum allowed limit of {max_days} days (approx. 2 months).",
            "sessions": []
        }

    target_code = specific_code.strip().lower() if specific_code and specific_code.strip() else None

    sessions = []
    current_dt = start_dt

    while current_dt <= end_dt:
        date_key = current_dt.strftime("%Y-%m-%d")
        filepath = os.path.join(LOGS_DIR, f"history_{date_key}.jsonl")

        if os.path.exists(filepath):
            # Parse day events
            open_sessions = {} # code -> { 'enter_time', 'enter_dt', 'enter_ts' }

            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except Exception:
                        continue

                    code = rec.get("code")
                    if not code:
                        continue
                    if target_code and code.lower() != target_code:
                        continue

                    event = rec.get("event")
                    time_str = rec.get("time")
                    ts = rec.get("ts", 0)

                    if event == "ENTER":
                        open_sessions[code] = {
                            "date": date_key,
                            "in": time_str,
                            "in_ts": ts
                        }
                    elif event == "LEAVE":
                        open_rec = open_sessions.pop(code, None)
                        if open_rec:
                            dur_sec = max(0, ts - open_rec["in_ts"])
                            sessions.append({
                                "code": code,
                                "date": date_key,
                                "in": open_rec["in"],
                                "out": time_str,
                                "duration_sec": round(dur_sec, 1),
                                "duration": parse_duration(dur_sec),
                                "status": "COMPLETED"
                            })
                        else:
                            # Left without known enter in this day file
                            sessions.append({
                                "code": code,
                                "date": date_key,
                                "in": "--",
                                "out": time_str,
                                "duration_sec": 0,
                                "duration": "--",
                                "status": "COMPLETED"
                            })

            # Check for any sessions still open at end of that day
            is_today = (date_key == time.strftime("%Y-%m-%d"))
            for code, open_rec in open_sessions.items():
                now_ts = time.time()
                dur_sec = max(0, now_ts - open_rec["in_ts"]) if is_today else 0
                sessions.append({
                    "code": code,
                    "date": date_key,
                    "in": open_rec["in"],
                    "out": "IN VIEW" if is_today else "UNCLOSED",
                    "duration_sec": round(dur_sec, 1) if is_today else 0,
                    "duration": parse_duration(dur_sec) if is_today else "--",
                    "status": "ACTIVE" if is_today else "UNCLOSED"
                })

        current_dt += timedelta(days=1)

    # Sort descending by date and in time
    sessions.sort(key=lambda s: (s["date"], s["in"]), reverse=True)

    unique_codes = list({s["code"] for s in sessions})
    total_dwell_sec = sum(s["duration_sec"] for s in sessions)

    return {
        "status": "success",
        "start_date": start_date_str,
        "end_date": end_date_str,
        "specific_code": specific_code or None,
        "total_records": len(sessions),
        "total_unique_codes": len(unique_codes),
        "total_dwell_formatted": parse_duration(total_dwell_sec),
        "sessions": sessions
    }
