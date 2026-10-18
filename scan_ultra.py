import os
import datetime
import numpy as np
import pandas as pd

MIN_PRICE = 50             # కనీస ధర
MIN_TRADED_VALUE = 10e7    # 20 రోజుల సగటు traded value కనీసం ₹10 కోట్లు
MIN_SCORE = 40             # దీని కంటే తక్కువ score ఉంటే జాబితాలో చూపం
MIN_ROWS = 70              # కనీసం ఇన్ని రోజుల data ఉండాలి

# ---- Stop / Target (టెక్నికల్, అంచనా సంఖ్యలు) ----
ATR_N = 14                 # ATR కాలం
SWING_LOOKBACK = 30        # swing low కోసం గత రోజులు
ATR_BUFFER = 0.25          # swing low కింద ATR బఫర్
ATR_MIN_STOP = 1.0         # stop కనీసం ఇన్ని ATR దూరం
NO_RES_ATR = 3.0           # resistance లేకపోతే target = Entry + ఇన్ని ATR
MAX_TARGET_ATR = 6.0       # target గరిష్టం (1-5 రోజుల trade కి)
MIN_RR = 2.0               # కనీస Reward:Risk
WIDE_STOP_PCT = 8.0        # దీని కంటే stop దూరమైతే "Wide stop" హెచ్చరిక (తొలగింపు కాదు)

# ---- Event score (అంచనా బరువులు) ----
EV_BOOST_MAIN = 5           # Order win / Acquisition / Buyback
EV_BOOST_DEAL = 3           # Bulk BUY / Block BUY
EV_BOOST_CAP = 8
EV_PEN_DEFAULT = -10        # Default/Insolvency
EV_PEN_DISRUPT = -5         # Disruption/Suspension
EV_PEN_AUDITOR = -3         # Auditor change

rejected = {"low_rr": 0}
rej_rows = []               # RR వల్ల తొలగిన stocks (Excluded tab కోసం)


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

# ---------- Events (data/events.csv) ----------
EV = {}
if os.path.exists("data/events.csv"):
    try:
        evdf = pd.read_csv("data/events.csv")
        for _, e in evdf.iterrows():
            k = str(e.get("symbol", "")).upper().replace(".NS", "").strip()
            EV.setdefault(k, set()).add(str(e.get("category", "")).strip())
        print("events చదివాం, symbols:", len(EV))
    except Exception as ex:
        print("హెచ్చరిక: events.csv చదవడం కుదరలేదు:", ex)
