import requests, json

H = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}
URLS = [
    "https://www.nseindia.com/api/event-calendar",
    "https://www.nseindia.com/api/corporate-board-meetings?index=equities",
]

s = requests.Session()
s.headers.update(H)
try:
    s.get("https://www.nseindia.com", timeout=20)
except Exception as e:
    print("HOME ERROR:", e)

for u in URLS:
    print("=" * 60)
    print("URL:", u)
    try:
        r = s.get(u, timeout=30)
        print("STATUS:", r.status_code)
        data = r.json()
        if isinstance(data, dict):
            print("DICT KEYS:", list(data.keys()))
            for k, v in data.items():
                if isinstance(v, list):
                    data = v
                    break
        print("ROWS:", len(data))
        print("COLUMNS:", list(data[0].keys()) if data else "none")
        for row in data[:3]:
            print(json.dumps(row, ensure_ascii=False)[:400])
        res = [x for x in data if "result" in json.dumps(x).lower()]
        print("ROWS WITH 'result':", len(res))
        for row in res[:3]:
            print(json.dumps(row, ensure_ascii=False)[:400])
    except Exception as e:
        print("ERROR:", e)
