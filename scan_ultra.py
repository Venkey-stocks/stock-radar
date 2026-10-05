import pandas as pd
import numpy as np

CAPITAL = 100000                 # your trading capital in Rs. CHANGE THIS
RISK_PCT = 0.01                  # 1% risk per trade
MIN_PRICE = 50
MIN_TRADED_VALUE = 10_00_00_000  # Rs 10 crore daily traded value
MAX_STOP_DIST = 0.06             # stop-loss within 6%

df = pd.read_csv("data/prices.csv.gz")
df["Date"] = df["Date"].astype(str).str[:10]
df = df.sort_values(["Symbol", "Date"])
last_date = df["Date"].max()

all_ret = []
cands = []

for sym, d in df.groupby("Symbol"):
    d = d.dropna(subset=["Close", "High", "Low", "Volume"])
    if len(d) < 120 or d["Date"].iloc[-1] != last_date:
        continue
    c = d["Close"].to_numpy()
    h = d["High"].to_numpy()
    l = d["Low"].to_numpy()
    v = d["Volume"].to_numpy()
    close, high, low, vol = c[-1], h[-1], l[-1], v[-1]

    if close < MIN_PRICE or (c[-20:] * v[-20:]).mean() < MIN_TRADED_VALUE:
        continue

    ret63 = close / c[-64] - 1
    all_ret.append(ret63)

    avg20v = v[-21:-1].mean()
    if avg20v == 0 or close / c[-3] - 1 >= 0.10:
        continue

    res = h[-21:-1].max()
    rng = (h - l) / c
    older = rng[-51:-11].mean()
    contr = rng[-11:-1].mean() / older if older > 0 else 1
    vdry = v[-6:-1].mean() / avg20v
    vratio = vol / avg20v
    cpos = (close - low) / (high - low) if high > low else 0.5
    sma20, sma50 = c[-20:].mean(), c[-50:].mean()
    above = close > res

    if above and vratio >= 2 and cpos >= 0.7:
        status = "Breakout"
    elif above and vratio >= 1.5:
        status = "Near Miss"
    elif (not above) and (res - close) / res <= 0.05 and contr < 0.9:
        status = "Setup"
    else:
        continue

    if status == "Setup":
        entry = res * 1.002
        stop = l[-5:].min()
        gap = (res - close) / res
    else:
        entry = close
        stop = low
        gap = (close - res) / res

    risk = entry - stop
    if risk <= 0 or risk / entry > MAX_STOP_DIST:
        continue

    cands.append(dict(Symbol=sym, Status=status, Close=close, Entry=entry,
                      Stop=stop, Target=entry + 2 * risk,
                      StopDist=risk / entry * 100,
                      Qty=int(CAPITAL * RISK_PCT / risk),
                      VolRatio=vratio, contr=contr, vdry=vdry, cpos=cpos,
                      gap=gap, ret63=ret63,
                      trend=(10 if close > sma50 and sma20 > sma50
                             else 5 if close > sma50 else 0)))

all_ret = np.array(all_ret)
rows = []
for r in cands:
    s = 15 if r["contr"] < 0.6 else 10 if r["contr"] < 0.8 else 5 if r["contr"] < 1.0 else 0
    s += 15 if r["gap"] <= 0.03 else (10 if r["Status"] == "Setup" else 8)
    s += 10 if r["vdry"] < 0.8 else 5 if r["vdry"] < 1.0 else 0
    if r["Status"] != "Setup":
        s += 20
        s += 10 if r["VolRatio"] >= 3 else 8 if r["VolRatio"] >= 2 else 4
        s += 10 if r["cpos"] >= 0.8 else 7 if r["cpos"] >= 0.7 else 3 if r["cpos"] >= 0.5 else 0
    s += 10 * (all_ret < r["ret63"]).mean()
    s += r["trend"]
    s = round(s)
    band = "High Conviction" if s >= 80 else "Good Setup" if s >= 65 else "Early Watch"
    rows.append(dict(Date=last_date, Symbol=r["Symbol"], Status=r["Status"],
                     Score=s, Band=band, Close=round(r["Close"], 2),
                     Entry=round(r["Entry"], 2), Stop=round(r["Stop"], 2),
                     Target=round(r["Target"], 2),
                     StopDistPct=round(r["StopDist"], 1), Qty=r["Qty"],
                     VolRatio=round(r["VolRatio"], 1)))

cols = ["Date", "Symbol", "Status", "Score", "Band", "Close", "Entry",
        "Stop", "Target", "StopDistPct", "Qty", "VolRatio"]
out = pd.DataFrame(rows, columns=cols)
if len(out):
    out = out.sort_values("Score", ascending=False)
out.to_csv("data/ultra_short.csv", index=False)
print("Data date:", last_date, "| Results:", len(out))
print(out.head(20).to_string(index=False))
