import datetime
import collections
import requests

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
frm = (today - datetime.timedelta(days=7)).strftime("%d-%m-%Y")
to = today.strftime("%d-%m-%Y")

r = s.get("https://www.nseindia.com/api/corporate-announcements",
          params={"index": "equities", "from_date": frm, "to_date": to}, timeout=60)
print("HTTP", r.status_code)
data = r.json()
items = data if isinstance(data, list) else data.get("data", [])
print("announcements:", len(items))

print("--- top 15 'desc' categories ---")
for k, v in collections.Counter(str(x.get("desc")) for x in items).most_common(15):
    print("  ", v, "|", k)

print("--- hasXbrl values ---")
print(dict(collections.Counter(str(x.get("hasXbrl")) for x in items)))

xb = [x for x in items if str(x.get("hasXbrl")).lower() in ("true", "1", "y", "yes")]
print("items with hasXbrl true:", len(xb))

ext = collections.Counter()
for x in xb:
    f = str(x.get("attchmntFile") or "")
    ext[f.rsplit(".", 1)[-1].lower() if "." in f else "none"] += 1
print("their attachment types:", dict(ext))

for x in xb[:6]:
    print("-", x.get("symbol"), "|", x.get("an_dt"), "|", x.get("desc"))
    print("   file:", x.get("attchmntFile"))
    print("   csvName:", x.get("csvName"), "| bflag:", x.get("bflag"))
    print("   text:", str(x.get("attchmntText"))[:150].replace("\n", " "))
