import io
import os
import time
import requests
import numpy as np
import pandas as pd

MIN_DAYS = 15             # 25 నుండి 15 కి తగ్గించాం (తొలి 2-3 వారాల మొమెంటం మిస్ కాకుండా)
MAX_DAYS = 130            # సుమారు 6 నెలల లోపు IPOలు
MIN_TURNOVER = 2e7        # రోజుకు సగటున Rs 2 కోట్లు Traded Value

# ---- Stop / Target (టెక్నికల్) ----
ATR_N = 14
SWING_LOOKBACK = 30
ATR_BUFFER = 0.3
ATR_MIN_STOP = 1.5
NO_RES_ATR = 5.0          # 4.0 నుండి 5.0 కి పెంచాం (ఆల్-టైమ్ హై వద్ద సరైన టార్గెట్ ప్రొజెక్షన్ కోసం)
MAX_TARGET_ATR = 10.0
MIN_RR = 1.5              # 2.0 నుండి 1.5 కి సడలించాం (మంచి IPO రన్నర్స్ Excluded లోకి వెళ్లకుండా కాపాడుతుంది)
WIDE_STOP_PCT = 12.0

# ---------- Surveillance (ASM / GSM) లోకల్ మ్యాపింగ్ ----------
SURV_MAP = {}
if os.path.exists("data/surveillance.csv"):
    try:
        surv_df = pd.read_csv("data/surveillance.csv")
        for _, row in surv_df.iterrows():
            sym_clean = str(row.get("Symbol", "")).upper().replace(".NS", "").strip()
            stype = str(row.get("Type", "ASM")).upper().strip()
            SURV_MAP[sym_clean] = "GSM" if "GSM" in stype else "ASM"
        print("NewListings: data/surveillance.csv లోడ్ అయ్యింది, stocks:", len(SURV_MAP))
    except Exception as e:
        print("surveillance.csv చదవడం విఫలమైంది:", e)

def get_surv(sym):
    s_clean = sym.upper().replace(".NS", "").strip()
    return SURV_MAP.get(s_clean, "")

# ---------- ధర data ----------
px = pd.read_csv("data/prices.csv.gz", parse_dates=["Date"])
last_date = px["Date"].max()
date_str = last_date.strftime("%Y-%m-%d")

nifty = None
try:
    if os.path.exists("data/index.csv"):
        idx = pd.read_csv("data/index.csv", parse_dates=["Date"])
        nifty = idx[idx["Symbol"] == "NIFTY50"].set_index("Date")["Close"].sort_index()
except Exception as e:
    pass

rows = []
rej_rows = []
removed = []
rejected = {"low_rr": 0}

