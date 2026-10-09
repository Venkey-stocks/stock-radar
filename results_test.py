import json
import requests

H = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-financial-results",
}

s = requests.Session()
s.headers.update(H)
try:
    s.get("https://www.nseindia.com", timeout=30)
    s.get("https://www.nseindia.com/companies-listing/corporate-filings-financial-results", timeout=30)
except Exception as e:
    print("cookie step error:", e)

BASE = "https://www.nseindia.com/api/corporates-financial-results"
TRIES = [
    {"index": "equities", "period": "Quarterly", "from_date": "01-07-2026", "to_date": "09-10-2026"},
    {"index": "equities", "period": "Quarterly"},
    {"index": "equities"},
]
KEYWORDS = ("income", "profit", "pat", "revenue", "sales", "eps", "loss", "netprofit")

for i, params in enumerate(TRIES, 1):
    print("=" * 60)
    print("TRY", i, params)
    try:
        r = s.get(BASE, params=params, timeout=40)
        print("HTTP", r.status_code)
        data = r.json()
    except Exception as e:
        print("error:", e)
        continue
    items = data if isinstance(data, list) else data.get("data", [])
    print("items:", len(items))
    if not items:
        continue
    keys = list(items[0].keys())
    print("KEYS:", keys)
    hit = [k for k in keys if any(w in k.lower() for w in KEYWORDS)]
    print("KEYS that look like numbers (profit/income/revenue/eps):", hit)
    for it in items[:2]:
        print(json.dumps(it, ensure_ascii=False)[:700])
    filled = sum(1 for it in items if any(it.get(k) not in (None, "", "-") for k in hit))
    print("items with at least one number field filled:", filled, "of", len(items))
    break
