import os
import glob
import numpy as np
import pandas as pd

LOOKBACK = 60                       # గత 60 ట్రేడింగ్ రోజుల విశ్లేషణ
WINDOW = {"ultra": 5, "short": 20, "early": 10}  # 15%+ పెరగడానికి గరిష్ట రోజులు
MIN_GAIN = 15.0
MIN_PRICE = 40
MIN_TV = 5e7                        # 20 రోజుల సగటు Traded Value Rs 5 కోట్లు
MAX_STOP = {"ultra": 6.0, "short": 7.5, "early": 8.0}

px = pd.read_csv("data/prices.csv.gz", parse_dates=["Date"])
px = px.dropna(subset=["Open", "High", "Low", "Close", "Volume"])
groups = {s: g.sort_values("Date").reset_index(drop=True) for s, g in px.groupby("Symbol")}

# ---------- Surveillance (ASM / GSM) Mapping ----------
SURV_MAP = {}
if os.path.exists("data/surveillance.csv"):
    try:
        surv_df = pd.read_csv("data/surveillance.csv")
        for _, row in surv_df.iterrows():
            sym_clean = str(row.get("Symbol", "")).upper().replace(".NS", "").strip()
            stype = str(row.get("Type", "ASM")).upper().strip()
            SURV_MAP[sym_clean] = "GSM" if "GSM" in stype else "ASM"
        print("Surveillance mapped stocks:", len(SURV_MAP))
    except Exception as e:
        print("surveillance.csv లోడింగ్ లోపం:", e)

# ---------- History Snapshots ----------
snap = {}
scans_to_check = tuple(WINDOW.keys())
for scan in scans_to_check:
    for f in glob.glob(f"data/history/{scan}_*.csv"):
        if "rejected" in f:
            continue
        d = os.path.basename(f)[len(scan) + 1:-4]
        try:
            s = pd.read_csv(f)
            status_col = "Status" if "Status" in s.columns else "Band"
            snap[(scan, d)] = {str(r.Symbol).strip(): getattr(r, status_col, "Listed") for r in s.itertuples()}
        except Exception:
            continue


def diagnose(scan, sym, h, l, c, v, i):
    """తిరస్కరణ కారణాన్ని ఖచ్చితంగా నిర్ధారించే లాజిక్"""
    sym_clean = sym.upper().replace(".NS", "").strip()
    if sym_clean in SURV_MAP:
        return f"Exchange {SURV_MAP[sym_clean]} Surveillance (Rejected for risk)"

    close = c[i]
    if i < 60:
        return "Not enough price history"

    if scan == "ultra" and c[i] / c[i - 2] - 1 > 0.10:
        return "Already rose 10%+ in 2 days (excluded)"

    low_n = l[i - 4:i + 1].min() if scan == "ultra" else l[i - 6:i + 1].min()
    stop = low_n * 0.999
    stop_pct = (close - stop) / close * 100
    if stop_pct > MAX_STOP.get(scan, 7.0):
        return "Stop-loss too far (%.1f%%, limit %.1f%%)" % (stop_pct, MAX_STOP.get(scan, 7.0))

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

    return "No base or pullback setup (or score below threshold)"


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

            # Snapshot తనిఖీ: ఆ రోజు లేదా 2 రోజుల ముందు వరకు
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
                result, reason = "Missed", diagnose(scan, sym, h, l, c, v, i)
            else:
                result, reason = "Unknown", "No snapshot that day. Approx: " + diagnose(scan, sym, h, l, c, v, i)

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

print("---- Miss Report సారాంశం ----")
print("మొత్తం 15%+ movers:", len(out))
if len(out):
    print(out.groupby(["Scan", "Result"]).size().to_string())
    print("\nటాప్ మిస్డ్ కారణాలు:")
    print(out[out["Result"] != "Caught"]["Reason"].str.replace("No snapshot that day. Approx: ", "").str.replace(r"\(.*\)", "", regex=True).value_counts().head(8).to_string())
