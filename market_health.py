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
    checks.append({
        "name": name,
        "text": text,
        "points": round(float(pts), 1),
        "max": int(mx),
        "good": bool(good),
    })


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
    last = float(ia[-1])
    s50, s200, s50p = float(ia[-50:].mean()), float(ia[-200:].mean()), float(ia[-60:-10].mean())
    ret5 = (last / float(ia[-6]) - 1) * 100
    ret1 = (last / float(ia[-2]) - 1) * 100
    add(
        "Index vs 50-day average",
        "%s is %.1f%% %s its 50-day average"
        % (idx_name, abs(last / s50 - 1) * 100, "above" if last > s50 else "below"),
        20 if last > s50 else 0,
        20,
        last > s50,
    )
    add(
        "Index vs 200-day average",
        "%s is %.1f%% %s its 200-day average"
        % (idx_name, abs(last / s200 - 1) * 100, "above" if last > s200 else "below"),
        15 if last > s200 else 0,
        15,
        last > s200,
    )
    add(
        "50-day average direction",
        "The 50-day average is %s" % ("rising" if s50 > s50p else "falling"),
        10 if s50 > s50p else 0,
        10,
        s50 > s50p,
    )
    add(
        "Index last 5 days",
        "%s moved %.1f%% in 5 trading days (today %.1f%%)" % (idx_name, ret5, ret1),
        5 if ret5 > 0 else 0,
        5,
        ret5 > 0,
    )

# ---------- Breadth ----------
p20, p50, p200 = 0.0, 0.0, 0.0
adv, dec, nh, nl = 0, 0, 0, 0

if n >= 50:
    cur = c.iloc[-1]
    p20 = round(float((cur > c.iloc[-20:].mean()).mean() * 100), 1)
    p50 = round(float((cur > c.iloc[-50:].mean()).mean() * 100), 1)
    p200 = round(float((cur > c.iloc[-200:].mean()).mean() * 100), 1)
    chg = cur / c.iloc[-2] - 1
    adv, dec = int((chg > 0).sum()), int((chg < 0).sum())
    nh = int((cur >= c.iloc[-250:].max() * 0.98).sum())
    nl = int((cur <= c.iloc[-250:].min() * 1.02).sum())

    add(
        "Stocks above 20-day average",
        "%.1f%% of %d liquid stocks are above their 20-day average" % (p20, n),
        clip01((p20 - 30) / 40.0) * 10,
        10,
        p20 >= 50,
    )
    add(
        "Stocks above 50-day average",
        "%.1f%% are above their 50-day average" % p50,
        clip01((p50 - 30) / 40.0) * 15,
        15,
        p50 >= 50,
    )
    add(
        "Stocks above 200-day average",
        "%.1f%% are above their 200-day average" % p200,
        clip01((p200 - 30) / 40.0) * 10,
        10,
        p200 >= 50,
    )
    ar = adv / float(adv + dec) if (adv + dec) else 0.5
    add(
        "Advancers vs decliners today",
        "%d stocks rose, %d fell" % (adv, dec),
        clip01((ar - 0.3) / 0.4) * 10,
        10,
        adv > dec,
    )
    hr = nh / float(nh + nl) if (nh + nl) else 0.5
    add(
        "Near 52-week highs vs lows",
        "%d stocks are near a 52-week high, %d near a 52-week low" % (nh, nl),
        clip01(hr) * 5,
        5,
        nh > nl,
    )

got = sum(x["points"] for x in checks)
mx = sum(x["max"] for x in checks)
score = round(got / mx * 100, 1) if mx else 0.0

if mx < 60:
    status, advice = "Unknown", "Not enough data to judge the market today."
elif score >= 65:
    status = "Favorable"
    advice = "మార్కెట్ చాలా బలంగా ఉంది. బ్రేక్‌అవుట్స్ మరియు పుల్‌బ్యాక్స్ వర్కవుట్ అయ్యే అవకాశాలు ఎక్కువ. సాధారణ పొజిషన్ సైజులతో ట్రేడ్ చేయవచ్చు."
elif score >= 40:
    status = "Cautious"
    advice = "మార్కెట్ మిశ్రమంగా ఉంది. కేవలం హై-కన్విక్షన్ సెటప్‌లు మాత్రమే ఎంచుకోండి. పొజిషన్ సైజులు తగ్గించండి."
else:
    status = "Weak"
    advice = "మార్కెట్ బలహీనంగా ఉంది. మెజారిటీ బ్రేక్‌అవుట్స్ ఫెయిల్ అయ్యే ప్రమాదం ఉంది. కొత్త ట్రేడ్స్ తీసుకోకపోవడం మంచిది, కఠినమైన స్టాప్‌లాస్ పాటించండి."

out = {
    "Date": date_str,
    "Score": float(score),
    "Status": status,
    "Advice": advice,
    "Index": idx_name or "n/a",
    "LiquidStocks": n,
    "ChecksMax": int(mx),
    "Breadth": {
        "p20": p20,
        "p50": p50,
        "p200": p200,
        "adv": adv,
        "dec": dec,
        "nh": nh,
        "nl": nl,
    },
    "Checks": checks,
}

os.makedirs("data", exist_ok=True)
with open("data/market_health.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)

# ---------- History ----------
hp = "data/market_health_history.csv"
hist = pd.read_csv(hp) if os.path.exists(hp) else pd.DataFrame(columns=["Date", "Score", "Status"])
hist = hist[hist["Date"] != date_str]
hist = pd.concat([hist, pd.DataFrame([{"Date": date_str, "Score": score, "Status": status}])], ignore_index=True)
hist.sort_values("Date").to_csv(hp, index=False)

print("డేటా తేదీ:", date_str, "| మార్కెట్ హెల్త్:", status, "| స్కోర్:", score, "| లిక్విడ్ స్టాక్స్:", n)
print("బ్రెడ్త్ గణాంకాలు -> >20-DMA: %.1f%% | >50-DMA: %.1f%% | >200-DMA: %.1f%%" % (p20, p50, p200))
