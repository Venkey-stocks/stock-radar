import os
import json
import pandas as pd


def clip01(x):
    return float(min(max(x, 0.0), 1.0))


px = pd.read_csv("data/prices.csv.gz", parse_dates=["Date"])
px = px.dropna(subset=["Close", "Volume"])
close = px.pivot_table(index="Date", columns="Symbol", values="Close").sort_index()
vol = px.pivot_table(index="Date", columns="Symbol", values="Volume").sort_index()
vol = vol.reindex(index=close.index, columns=close.columns)
date_str = close.index[-1].strftime("%Y-%m-%d")

tv = (close.iloc[-20:] * vol.iloc[-20:]).mean()
ok = (tv >= 10e7) & (close.iloc[-1] >= 50)
c = close.loc[:, ok[ok].index]
c = c.loc[:, c.iloc[-1].notna() & c.iloc[-2].notna()]
n = int(c.shape[1])

checks = []


def add(name, text, pts, mx, good):
    checks.append({"name": name, "text": text, "points": round(pts, 1), "max": mx, "good": good})


# ---------- Index ----------
idx_name, ia = None, None
if os.path.exists("data/index.csv"):
    ix = pd.read_csv("data/index.csv", parse_dates=["Date"])
    for name in ("NIFTY500", "NIFTY50"):
        g = ix[ix["Symbol"] == name].sort_values("Date")["Close"].dropna().values
        if len(g) >= 210:
            idx_name, ia = name, g
            break

ret5 = None
if ia is not None:
    last = ia[-1]
    s50, s200, s50p = ia[-50:].mean(), ia[-200:].mean(), ia[-60:-10].mean()
    ret5 = (last / ia[-6] - 1) * 100
    ret1 = (last / ia[-2] - 1) * 100
    add("Index vs 50-day average", "%s is %.1f%% %s its 50-day average" % (idx_name, abs(last / s50 - 1) * 100, "above" if last > s50 else "below"),
        20 if last > s50 else 0, 20, last > s50)
    add("Index vs 200-day average", "%s is %.1f%% %s its 200-day average" % (idx_name, abs(last / s200 - 1) * 100, "above" if last > s200 else "below"),
        15 if last > s200 else 0, 15, last > s200)
    add("50-day average direction", "The 50-day average is %s" % ("rising" if s50 > s50p else "falling"),
        10 if s50 > s50p else 0, 10, s50 > s50p)
    add("Index last 5 days", "%s moved %.1f%% in 5 trading days (today %.1f%%)" % (idx_name, ret5, ret1),
        5 if ret5 > 0 else 0, 5, ret5 > 0)

# ---------- Breadth ----------
if n >= 50:
    cur = c.iloc[-1]
    p50 = float((cur > c.iloc[-50:].mean()).mean() * 100)
    p200 = float((cur > c.iloc[-200:].mean()).mean() * 100)
    chg = cur / c.iloc[-2] - 1
    adv, dec = int((chg > 0).sum()), int((chg < 0).sum())
    nh = int((cur >= c.iloc[-250:].max() * 0.98).sum())
    nl = int((cur <= c.iloc[-250:].min() * 1.02).sum())
    add("Stocks above 50-day average", "%.0f%% of %d liquid stocks are above their 50-day average" % (p50, n),
        clip01((p50 - 30) / 40.0) * 20, 20, p50 >= 50)
    add("Stocks above 200-day average", "%.0f%% are above their 200-day average" % p200,
        clip01((p200 - 30) / 40.0) * 10, 10, p200 >= 50)
    ar = adv / float(adv + dec) if (adv + dec) else 0.5
    add("Advancers vs decliners today", "%d stocks rose, %d fell" % (adv, dec),
        clip01((ar - 0.3) / 0.4) * 10, 10, adv > dec)
    hr = nh / float(nh + nl) if (nh + nl) else 0.5
    add("Near 52-week highs vs lows", "%d stocks are near a 52-week high, %d near a 52-week low" % (nh, nl),
        clip01(hr) * 10, 10, nh > nl)

got = sum(x["points"] for x in checks)
mx = sum(x["max"] for x in checks)
score = round(got / mx * 100, 1) if mx else 0.0
if mx < 60:
    status, advice = "Unknown", "Not enough data to judge the market today."
elif score >= 65:
    status = "Favorable"
    advice = "Market is healthy. Breakouts and pullbacks have a better chance of working. Normal position sizes are reasonable."
elif score >= 40:
    status = "Cautious"
    advice = "Market is mixed. Be selective: prefer High Conviction setups, consider smaller positions, and expect more failed breakouts."
else:
    status = "Weak"
    advice = "Market is weak. Most breakouts tend to fail in such conditions. Fewer or no new trades, and keep stops tight to your plan."

out = {"Date": date_str, "Score": score, "Status": status, "Advice": advice, "Index": idx_name or "n/a",
       "LiquidStocks": n, "ChecksMax": mx, "Checks": checks}
os.makedirs("data", exist_ok=True)
with open("data/market_health.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1)

# ---------- history ----------
hp = "data/market_health_history.csv"
hist = pd.read_csv(hp) if os.path.exists(hp) else pd.DataFrame(columns=["Date", "Score", "Status"])
hist = hist[hist["Date"] != date_str]
hist = pd.concat([hist, pd.DataFrame([{"Date": date_str, "Score": score, "Status": status}])], ignore_index=True)
hist.sort_values("Date").to_csv(hp, index=False)

print("data తేదీ:", date_str, "| Market health:", status, "| score:", score, "| liquid stocks:", n)
for x in checks:
    print(" -", x["name"], ":", x["text"], "(%s/%s)" % (x["points"], x["max"]))
