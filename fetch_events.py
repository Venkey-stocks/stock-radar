import os
import io
import time
import datetime as dt
import pandas as pd
import requests

H = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}
B = "https://www.nseindia.com/api/"
now = dt.datetime.utcnow() + dt.timedelta(hours=5, minutes=30)
today = now.date()


def d(x):
    return x.strftime("%d-%m-%Y")


s = requests.Session()
s.headers.update(H)
try:
    s.get("https://www.nseindia.com", timeout=30)
except Exception:
    pass
time.sleep(2)


def get_json(url):
    for _ in range(3):
        try:
            r = s.get(url, timeout=90)
            if r.status_code == 200:
                return r.json()
            print("status", r.status_code)
        except Exception as e:
            print("error", str(e)[:100])
        time.sleep(3)
    return None


rows = []


def add(date, symbol, cat, detail, link=""):
    rows.append({
        "date": date,
        "symbol": symbol,
        "category": cat,
        "detail": str(detail)[:200],
        "link": link,
    })


# 1) Announcements (last 7 days)
desc_counts = {}
url = B + "corporate-announcements?index=equities&from_date=%s&to_date=%s" % (
    d(today - dt.timedelta(days=7)), d(today))
a = get_json(url)
if isinstance(a, list):
    for it in a:
        desc = str(it.get("desc") or "")
        desc_counts[desc] = desc_counts.get(desc, 0) + 1
        low = desc.lower()
        cat = None
        if ("award" in low or "bagging" in low or "order" in low) and "passed" not in low and "action" not in low:
            cat = "Order win"
        elif "acquisition" in low or "amalgamation" in low or "merger" in low:
            cat = "Acquisition/Merger"
        elif "buy" in low and "back" in low:
            cat = "Buyback"
        elif "preferential" in low:
            cat = "Preferential issue"
        elif "open offer" in low or "takeover" in low:
            cat = "Open offer"
        elif "auditor" in low:
            cat = "Auditor change (check)"
        if cat:
            add(str(it.get("an_dt", ""))[:11], it.get("symbol", ""), cat,
                it.get("attchmntText", desc), it.get("attchmntFile", ""))

# 2) Board meetings with results (next 30 days)
url = B + "corporate-board-meetings?index=equities&from_date=%s&to_date=%s" % (
    d(today), d(today + dt.timedelta(days=30)))
b = get_json(url)
if isinstance(b, list):
    for it in b:
        text = (str(it.get("bm_purpose", "")) + " " + str(it.get("bm_desc", ""))).lower()
        if "financial result" in text:
            add(it.get("bm_date", ""), it.get("bm_symbol", ""), "Results date",
                "Board meeting for financial results")

# 3) Bulk and block deals (BUY, value >= Rs 5 crore)
for name in ["bulk", "block"]:
    try:
        r = s.get("https://nsearchives.nseindia.com/content/equities/%s.csv" % name, timeout=60)
        df = pd.read_csv(io.StringIO(r.text))
        df.columns = [c.strip() for c in df.columns]
        qty = pd.to_numeric(df["Quantity Traded"].astype(str).str.replace(",", ""), errors="coerce")
        price = pd.to_numeric(df.iloc[:, 6].astype(str).str.replace(",", ""), errors="coerce")
        df["value"] = qty * price
        df["qty"] = qty
        df["price"] = price
        df = df[(df["Buy/Sell"].astype(str).str.upper().str.strip() == "BUY") & (df["value"] >= 5e7)]
        for _, x in df.iterrows():
            add(x["Date"], x["Symbol"], name.capitalize() + " BUY",
                "%s | qty %d | price %.2f | %.1f Cr" % (
                    x["Client Name"], x["qty"], x["price"], x["value"] / 1e7))
    except Exception as e:
        print(name, "error", str(e)[:150])

cols = ["date", "symbol", "category", "detail", "link"]
ev = pd.DataFrame(rows, columns=cols)
ev = ev.drop_duplicates(subset=["date", "symbol", "category", "detail"])
os.makedirs("data", exist_ok=True)
ev.to_csv("data/events.csv", index=False)

with open("data/event_desc_counts.txt", "w", encoding="utf-8") as f:
    f.write("TOTAL EVENTS: %d\n" % len(ev))
    f.write("BY CATEGORY: %s\n\n" % ev["category"].value_counts().to_dict())
    f.write("TOP ANNOUNCEMENT TYPES (count | desc)\n")
    for k, v in sorted(desc_counts.items(), key=lambda x: -x[1])[:80]:
        f.write("%d | %s\n" % (v, k))
print("done", len(ev))
