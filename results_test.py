import re
import datetime
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
print("newest broadCastDate:", items[0].get("broadCastDate") if items else None)
print("oldest broadCastDate:", items[-1].get("broadCastDate") if items else None)

with_x = [x for x in items if str(x.get("xbrl") or "").startswith("http")]
print("items with xbrl link:", len(with_x), "of", len(items))
for x in with_x[:5]:
    print(x.get("symbol"), "|", x.get("broadCastDate"), "|", x.get("relatingTo"), "|", x.get("xbrl"))

TAGS = ("ProfitLossForPeriod|RevenueFromOperations|TotalIncome|Income|"
        "ProfitBeforeTax|BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations")
pat = re.compile(r"<(?:\w+:)?(" + TAGS + r")\b([^>]*)>([^<]+)</")

for x in with_x[:3]:
    print("=" * 60)
    print("TEST", x.get("symbol"), x.get("broadCastDate"))
    try:
        rr = s.get(x["xbrl"], timeout=60)
        print("HTTP", rr.status_code, "| size:", len(rr.text))
        print("start:", rr.text[:150].replace("\n", " "))
        found = pat.findall(rr.text)
        print("number tags found:", len(found))
        for tag, attrs, val in found[:12]:
            cr = re.search(r'contextRef="([^"]+)"', attrs)
            print(" ", tag, "=", val.strip(), "| context:", cr.group(1) if cr else "n/a")
    except Exception as e:
        print("error:", e)
