import os
import datetime
import numpy as np
import pandas as pd

# ================= మీరు మార్చవలసిన సంఖ్య =================
CAPITAL = 100000   # <-- మీ నిజమైన capital ఇక్కడ మార్చండి (Step C లో)
# ==========================================================

RISK_PCT = 0.01            # ప్రతి trade కి capital లో 1% risk
MIN_PRICE = 50             # కనీస ధర
MIN_TRADED_VALUE = 10e7    # 20 రోజుల సగటు traded value కనీసం ₹10 కోట్లు
MIN_STOP_PCT = 2.0         # stop కనీస దూరం %
MAX_STOP_PCT = 6.0         # stop గరిష్ట దూరం %
MIN_TARGET_PCT = 15.0      # కనీస target %
MIN_SCORE = 40             # దీని కంటే తక్కువ score ఉంటే జాబితాలో చూపం
MIN_ROWS = 70              # కనీసం ఇన్ని రోజుల data ఉండాలి


def clip01(x):
    return float(min(max(x, 0.0), 1.0))


# ---------- data చదవడం ----------
df = pd.read_csv("data/prices.csv.gz", parse_dates=["Date"])
df = df.dropna(subset=["Open", "High", "Low", "Close", "Volume"])
last_date = df["Date"].max()
date_str = last_date.strftime("%Y-%m-%d")

# data అసంపూర్ణ candle తో ఉందేమో హెచ్చరిక (భారత సమయం)
ist = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=5, minutes=30)
if last_date.date() == ist.date() and (ist.hour, ist.minute) < (15, 45):
    print("హెచ్చరిక: market ఇంకా మూసి ఉండకపోవచ్చు, ఈ రోజు candle అసంపూర్ణం కావచ్చు.")

groups = {sym: g.sort_values("Date").reset_index(drop=True) for sym, g in df.groupby("Symbol")}

# ---------- Pass 1: 63 రోజుల relative strength (అన్ని stocks తో ర్యాంక్) ----------
ret63 = {}
for sym, g in groups.items():
    if len(g) > 64 and g["Date"].iloc[-1] == last_date:
        cc = g["Close"].values
        ret63[sym] = cc[-1] / cc[-64] - 1
rs_rank = pd.Series(ret63).rank(pct=True)


