import os
import glob
import numpy as np
import pandas as pd

LOOKBACK = 60                       # గత ఎన్ని ట్రేడింగ్ రోజుల signals చూడాలి
WINDOW = {"ultra": 5, "short": 20}  # 15%+ పెరగడానికి గరిష్ట రోజులు
MIN_GAIN = 15.0
MIN_PRICE = 50
MIN_TV = 10e7                       # 20 రోజుల సగటు traded value Rs 10 కోట్లు
MAX_STOP = {"ultra": 6.0, "short": 7.5}

px = pd.read_csv("data/prices.csv.gz", parse_dates=["Date"])
px = px.dropna(subset=["Open", "High", "Low", "Close", "Volume"])
groups = {s: g.sort_values("Date").reset_index(drop=True) for s, g in px.groupby("Symbol")}

# ---------- history snapshots: (scan, తేదీ) -> {Symbol: Status} ----------
snap = {}
for scan in ("ultra", "short"):
    for f in glob.glob("data/history/%s_*.csv" % scan):
        d = os.path.basename(f)[len(scan) + 1:-4]
        try:
            s = pd.read_csv(f)
        except Exception:
            snap[(scan, d)] = {}
            continue
        snap[(scan, d)] = {r.Symbol: r.Status for r in s.itertuples()}


def diagnose(scan, h, l, c, v, i):
    """ఆ రోజు మన నియమాలలో ఏది అడ్డు అయి ఉండొచ్చో అంచనా (పాత రోజులకు snapshot లేనప్పుడు)."""
    close = c[i]
    if i < 60:
        return "Not enough price history"
    if scan == "ultra" and c[i] / c[i - 2] - 1 > 0.10:
        return "Already rose 10%+ in 2 days (excluded)"
    low_n = l[i - 4:i + 1].min() if scan == "ultra" else l[i - 6:i + 1].min()
    stop = low_n * 0.999
    stop_pct = (close - stop) / close * 100
    if stop_pct > MAX_STOP[scan]:
        return "Stop-loss too far (%.1f%%, limit %.1f%%)" % (stop_pct, MAX_STOP[scan])
    res = h[i - 20:i].max()
    vol_avg = v[i - 20:i].mean()
    vol_ratio = v[i] / vol_avg if vol_avg > 0 else 0
    if scan == "ultra":
        if close > res * 1.08:
            return "Already extended above breakout level"
        dist = (res / close - 1) * 100
        if dist > 5:
            return "Too far below resistance (%.1f%%)" % dist
        if close > res and vol_ratio < 1.2:
            return "Broke out on weak volume"
        return "Setup conditions not fully met (low score)"
    if i >= 199:
        sma50 = c[i - 49:i + 1].mean()
        sma200 = c[i - 199:i + 1].mean()
        sma50p = c[i - 59:i - 9].mean()
        if not (close > sma50 and close > sma200 and sma50 > sma50p):
            return "Trend filter failed (below 50/200-day avg or 50-day not rising)"
    ext = (close / c[i - 19:i + 1].mean() - 1) * 100
    if ext > 15:
        return "More than 15% above 20-day average (extended)"
    return "No base or pullback setup (or score below 40)"


rows = []
for sym, g in groups.items():
    n = len(g)
    if n < 80:
        continue
    h = g["High"].values
    l = g["Low"].values
    c = g["Close"].values
    v = g["Volume"].values.astype(float)
    dates = g["Date"].dt.strftime("%Y-%m-%d").values
    for scan, W in WINDOW.items():
        last = -999
        for i in range(max(60, n - LOOKBACK), n - 1):
            fut = c[i + 1:i + 1 + W]
            if len(fut) == 0:
                continue
            gain = (fut.max() / c[i] - 1) * 100
            if gain < MIN_GAIN:
                continue
            if c[i] < MIN_PRICE or (c[i - 19:i + 1] * v[i - 19:i + 1]).mean() < MIN_TV:
                continue
            if i - last < W:
                continue
            last = i
            days = int(np.argmax(fut >= c[i] * 1.15)) + 1
            # snapshot తనిఖీ: ఆ రోజు లేదా 2 రోజుల ముందు వరకు
            have, listed = False, ""
            for j in (i, i - 1, i - 2):
                sp = snap.get((scan, dates[j]))
                if sp is not None:
                    have = True
                    if sym in sp:
                        listed = sp[sym]
                        break
            if listed:
                result, reason = "Caught", ""
            elif have:
                result, reason = "Missed", diagnose(scan, h, l, c, v, i)
            else:
                result, reason = "Unknown", "No snapshot that day. Approx: " + diagnose(scan, h, l, c, v, i)
            rows.append({
                "Date": dates[i], "Scan": scan, "Symbol": sym, "Close": round(c[i], 2),
                "PeakClose": round(fut.max(), 2), "GainPct": round(gain, 1), "Days": days,
                "Result": result, "ListedStatus": listed, "Reason": reason,
            })

cols = ["Date", "Scan", "Symbol", "Close", "PeakClose", "GainPct", "Days", "Result", "ListedStatus", "Reason"]
out = pd.DataFrame(rows, columns=cols)
if len(out):
    out = out.sort_values(["Date", "GainPct"], ascending=[False, False])
out.to_csv("data/miss_report.csv", index=False)
print("మొత్తం big movers:", len(out))
if len(out):
    print(out.groupby(["Scan", "Result"]).size().to_string())
    print(out[out["Result"] != "Caught"]["Reason"].str.replace("No snapshot that day. Approx: ", "").str.replace(r"\(.*\)", "", regex=True).value_counts().head(8).to_string())
