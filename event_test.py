import os
import time
import requests

H = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}
B = "https://www.nseindia.com/api/"
URLS = [
    ("announcements_range", B + "corporate-announcements?index=equities&from_date=01-10-2026&to_date=09-10-2026"),
    ("corp_actions_range", B + "corporates-corporateActions?index=equities&from_date=09-10-2026&to_date=31-12-2026"),
    ("pit_range", B + "corporates-pit?index=equities&from_date=01-10-2026&to_date=09-10-2026"),
    ("results_a", B + "corporates-financial-results?index=equities&period=Quarterly"),
    ("results_b", B + "corporates-financial-results?index=equities&period=Quarterly&from_date=01-10-2026&to_date=09-10-2026"),
    ("board_range", B + "corporate-board-meetings?index=equities&from_date=09-10-2026&to_date=31-10-2026"),
]

out = []
s = requests.Session()
s.headers.update(H)
try:
    s.get("https://www.nseindia.com", timeout=30)
except Exception as e:
    out.append("home error: " + str(e)[:100])
time.sleep(2)

for name, url in URLS:
    out.append("")
    out.append("== " + name)
    try:
        r = s.get(url, timeout=30)
        out.append("status: " + str(r.status_code) + ", bytes: " + str(len(r.content)))
        try:
            j = r.json()
        except Exception:
            out.append("not json: " + r.text[:150].replace("\n", " "))
            j = None
        if isinstance(j, dict) and isinstance(j.get("data"), list):
            j = j["data"]
        if isinstance(j, list):
            out.append("items: " + str(len(j)))
            if j and isinstance(j[0], dict):
                out.append("keys: " + ", ".join(list(j[0].keys())[:40]))
                out.append("sample: " + str(j[0])[:500])
        elif isinstance(j, dict):
            out.append("dict keys: " + ", ".join(list(j.keys())[:20]))
    except Exception as e:
        out.append("error: " + str(e)[:150])
    time.sleep(2)

os.makedirs("data", exist_ok=True)
with open("data/event_test.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(out))
print("\n".join(out))