# ---------- Pass 2: ఒక్కో stock విశ్లేషణ ----------
def analyze(sym, g):
    if len(g) < MIN_ROWS or g["Date"].iloc[-1] != last_date:
        return None

    o = g["Open"].values
    h = g["High"].values
    l = g["Low"].values
    c = g["Close"].values
    v = g["Volume"].values.astype(float)
    close = c[-1]

    # Universe filters
    if close < MIN_PRICE:
        return None
    if (c[-20:] * v[-20:]).mean() < MIN_TRADED_VALUE:
        return None
    # 2 రోజుల్లో 10%+ పెరిగినవి తొలగింపు
    if close / c[-3] - 1 > 0.10:
        return None

    res = h[-21:-1].max()          # resistance = నిన్నటి వరకు 20 రోజుల high
    high52 = h[-251:-1].max()      # 52 వారాల high (ఈ రోజు మినహా)
    vol_avg20 = v[-21:-1].mean()
    if vol_avg20 <= 0:
        return None
    vol_ratio = v[-1] / vol_avg20

    day_range = h[-1] - l[-1]
    close_pos = (close - l[-1]) / day_range if day_range > 0 else 0.5

    # gap-up breakout: నిన్న resistance కింద close, ఈ రోజు resistance పైన open
    gap = bool(o[-1] > res and c[-2] <= res)

    above = close > res
    dist_res = (res / close - 1) * 100   # + అంటే resistance పైన ఉంది

    # range contraction మరియు volume dry-up (ఈ రోజు మినహా)
    rng = (h - l) / c
    contr = rng[-11:-1].mean() / rng[-51:-1].mean()
    dry = v[-6:-1].mean() / vol_avg20

    # ---------- Status ----------
    cp_need = 0.5 if (gap and close >= o[-1]) else 0.7
    if above:
        if close > res * 1.08:
            return None            # ఇప్పటికే ఎక్కువ పైకి వెళ్ళింది
        if vol_ratio >= 2 and close_pos >= cp_need:
            status = "Breakout"
        elif vol_ratio >= 1.2:
            status = "Near Miss"
        else:
            return None
    else:
        if 0 <= dist_res <= 1 and vol_ratio >= 2:
            status = "Near Miss"
        elif 0 <= dist_res <= 5 and contr < 1.0 and dry < 1.0:
            status = "Setup"
        else:
            return None

    # ---------- Entry / Stop / Target ----------
    entry = res * 1.002 if status == "Setup" else close
    stop = l[-5:].min() * 0.999          # గత 5 రోజుల low
    risk = entry - stop
    stop_pct = risk / entry * 100
    if stop_pct < MIN_STOP_PCT:          # stop మరీ దగ్గరగా ఉంటే 2% కి పెంచుతాం
        stop = entry * (1 - MIN_STOP_PCT / 100)
        risk = entry - stop
        stop_pct = MIN_STOP_PCT
    if stop_pct > MAX_STOP_PCT:          # stop మరీ దూరం -> తొలగింపు
        return None

    target = max(entry * (1 + MIN_TARGET_PCT / 100), entry + 2 * risk)
    target_pct = (target / entry - 1) * 100
    qty = int(max(min(CAPITAL * RISK_PCT / risk, CAPITAL / entry), 0))

    # ---------- 15% లోపు resistance హెచ్చరిక ----------
    hi250 = h[-251:]
    piv = pd.Series(hi250).rolling(11, center=True).max().values
    levels = hi250[hi250 == piv]         # swing highs
    if entry * 1.03 < high52 <= entry * 1.15:
        levels = np.append(levels, high52)
    levels = levels[(levels > entry * 1.03) & (levels <= entry * 1.15)]
    warning = ""
    penalty = 0
    if len(levels) > 0:
        lvl = levels.min()
        warning = "పైన %.1f%% వద్ద పాత high (Rs %.1f), 15%% target కి అడ్డు కావచ్చు" % (
            (lvl / entry - 1) * 100, lvl)
        penalty = 10

    # ---------- Technical reasons (website కోసం, English) ----------
    sma50 = c[-50:].mean()
    sma50_prev = c[-60:-10].mean()
    rs_ = []
    if status == "Breakout":
        rs_.append("Closed above 20-day high Rs %.1f on volume %.1fx average" % (res, vol_ratio))
        rs_.append("Closed in the top %.0f%% of the day's range" % ((1 - close_pos) * 100 + 0.0001) if close_pos >= 0.7 else "Closed in the upper part of the day's range")
    elif status == "Near Miss":
        rs_.append("At the 20-day high Rs %.1f; volume %.1fx average" % (res, vol_ratio))
    else:
        rs_.append("Tightening %.1f%% below 20-day high Rs %.1f" % (dist_res, res))
    if gap:
        rs_.append("Gap-up open above resistance")
    if contr < 1.0:
        rs_.append("Daily range is contracting (price is coiling)")
    if dry < 1.0:
        rs_.append("Volume dried up in the last 5 days (quiet before the move)")
    if close > sma50:
        rs_.append("Price above 50-day average")
    if len(c) >= 200 and close > c[-200:].mean():
        rs_.append("Price above 200-day average")
    if sma50 > sma50_prev:
        rs_.append("50-day average is rising")
    if len(levels) > 0:
        lv_ = levels.min()
        rs_.append("Next resistance Rs %.1f (+%.1f%%)" % (lv_, (lv_ / entry - 1) * 100))
    else:
        rs_.append("No major resistance within 15%")
    reasons = " | ".join(rs_)

    # ---------- Score (100 లో, నా అంచనా బరువులు) ----------
    s = {"Breakout": 30, "Near Miss": 18, "Setup": 8}[status]
    if status != "Setup":
        s += clip01((vol_ratio - 1) / 2) * 10
        s += close_pos * 5
    s += clip01((1 - contr) / 0.5) * 15
    s += clip01((1 - dry) / 0.4) * 10
    s += float(rs_rank.get(sym, 0.0)) * 15
    if close > sma50:
        s += 5
    if len(c) >= 200 and close > c[-200:].mean():
        s += 3
    if sma50 > sma50_prev:
        s += 2
    d52 = (high52 / close - 1) * 100
    if d52 <= 5:
        s += 5
    elif d52 <= 10:
        s += 2
    s -= penalty
    s = round(max(min(s, 100), 0), 1)

    band = "High Conviction" if s >= 80 else ("Good Setup" if s >= 65 else "Early Watch")

    return {
        "Date": date_str, "Symbol": sym, "Status": status, "Score": s, "Band": band,
        "Close": round(close, 2), "Entry": round(entry, 2), "Stop": round(stop, 2),
        "Target": round(target, 2), "StopDistPct": round(stop_pct, 2), "Qty": qty,
        "VolRatio": round(vol_ratio, 2),
        "TargetPct": round(target_pct, 1), "Resistance": round(res, 2),
        "High52": round(high52, 2), "Gap": "Yes" if gap else "",
        "Warning": warning, "Reasons": reasons,
    }


rows = []
for sym, g in groups.items():
    try:
        r = analyze(sym, g)
        if r is not None:
            rows.append(r)
    except Exception as e:
        print("దాటవేసాం", sym, e)

columns = ["Date", "Symbol", "Status", "Score", "Band", "Close", "Entry", "Stop", "Target",
           "StopDistPct", "Qty", "VolRatio", "TargetPct", "Resistance", "High52", "Gap", "Warning",
           "Reasons"]
out = pd.DataFrame(rows, columns=columns)
out = out[out["Score"] >= MIN_SCORE].sort_values("Score", ascending=False)

os.makedirs("data/history", exist_ok=True)
out.to_csv("data/ultra_short.csv", index=False)                       # తాజా ఫలితం
out.to_csv("data/history/ultra_%s.csv" % date_str, index=False)       # రోజువారీ snapshot (Miss Report కి)

print("data తేదీ:", date_str)
print("మొత్తం ఫలితాలు:", len(out))
if len(out) > 0:
    print(out["Status"].value_counts().to_string())
    print(out.head(10)[["Symbol", "Status", "Score", "Entry", "Stop", "Target", "Warning"]].to_string(index=False))
