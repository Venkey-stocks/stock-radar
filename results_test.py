import re
import datetime
import collections
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
r = s.get(BASE, params={"index": "equities", "period": "Quarterly"}, timeout=60)
print("HTTP", r.status_code)
data = r.json()
items = data if isinstance(data, list) else data.get("data", [])
print("items:", len(items))


def d(x):
    try:
        return datetime.datetime.strptime(str(x)[:11], "%d-%b-%Y")
    except Exception:
        return datetime.datetime(1970, 1, 1)


items = sorted(items, key=lambda x: d(x.get("broadCastDate")), reverse=True)

months = collections.Counter(d(x.get("broadCastDate")).strftime("%Y-%m") for x in items)
print("items per month (last 8 months in list):")
for m in sorted(months)[-8:]:
    print("  ", m, months[m])

good = [x for x in items
        if str(x.get("xbrl") or "").startswith("http") and not str(x.get("xbrl")).endswith("/-")]
print("items with a real xbrl file link:", len(good), "of", len(items))

WANT = ("ProfitLossForPeriod", "RevenueFromOperations", "Income", "ProfitBeforeTax",
        "EarningsPerShare", "ProfitLoss")
for x in good[:2]:
    print("=" * 60)
    print("TEST", x.get("symbol"), x.get("broadCastDate"), x.get("relatingTo"))
    try:
        rr = s.get(x["xbrl"], timeout=60)
        print("HTTP", rr.status_code, "| size:", len(rr.text))
        found = re.findall(r"<([\w\-]+:[\w\-]+)\b([^>]*)>\s*(-?[0-9][0-9.,]*)\s*</", rr.text)
        print("numeric tags found:", len(found))
        shown = 0
        for tag, attrs, val in found:
            if any(w in tag for w in WANT):
                cr = re.search(r'contextRef="([^"]+)"', attrs)
                print("  ", tag, "=", val, "| context:", cr.group(1) if cr else "n/a")
                shown += 1
                if shown >= 15:
                    break
        names = sorted(set(t for t, _, _ in found))
        print("sample tag names:", names[:25])
    except Exception as e:
        print("error:", e)
