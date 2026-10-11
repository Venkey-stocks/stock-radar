import os
import json
import pandas as pd

DAYS = 120   # chart లో చూపే చివరి రోజుల సంఖ్య

syms = set()
for path in ("data/ultra_short.csv", "data/short_term.csv", "data/multibagger.csv", "data/quality.csv", "data/newlistings.csv"):
    if not os.path.exists(path):
        print("లేదు:", path)
        continue
    try:
        d = pd.read_csv(path)
        cols = {c.lower(): c for c in d.columns}
        if "symbol" in cols:
            syms.update(d[cols["symbol"]].astype(str).str.strip().tolist())
    except Exception as e:
        print("చదవడం కుదరలేదు", path, e)
print("charts కావలసిన stocks:", len(syms))

df = pd.read_csv("data/prices.csv.gz", parse_dates=["Date"])
df = df.dropna(subset=["Open", "High", "Low", "Close"])
df = df[df["Symbol"].isin(syms)]

out = {}
for sym, g in df.groupby("Symbol"):
    g = g.sort_values("Date").tail(DAYS)
    out[sym] = {
        "d": [x.strftime("%Y-%m-%d") for x in g["Date"]],
        "o": [round(float(x), 2) for x in g["Open"]],
        "h": [round(float(x), 2) for x in g["High"]],
        "l": [round(float(x), 2) for x in g["Low"]],
        "c": [round(float(x), 2) for x in g["Close"]],
    }

os.makedirs("data", exist_ok=True)
with open("data/charts.json", "w") as f:
    json.dump(out, f, separators=(",", ":"))
print("charts.json లో stocks:", len(out))
