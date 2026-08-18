#!/usr/bin/env python3
import json, os, re, time, urllib.parse, urllib.request
from datetime import datetime, timedelta
from pathlib import Path

LOG_FILE = Path(os.getenv("XRAY_ACCESS_LOG", "/var/log/xray/access.log"))
STATE_FILE = Path(os.getenv("MIFA_NOTIFY_STATE", "/var/lib/mifa/online_ips.json"))
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("NOTIFY_CHAT_ID", "").strip()
WINDOW_MINUTES = int(os.getenv("NOTIFY_WINDOW_MINUTES", "5"))
GEO = os.getenv("NOTIFY_GEO", "0").strip() == "1"
LINE_RE = re.compile(r"^(\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2})\..*?from (?:tcp:)?(\d+\.\d+\.\d+\.\d+):")
USER_RE = re.compile(r"email: ([^ ]+)")

def recent_ips():
    cutoff = datetime.now() - timedelta(minutes=WINDOW_MINUTES)
    found = {}
    if not LOG_FILE.exists(): return found
    with LOG_FILE.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            m = LINE_RE.search(line)
            if not m: continue
            try: ts = datetime.strptime(m.group(1), "%Y/%m/%d %H:%M:%S")
            except ValueError: continue
            if ts < cutoff: continue
            user_m = USER_RE.search(line)
            found[m.group(2)] = user_m.group(1) if user_m else ""
    return found

def load_previous():
    try: return set(json.loads(STATE_FILE.read_text()).get("ips", []))
    except Exception: return set()

def save_current(ips):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps({"ips": sorted(ips), "updated": int(time.time())}) + "\n")
    tmp.replace(STATE_FILE)

def geo(ip):
    if not GEO: return {}
    try:
        with urllib.request.urlopen(f"http://ip-api.com/json/{urllib.parse.quote(ip)}?fields=status,country,regionName,city,isp", timeout=5) as r:
            data = json.loads(r.read().decode("utf-8", "replace"))
            return data if data.get("status") != "fail" else {}
    except Exception: return {}

def send(text):
    if not BOT_TOKEN or not CHAT_ID: return
    data = urllib.parse.urlencode({"chat_id": CHAT_ID, "text": text}).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", data=data)
    with urllib.request.urlopen(req, timeout=10): pass

def main():
    current = recent_ips(); previous = load_previous()
    if not STATE_FILE.exists(): save_current(current.keys()); return
    for ip in sorted(set(current) - previous):
        info = geo(ip); parts = ["🔔 Новое подключение к VPN", f"IP: {ip}"]
        if current[ip]: parts.append(f"User: {current[ip]}")
        if info.get("city"): parts.append(f"Город: {info['city']}")
        if info.get("regionName") and info.get("regionName") != info.get("city"): parts.append(f"Регион: {info['regionName']}")
        if info.get("country"): parts.append(f"Страна: {info['country']}")
        if info.get("isp"): parts.append(f"Провайдер: {info['isp']}")
        parts.append(datetime.now().strftime("Время: %d.%m.%Y %H:%M:%S"))
        try: send("\n".join(parts))
        except Exception: pass
    save_current(current.keys())

if __name__ == "__main__": main()
