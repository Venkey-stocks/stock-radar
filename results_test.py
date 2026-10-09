import time
import datetime
import requests
import pandas as pd
import yfinance as yf

H = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-announcements",
}

s = requests.Session()
s.headers.update(H)
try:
    s.get("https://www.nseindia.com", timeout=30)
    s.get("https://www.nseindia.com/companies-listing/corporate-filings-announcements", timeout=30)
except Exception as e:
    print("cookie step error:", e)

today = datetime.date.today()
frm = (today - datetime.timedelta(days=10)).strftime("%d-%m-%Y")
to = today.strftime("%d-%m-%Y")
r = s.get("https://www.nseindia.com/api/corporate-announcements",
          params={"index": "equities", "from_date": frm, "to_date": to}, timeout=60)
print("HTTP", r.status_code)
data = r.json()
items = data if isinstance(data, list) else data.get("data", [])

res = []
seen = set()
for x in items:
    t = str(x.get("attchmntText", "")).lower()
    if "financial result" in t and ("period ended" in t or "quarter ended" in t):
        sym = x.get("symbol")
        if sym and sym not in seen:
            seen.add(sym)
            res.append(x)
print("companies with results announcements (10 days):", len(res))


def row(q, names):
    for n in names:
        if n in q.index:
            return q.loc[n]
    return None


for x in res[:15]:
    sym = x["symbol"]
    print("=" * 60)
    print(sym, "| announced:", x.get("an_dt"))
    print("  text:", str(x.get("attchmntText"))[:140].replace("\n", " "))
    try:
        q = yf.Ticker(sym + ".NS").quarterly_income_stmt
        if q is None or q.empty:
            print("  yfinance: n/a (empty)")
            continue
        q = q.sort_index(axis=1, ascending=False)
        latest = q.columns[0]
        print("  yfinance latest quarter:", str(latest)[:10])
        ni = row(q, ["Net Income", "Net Income Common Stockholders"])
        rev = row(q, ["Total Revenue", "Operating Revenue"])
        prev = None
        for c in q.columns[1:]:
            if abs((latest - c).days - 365) <= 20:
                prev = c
                break
        for name, rw in (("Net profit", ni), ("Revenue", rev)):
            if rw is None:
                print("  ", name, ": n/a")
                continue
            cur = rw[latest]
            old = rw[prev] if prev is not None else None
            if pd.isna(cur) or old is None or pd.isna(old) or old == 0:
                print("  ", name, ": latest", cur, "| year-ago n/a")
            else:
                print("  ", name, ": latest %.1f cr | year-ago %.1f cr | change %+.0f%%"
                      % (cur / 1e7, old / 1e7, (cur / old - 1) * 100 if old > 0 else float("nan")))
    except Exception as e:
        print("  error:", e)
    time.sleep(1)
