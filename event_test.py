import requests
import json
import time

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}

BASE = "https://www.nseindia.com"
URLS = [
    ("announcements", BASE + "/api/corporate-announcements?index=equities"),
    ("event_calendar", BASE + "/api/event-calendar"),
    ("board_meetings", BASE + "/api/corporate-board-meetings?index=equities"),
    ("corporate_actions", BASE + "/api/corporates-corporateActions?index=equities"),
    ("financial_results", BASE + "/api/corporate-financial-results?index=equities&period=Quarterly"),
    ("insider_pit", BASE + "/api/corporates-pit?index=equities"),
    ("large_deals", BASE + "/api/snapshot-capital-market-largedeal"),
    ("bulk_csv", "https://nsearchives.nseindia.com/content/equities/bulk.csv"),
    ("block_csv", "https://nsearchives.nseindia.com/content/equities/block.csv"),
]

out = []
s = requests.Session()
s.headers.update(HEADERS)
try:
    r = s.get(BASE, timeout=30)
    out.append("home page status: " + str(r.status_code))
except Exception as e:
    out.append("home page error: " + str(e)[:200])
time.sleep(2)

for name, url in URLS:
    out.append("")
    out.append("== " + name)
    out.append(url)
    try:
        r = s.get(url, timeout=30)
        out.append("status: " + str(r.status_code) + ", bytes: " + str(len(r.content)))
        txt = r.text
        try:
            j = r.json()
            if isinstance(j, list):
                out.append("json list, items: " + str(len(j)))
                if j and isinstance(j[0], dict):
                    out.append("keys: " + ", ".join(list(j[0].keys())[:25]))
            elif isinstance(j, dict):
                out.append("json dict, keys: " + ", ".join(list(j.keys())[:25]))
                for k, v in j.items():
                    if isinstance(v, list) and v and isinstance(v[0], dict):
                        out.append("list '" + k + "' items: " + str(len(v)))
                        out.append("item keys: " + ", ".join(list(v[0].keys())[:25]))
                        break
        except Exception:
            out.append("not json. first 250 chars: " + txt[:250].replace("\n", " | "))
    except Exception as e:
        out.append("error: " + str(e)[:200])
    time.sleep(2)

import os
os.makedirs("data", exist_ok=True)
with open("data/event_test.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(out))
print("\n".join(out))
