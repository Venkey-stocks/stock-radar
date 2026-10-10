import requests, json
import yfinance as yf

H = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.bseindia.com/",
    "Origin": "https://www.bseindia.com",
}
URL = "https://api.bseindia.com/BseIndiaAPI/api/ListofScripData/w?Group=&Scripcode=&industry=&segment=Equity&status=Active"

print("=" * 60)
print("PART 1: BSE scrip list")
try:
    r = requests.get(URL, headers=H, timeout=40)
    print("STATUS:", r.status_code)
    print("CONTENT-TYPE:", r.headers.get("content-type"))
    print("LENGTH:", len(r.text))
    print("START:", r.text[:300].replace("\n", " "))
    data = r.json()
    if isinstance(data, dict):
        print("DICT KEYS:", list(data.keys()))
        for v in data.values():
            if isinstance(v, list):
                data = v
                break
    print("ROWS:", len(data))
    print("COLUMNS:", list(data[0].keys()) if data else "none")
    for row in data[:3]:
        print(json.dumps(row, ensure_ascii=False)[:400])
except Exception as e:
    print("ERROR:", e)

print("=" * 60)
print("PART 2: Yahoo prices for BSE tickers")
for t in ["500325.BO", "RELIANCE.BO", "532540.BO", "TCS.BO"]:
    try:
        df = yf.download(t, period="1mo", progress=False, auto_adjust=False)
        print(t, "rows:", len(df), "last date:", (str(df.index[-1].date()) if len(df) else "none"))
    except Exception as e:
        print(t, "ERROR:", e)
