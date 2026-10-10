import requests, csv, os, sys, time
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))
today = datetime.now(IST).date()

H = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}
URL = "https://www.nseindia.com/api/event-calendar"

data = None
for attempt in range(3):
    try:
        s = requests.Session()
        s.headers.update(H)
        s.get("https://www.nseindia.com", timeout=20)
        r = s.get(URL, timeout=30)
        r.raise_for_status()
        data = r.json()
        break
    except Exception as e:
        print("attempt", attempt + 1, "failed:", e)
        time.sleep(5)

if data is None:
    print("FAILED: NSE data not fetched, old file kept")
    sys.exit(1)

if isinstance(data, dict):
    for v in data.values():
        if isinstance(v, list):
            data = v
            break

out = {}
for x in data:
    text = (str(x.get("purpose", "")) + " " + str(x.get("bm_desc", ""))).lower()
    if "result" not in text:
        continue
    try:
        d = datetime.strptime(str(x.get("date", "")).strip(), "%d-%b-%Y").date()
    except Exception:
        continue
    if d < today:
        continue
    sym = str(x.get("symbol", "")).strip()
    if not sym:
        continue
    out[(sym, d)] = [
        sym,
        str(x.get("company", "")).strip(),
        d.isoformat(),
        str(x.get("purpose", "")).strip(),
        str(x.get("bm_desc", "")).strip(),
    ]

rows = sorted(out.values(), key=lambda r: (r[2], r[0]))

os.makedirs("data", exist_ok=True)
with open("data/results_calendar.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["Symbol", "Company", "Date", "Purpose", "Detail"])
    w.writerows(rows)

print("Rows saved:", len(rows))
if rows:
    print("Date range:", rows[0][2], "to", rows[-1][2])
    for r in rows[:3]:
        print(r[:4])