for sym, g in px.groupby("Symbol"):
    g = g.sort_values("Date").dropna(subset=["Close"])
    n = len(g)
    if n < MIN_DAYS or n > MAX_DAYS:
        continue
    if g["Date"].iloc[-1] < last_date:
        continue
        
    c = g["Close"].values
    h = g["High"].values
    l = g["Low"].values
    v = g["Volume"].values

    turnover = (c[-min(20, n):] * v[-min(20, n):]).mean()
    if turnover < MIN_TURNOVER:
        continue

    score = 0
    why = []
    
    # 20-DMA Rule
    if n >= 20:
        sma20 = c[-20:].mean()
        if c[-1] > sma20:
            score += 20
            why.append("Above 20-day average")
    else:
        if c[-1] > c.mean():
            score += 20
            why.append("Above average price")

    # 50-DMA Rule
    if n >= 50:
        sma50 = c[-50:].mean()
        sma20 = c[-20:].mean()
        if sma20 > sma50:
            score += 15
            why.append("20-day above 50-day")

    # High / All-time High Distance
    hi = h.max()
    from_high = (hi - c[-1]) / hi * 100
    if from_high <= 8:
        score += 25
        why.append("Near All-Time High (<8%)")
    elif from_high <= 15:
        score += 15
        why.append("Within 15% of high")

    # Volume Surge Logic
    lookback_v = min(n - 5, 30)
    if lookback_v > 5:
        v_base = np.median(v[-lookback_v:-5])
        if v_base > 0 and (v[-5:].mean() / v_base) >= 1.25:
            score += 15
            why.append("Volume rising on base")

    # Relative strength vs Nifty
    lookback_r = min(20, n - 1)
    r_stock = (c[-1] / c[-lookback_r - 1] - 1) * 100
    if nifty is not None and len(nifty) > 0:
        try:
            n_then = nifty.asof(g["Date"].iloc[-lookback_r - 1])
            n_now = nifty.iloc[-1]
            n_ret = (n_now / n_then - 1) * 100
            if r_stock > n_ret:
                score += 15
                why.append("Beating Nifty")
        except Exception:
            pass

    # Above Listing-day close
    if c[-1] >= c[0]:
        score += 15
        why.append("Above listing-day close")

    score = min(score, 79)   # హిస్టరీ తక్కువ కాబట్టి గరిష్టంగా 79
    if score < 45:           # 50 నుండి 45 కి సడలించాం
        continue
        
    band = "Good Setup" if score >= 60 else "Early Watch"

    # Surveillance Filter
    surv_val = get_surv(sym)
    if surv_val in ["ASM", "GSM"]:
        removed.append(f"{sym} ({surv_val})")
        continue

    entry = float(c[-1])

    # ---------- ATR (14 రోజులు) ----------
    if len(c) > ATR_N:
        pc = c[:-1]
        tr = np.maximum.reduce([h[1:] - l[1:], np.abs(h[1:] - pc), np.abs(l[1:] - pc)])
        atr = float(tr[-ATR_N:].mean())
    else:
        atr = float((h - l).mean())
        
    if atr <= 0:
        continue

    # ---------- STOP: Swing Low కింద ----------
    look_low = min(SWING_LOOKBACK, n)
    seg_l = l[-look_low:]
    pivl = pd.Series(seg_l).rolling(5, center=True).min().values
    swing_lows = seg_l[(seg_l == pivl) & (seg_l < entry * 0.995)]
    
    if len(swing_lows) > 0:
        sw = float(swing_lows.max())
        sw_name = "swing low Rs %.1f" % sw
    else:
        sw = float(l[-min(10, n):].min())
        sw_name = "recent low Rs %.1f" % sw
        
    swing_stop = sw - ATR_BUFFER * atr
    atr_stop = entry - ATR_MIN_STOP * atr
    
    if swing_stop <= atr_stop:
        stop = swing_stop
        stop_reason = "Below %s with %.1f ATR buffer (ATR Rs %.1f)" % (sw_name, ATR_BUFFER, atr)
    else:
        stop = atr_stop
        stop_reason = "%s is too close; stop set %.1f ATR below entry" % (sw_name, ATR_MIN_STOP)
        
    risk = entry - stop
    if risk <= 0:
        continue
    stop_pct = risk / entry * 100

    # ---------- TARGET: Resistance Levels ----------
    hi_len = len(h)
    pivh = pd.Series(h).rolling(min(11, max(3, hi_len // 3)), center=True).max().values
    levels = np.append(h[h == pivh], hi)
    levels = levels[levels > entry * 1.02]
    cap_price = entry + MAX_TARGET_ATR * atr
    
    if len(levels) > 0:
        lvl = float(levels.min())
        lvl_name = "post-listing high" if abs(lvl - hi) < 1e-9 else "swing high"
        if lvl > cap_price:
            target = cap_price
            target_reason = "Resistance far; capped at %.0f ATR" % MAX_TARGET_ATR
        else:
            target = lvl
            target_reason = "Nearest resistance: %s Rs %.1f (+%.1f%%)" % (lvl_name, lvl, (lvl / entry - 1) * 100)
    else:
        target = entry + NO_RES_ATR * atr
        target_reason = "At/near post-listing high, no resistance; %.0f ATR projection" % NO_RES_ATR
        
    rr = (target - entry) / risk
    
    if rr < MIN_RR:
        rejected["low_rr"] += 1
        rej_rows.append({
            "Date": date_str, "Symbol": sym, "Score": score, "Band": band,
            "DataDays": n, "Entry": round(entry, 2), "Stop": round(stop, 2),
            "Target": round(target, 2), "StopDistPct": round(stop_pct, 2),
            "TargetPct": round((target / entry - 1) * 100, 1),
            "RR": round(rr, 2), "Reason": f"Reward:Risk below 1:{MIN_RR}",
            "StopReason": stop_reason, "TargetReason": target_reason,
        })
        continue

    warn = "Low history (%d days)" % n
    if stop_pct > WIDE_STOP_PCT:
        warn += "; Wide stop (%.1f%% away)" % stop_pct

    rows.append({
        "Symbol": sym,
        "Score": score,
        "Band": band,
        "DataDays": n,
        "ListedOn": g["Date"].iloc[0].strftime("%Y-%m-%d"),
        "ChangeSinceListing%": round((c[-1] / c[0] - 1) * 100, 1),
        "Return20d%": round(r_stock, 1),
        "FromHigh%": round(from_high, 1),
        "Entry": round(entry, 2),
        "Stop": round(stop, 2),
        "Target": round(target, 2),
        "RiskPct": round(stop_pct, 1),
        "RR": round(rr, 2),
        "StopReason": stop_reason,
        "TargetReason": target_reason,
        "Why": "; ".join(why),
        "Warning": warn,
        "Surveillance": surv_val,
        "ASM": "Yes" if surv_val == "ASM" else "",
        "GSM": "Yes" if surv_val == "GSM" else ""
    })

cols = ["Symbol", "Score", "Band", "DataDays", "ListedOn", "ChangeSinceListing%",
        "Return20d%", "FromHigh%", "Entry", "Stop", "Target", "RiskPct", "RR",
        "StopReason", "TargetReason", "Why", "Warning", "Surveillance", "ASM", "GSM"]

out = pd.DataFrame(rows, columns=cols)
if len(out) > 0:
    out = out.sort_values("Score", ascending=False)

rej_cols = ["Date", "Symbol", "Score", "Band", "DataDays", "Entry", "Stop", "Target",
            "StopDistPct", "TargetPct", "RR", "Reason", "StopReason", "TargetReason"]
rej_out = pd.DataFrame(rej_rows, columns=rej_cols)
if len(rej_out) > 0:
    rej_out = rej_out.sort_values("RR", ascending=False)

os.makedirs("data", exist_ok=True)
out.to_csv("data/newlistings.csv", index=False)
rej_out.to_csv("data/newlistings_rejected.csv", index=False)
rej_out.to_csv("data/excluded_newlistings.csv", index=False)

print("---- సారాంశం ----")
print("పాస్ అయిన New Listings సంఖ్య:", len(out))
print("RR తక్కువని తొలగించినవి:", rejected["low_rr"])
print("ASM/GSM సర్వైలెన్స్ తొలగింపులు:", len(removed))