else:
    print("హెచ్చరిక: data/events.csv లేదు, event score లేకుండా నడుస్తోంది.")

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
    cp_need = 0.5 if (gap and close >= o[-1]) else 0.65
    if above:
        if close > res * 1.08:
            return None            # ఇప్పటికే ఎక్కువ పైకి వెళ్ళింది
        if vol_ratio >= 1.8 and close_pos >= cp_need:
            status = "Breakout"
        elif vol_ratio >= 1.2:
            status = "Near Miss"
        else:
            return None
    else:
        if 0 <= dist_res <= 1.5 and vol_ratio >= 1.8:
            status = "Near Miss"
        elif 0 <= dist_res <= 10.0 and contr < 1.1 and dry < 1.15:
            status = "Setup"
        else:
            return None
    # ---------- Entry ----------
    entry = res * 1.002 if status == "Setup" else close

    # ---------- ATR (14 రోజులు) ----------
    pc = c[:-1]
    tr = np.maximum.reduce([h[1:] - l[1:], np.abs(h[1:] - pc), np.abs(l[1:] - pc)])
    atr = float(tr[-ATR_N:].mean())
    if atr <= 0:
        return None

    # ---------- STOP: swing low కింద (ATR బఫర్), కనీసం 1 ATR దూరం ----------
    seg_l = l[-SWING_LOOKBACK:]
    pivl = pd.Series(seg_l).rolling(5, center=True).min().values
    swing_lows = seg_l[(seg_l == pivl) & (seg_l < entry * 0.995)]
    if len(swing_lows) > 0:
        sw = float(swing_lows.max())          # entry కి దగ్గరగా కింద ఉన్న swing low
        sw_name = "swing low Rs %.1f" % sw
    else:
        sw = float(l[-10:].min())
        sw_name = "10-day low Rs %.1f" % sw
    swing_stop = sw - ATR_BUFFER * atr
    atr_stop = entry - ATR_MIN_STOP * atr
    if swing_stop <= atr_stop:
        stop = swing_stop
        stop_reason = "Below %s with %.2f ATR buffer (ATR Rs %.1f)" % (sw_name, ATR_BUFFER, atr)
    else:
        stop = atr_stop
        stop_reason = "%s is too close; stop set %.1f ATR below entry (ATR Rs %.1f)" % (
            sw_name, ATR_MIN_STOP, atr)
    if stop >= entry:
        return None
    risk = entry - stop
    stop_pct = risk / entry * 100

    # ---------- TARGET: పైన దగ్గరి నిజమైన resistance ----------
    hi250 = h[-251:]
    piv = pd.Series(hi250).rolling(11, center=True).max().values
    levels = hi250[hi250 == piv]         # swing highs
    levels = np.append(levels, high52)
    levels = levels[levels > entry * 1.02]
    cap_price = entry + MAX_TARGET_ATR * atr
    next_res = None
    if len(levels) > 0:
        lvl = float(levels.min())
        next_res = lvl
        lvl_name = "52-week high" if abs(lvl - high52) < 1e-9 else "swing high"
        if lvl > cap_price:
            target = cap_price
            target_reason = "Nearest resistance (%s Rs %.1f) is far; capped at %.0f ATR for a short trade" % (
                lvl_name, lvl, MAX_TARGET_ATR)
        else:
            target = lvl
            target_reason = "Nearest resistance: %s Rs %.1f (+%.1f%%)" % (lvl_name, lvl, (lvl / entry - 1) * 100)
    else:
        target = entry + NO_RES_ATR * atr
        target_reason = "No overhead resistance found; %.0f ATR projection (estimate)" % NO_RES_ATR
    target_pct = (target / entry - 1) * 100
    rr = (target - entry) / risk
    if rr < MIN_RR:
        rejected["low_rr"] += 1
        rej_rows.append({
            "Date": date_str, "Symbol": sym, "Status": status,
            "Close": round(close, 2), "Entry": round(entry, 2),
            "Stop": round(stop, 2), "Target": round(target, 2),
            "StopDistPct": round(stop_pct, 2), "TargetPct": round(target_pct, 1),
            "RR": round(rr, 2), "Reason": "Reward:Risk below 1:2",
            "StopReason": stop_reason, "TargetReason": target_reason,
        })
        return None

    warns = []
    if stop_pct > WIDE_STOP_PCT:
        warns.append("Wide stop (%.1f%% away); position size should be small" % stop_pct)

    # ---------- Events (Catalyst boost / penalty) ----------
    cats = EV.get(sym.upper().replace(".NS", ""), set())
    boost = 0
    pen = 0
    ev_names = []
    neg_names = []
    for cat in sorted(cats):
        cl = cat.lower()
        if cl.startswith("order win") or cl.startswith("acquisition") or cl.startswith("buyback"):
            boost += EV_BOOST_MAIN
            ev_names.append(cat)
        elif cl.startswith("bulk buy") or cl.startswith("block buy"):
            boost += EV_BOOST_DEAL
            ev_names.append(cat)
        elif cl.startswith("default"):
            pen += EV_PEN_DEFAULT
            neg_names.append(cat)
        elif cl.startswith("disruption"):
            pen += EV_PEN_DISRUPT
            neg_names.append(cat)
        elif cl.startswith("auditor"):
            pen += EV_PEN_AUDITOR
            neg_names.append(cat)
    boost = min(boost, EV_BOOST_CAP)
    ev_adj = boost + pen
    events_txt = ", ".join(ev_names + neg_names)
    if neg_names:
        warns.append("NSE event హెచ్చరిక: " + ", ".join(neg_names))
    warning = "; ".join(warns)

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
    if next_res is not None:
        rs_.append("Next resistance Rs %.1f (+%.1f%%)" % (next_res, (next_res / entry - 1) * 100))
    else:
        rs_.append("No major resistance overhead")
    if events_txt:
        rs_.append("NSE events (last 7 days): %s, score %+d" % (events_txt, ev_adj))
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
    s += ev_adj
    s = round(max(min(s, 100), 0), 1)

    band = "High Conviction" if s >= 80 else ("Good Setup" if s >= 65 else "Early Watch")

    return {
        "Date": date_str, "Symbol": sym, "Status": status, "Score": s, "Band": band,
        "Close": round(close, 2), "Entry": round(entry, 2), "Stop": round(stop, 2),
        "Target": round(target, 2), "StopDistPct": round(stop_pct, 2),
        "RR": round(rr, 2), "StopReason": stop_reason, "TargetReason": target_reason,
        "VolRatio": round(vol_ratio, 2),
        "TargetPct": round(target_pct, 1), "Resistance": round(res, 2),
        "High52": round(high52, 2), "Gap": "Yes" if gap else "",
        "Warning": warning, "Reasons": reasons,
        "Events": events_txt, "EventAdj": ev_adj,
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
           "StopDistPct", "RR", "StopReason", "TargetReason", "VolRatio", "TargetPct",
           "Resistance", "High52", "Gap", "Warning", "Reasons", "Events", "EventAdj"]
out = pd.DataFrame(rows, columns=columns)
out = out[out["Score"] >= MIN_SCORE].sort_values("Score", ascending=False)

rej_cols = ["Date", "Symbol", "Status", "Close", "Entry", "Stop", "Target", "StopDistPct",
            "TargetPct", "RR", "Reason", "StopReason", "TargetReason"]
rej_out = pd.DataFrame(rej_rows, columns=rej_cols).sort_values("RR", ascending=False)

os.makedirs("data/history", exist_ok=True)
out.to_csv("data/ultra_short.csv", index=False)                       # తాజా ఫలితం
out.to_csv("data/history/ultra_%s.csv" % date_str, index=False)       # రోజువారీ snapshot (Miss Report కి)
rej_out.to_csv("data/ultra_rejected.csv", index=False)                # RR వల్ల తొలగినవి (Excluded tab కి)

print("data తేదీ:", date_str)
print("Reward:Risk %.0f కంటే తక్కువ అని తొలగినవి:" % MIN_RR, rejected["low_rr"])
print("మొత్తం ఫలితాలు:", len(out))
if len(out) > 0:
    print(out["Status"].value_counts().to_string())
    print(out.head(10)[["Symbol", "Status", "Score", "Entry", "Stop", "Target", "RR", "Warning"]].to_string(index=False))
if len(rej_out) > 0:
    print("RR తొలగినవి (టాప్ 5, RR ఎక్కువ నుంచి):")
    print(rej_out.head(5)[["Symbol", "Status", "Entry", "Stop", "Target", "RR"]].to_string(index=False))
