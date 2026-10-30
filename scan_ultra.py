import os
import datetime
import numpy as np
import pandas as pd

MIN_PRICE = 50              # కనీస ధర
MIN_TRADED_VALUE = 10e7     # 20 రోజుల సగటు traded value కనీసం ₹10 కోట్లు
MIN_SCORE = 40              # దీని కంటే తక్కువ score ఉంటే జాబితాలో చూపం
MIN_ROWS = 70               # కనీసం ఇన్ని రోజుల data ఉండాలి
MAX_STOP_PCT = 8.0          # ఫైన్-ట్యూన్డ్ గరిష్ట స్టాప్‌లాస్ పరిమితి

# ---- Stop / Target (టెక్నికల్, అంచనా సంఖ్యలు) ----
ATR_N = 14                  # ATR కాలం
SWING_LOOKBACK = 30         # swing low కోసం గత రోజులు
ATR_BUFFER = 0.25           # swing low కింద ATR బఫర్
ATR_MIN_STOP = 1.0          # stop కనీసం ఇన్ని ATR దూరం
NO_RES_ATR = 3.0            # resistance లేకపోతే target = Entry + ఇన్ని ATR
MAX_TARGET_ATR = 6.0        # target గరిష్టం (1-5 రోజుల trade కి)
MIN_RR = 1.8                # కనీస Reward:Risk
WIDE_STOP_PCT = 8.0         # దీని కంటే stop దూరమైతే "Wide stop" హెచ్చరిక

# ---- Event score (అంచనా బరువులు) ----
EV_BOOST_MAIN = 5           # Order win / Acquisition / Buyback
EV_BOOST_DEAL = 3           # Bulk BUY / Block BUY
EV_BOOST_CAP = 8
EV_PEN_DEFAULT = -10        # Default/Insolvency
EV_PEN_DISRUPT = -5         # Disruption/Suspension
EV_PEN_AUDITOR = -3         # Auditor change

rejected = {"low_rr": 0, "wide_stop": 0}
rej_rows = []               # తిరస్కరించబడిన stocks (Excluded tab కోసం)


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

# ---------- Events & Surveillance ----------
EV = {}
SURV_MAP = {}

if os.path.exists("data/events.csv"):
    try:
        evdf = pd.read_csv("data/events.csv")
        for _, e in evdf.iterrows():
            k = str(e.get("symbol", "")).upper().replace(".NS", "").strip()
            cat = str(e.get("category", "")).strip()
            EV.setdefault(k, set()).add(cat)
            cat_upper = cat.upper()
            if "GSM" in cat_upper:
                SURV_MAP[k] = "GSM"
            elif "ASM" in cat_upper:
                SURV_MAP[k] = "ASM"
        print("events చదివాం, symbols:", len(EV))
    except Exception as ex:
        print("హెచ్చరిక: events.csv చదవడం కుదరలేదు:", ex)

if os.path.exists("data/surveillance.csv"):
    try:
        surv_df = pd.read_csv("data/surveillance.csv")
        for _, row in surv_df.iterrows():
            sym_clean = str(row.get("Symbol", "")).upper().replace(".NS", "").strip()
            stype = str(row.get("Type", "ASM")).upper().strip()
            if "GSM" in stype:
                SURV_MAP[sym_clean] = "GSM"
            else:
                SURV_MAP[sym_clean] = "ASM"
        print("ప్రత్యేక surveillance లిస్ట్ లోడ్ అయ్యింది, stocks:", len(SURV_MAP))
    except Exception as e:
        print("surveillance.csv చదవడం విఫలమైంది:", e)

groups = {sym: g.sort_values("Date").reset_index(drop=True) for sym, g in df.groupby("Symbol")}

# ---------- Pass 1: మాన్స్‌ఫీల్డ్ RS & లీడర్‌షిప్ డేటా లోడ్ చేయడం ----------
rs_data = {}
if os.path.exists("data/rs_rank.csv"):
    try:
        df_rs = pd.read_csv("data/rs_rank.csv")
        for _, r in df_rs.iterrows():
            sym_clean = str(r["Symbol"]).strip()
            rs_data[sym_clean] = {
                "RS": float(r.get("RS", 50.0)),
                "Mansfield_RS": float(r.get("Mansfield_RS", 50.0)),
                "Is_Leader": bool(r.get("Is_Leader", False))
            }
        print("మాన్స్‌ఫీల్డ్ RS ర్యాంకులు విజయవంతంగా అనుసంధానించబడ్డాయి:", len(rs_data))
    except Exception as e:
        print("rs_rank.csv లోడింగ్ లోపం:", e)


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
    if close / c[-3] - 1 > 0.10:
        return None

    res = h[-21:-1].max()          # 20 రోజుల రెసిస్టెన్స్
    high52 = h[-251:-1].max() if len(h) > 251 else h[:-1].max()
    vol_avg20 = v[-21:-1].mean()
    if vol_avg20 <= 0:
        return None
    vol_ratio = v[-1] / vol_avg20

    day_range = h[-1] - l[-1]
    close_pos = (close - l[-1]) / day_range if day_range > 0 else 0.5

    gap = bool(o[-1] > res and c[-2] <= res)
    above = close > res
    dist_res = (res / close - 1) * 100

    # range contraction & volume dry-up
    rng = (h - l) / c
    contr = rng[-11:-1].mean() / rng[-51:-1].mean() if len(rng) > 51 else 1.0
    dry = v[-6:-1].mean() / vol_avg20

    # ---------- Status ----------
    cp_need = 0.5 if (gap and close >= o[-1]) else 0.65
    if above:
        if close > res * 1.08:
            return None
        if vol_ratio >= 1.8 and close_pos >= cp_need:
            status = "Breakout"
        elif vol_ratio >= 1.2:
            status = "Near Miss"
        else:
            return None
    else:
        if 0 <= dist_res <= 1.5 and vol_ratio >= 1.8:
            status = "Near Miss"
        elif 0 <= dist_res <= 8.0 and contr < 1.15 and dry < 1.15:
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

    # ---------- STOP ----------
    seg_l = l[-SWING_LOOKBACK:]
    pivl = pd.Series(seg_l).rolling(5, center=True).min().values
    swing_lows = seg_l[(seg_l == pivl) & (seg_l < entry * 0.995)]
    if len(swing_lows) > 0:
        sw = float(swing_lows.max())
        sw_name = "swing low Rs %.1f" % sw
    else:
        sw = float(l[-10:].min())
        sw_name = "10-day low Rs %.1f" % sw

    tight_swing_stop = sw - ATR_BUFFER * atr
    tight_atr_stop = entry - ATR_MIN_STOP * atr
    stop_tight = min(tight_swing_stop, tight_atr_stop)

    whipsaw_buffer = sw * 0.0075
    safe_swing_stop = (sw - whipsaw_buffer) - (ATR_BUFFER * atr)
    safe_atr_stop = entry - (ATR_MIN_STOP + 0.25) * atr

    if safe_swing_stop <= safe_atr_stop:
        stop = safe_swing_stop
        stop_reason = "Below %s with 0.75%% dynamic buffer + %.2f ATR (ATR Rs %.1f)" % (sw_name, ATR_BUFFER, atr)
    else:
        stop = safe_atr_stop
        stop_reason = "%s is too close; safe stop set %.2f ATR below entry (ATR Rs %.1f)" % (
            sw_name, ATR_MIN_STOP + 0.25, atr)

    if stop >= entry:
        return None
    risk = entry - stop
    stop_pct = risk / entry * 100

    clean_sym = sym.upper().replace(".NS", "").strip()
    surv_status = SURV_MAP.get(clean_sym, "")

    # ---------- TARGET ----------
    hi250 = h[-251:] if len(h) >= 251 else h
    piv = pd.Series(hi250).rolling(11, center=True).max().values
    levels = hi250[hi250 == piv]
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

    if stop_pct > MAX_STOP_PCT:
        rejected["wide_stop"] += 1
        rej_rows.append({
            "Date": date_str, "Symbol": sym, "Status": status,
            "Close": round(close, 2), "Entry": round(entry, 2),
            "Stop": round(stop, 2), "StopTight": round(stop_tight, 2), "Target": round(target, 2),
            "StopDistPct": round(stop_pct, 2), "TargetPct": round(target_pct, 1),
            "RR": round(rr, 2), "Reason": f"Stop-loss too far ({stop_pct:.1f}%, limit {MAX_STOP_PCT:.1f}%)",
            "StopReason": stop_reason, "TargetReason": target_reason,
            "Surveillance": surv_status
        })
        return None

    if rr < MIN_RR:
        rejected["low_rr"] += 1
        rej_rows.append({
            "Date": date_str, "Symbol": sym, "Status": status,
            "Close": round(close, 2), "Entry": round(entry, 2),
            "Stop": round(stop, 2), "StopTight": round(stop_tight, 2), "Target": round(target, 2),
            "StopDistPct": round(stop_pct, 2), "TargetPct": round(target_pct, 1),
            "RR": round(rr, 2), "Reason": "Reward:Risk below 1:2",
            "StopReason": stop_reason, "TargetReason": target_reason,
            "Surveillance": surv_status
        })
        return None

    warns = []
    if stop_pct > WIDE_STOP_PCT:
        warns.append("Wide stop (%.1f%% away); position size should be small" % stop_pct)
    if surv_status:
        warns.append(f"Exchange {surv_status} Surveillance (100% Margin / Circuit risk)")

    # ---------- Events ----------
    cats = EV.get(clean_sym, set())
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

    # ---------- ట్రెండ్ టెంప్లేట్ (Minervini Rules) & RS ----------
    sma50 = c[-50:].mean()
    sma150 = c[-150:].mean() if len(c) >= 150 else sma50
    sma200 = c[-200:].mean() if len(c) >= 200 else sma150
    sma50_prev = c[-60:-10].mean()

    # మినెర్విని కీలక అమరిక: Close > 50 DMA > 150 DMA > 200 DMA
    trend_template_pass = bool(close > sma50 and sma50 > sma150 and sma150 > sma200)

    # మాన్స్‌ఫీల్డ్ RS విలువలను పొందడం
    stock_rs_info = rs_data.get(clean_sym, {"RS": 50.0, "Mansfield_RS": 50.0, "Is_Leader": False})
    stock_rs = stock_rs_info["RS"]
    is_true_leader = stock_rs_info["Is_Leader"]

    rs_ = []
    if status == "Breakout":
        rs_.append("Closed above 20-day high Rs %.1f on volume %.1fx average" % (res, vol_ratio))
        rs_.append("Closed in the top part of the day's range" if close_pos >= 0.7 else "Closed in the upper part")
    elif status == "Near Miss":
        rs_.append("At the 20-day high Rs %.1f; volume %.1fx average" % (res, vol_ratio))
    else:
        rs_.append("Tightening %.1f%% below 20-day high Rs %.1f" % (dist_res, res))
    
    if trend_template_pass:
        rs_.append("Trend Template Passed (50 > 150 > 200 DMA)")
    if is_true_leader:
        rs_.append("True Market Leader (Mansfield RS > 0 & RS >= 80)")
    if vol_ratio >= 2.5:
        rs_.append("Heavy Institutional Volume Breakout (%.1fx)" % vol_ratio)

    reasons = " | ".join(rs_)

    # ---------- స్కోర్ గణన (Enhanced Smart Scoring) ----------
    s = {"Breakout": 30, "Near Miss": 18, "Setup": 8}[status]
    if status != "Setup":
        s += clip01((vol_ratio - 1) / 2) * 10
        s += close_pos * 5
        if vol_ratio >= 2.5:  # సంస్థాగత వాల్యూమ్ గేట్ బూస్ట్
            s += 5
    s += clip01((1 - contr) / 0.5) * 10
    s += clip01((1 - dry) / 0.4) * 5

    # మాన్స్‌ఫీల్డ్ RS స్కోర్ అనుసంధానం (గరిష్టంగా 20 పాయింట్లు)
    s += (stock_rs / 100.0) * 15
    if is_true_leader:
        s += 5  # మార్కెట్ లీడర్‌కు అదనపు బూస్ట్

    # ట్రెండ్ టెంప్లేట్ పాయింట్లు
    if trend_template_pass:
        s += 8
    elif close > sma50:
        s += 4

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
        "StopTight": round(stop_tight, 2), "Target": round(target, 2),
        "StopDistPct": round(stop_pct, 2), "RR": round(rr, 2),
        "StopReason": stop_reason, "TargetReason": target_reason,
        "VolRatio": round(vol_ratio, 2),
        "TargetPct": round(target_pct, 1), "Resistance": round(res, 2),
        "High52": round(high52, 2), "Gap": "Yes" if gap else "",
        "Warning": warning, "Reasons": reasons,
        "Events": events_txt, "EventAdj": ev_adj,
        "Surveillance": surv_status,
        "ASM": "Yes" if surv_status == "ASM" else "",
        "GSM": "Yes" if surv_status == "GSM" else "",
        "RS": stock_rs,
        "IsLeader": "Yes" if is_true_leader else ""
    }


rows = []
for sym, g in groups.items():
    try:
        r = analyze(sym, g)
        if r is not None:
            rows.append(r)
    except Exception as e:
        print("దాటవేసాం", sym, e)

columns = ["Date", "Symbol", "Status", "Score", "Band", "Close", "Entry", "Stop", "StopTight", "Target",
           "StopDistPct", "RR", "StopReason", "TargetReason", "VolRatio", "TargetPct",
           "Resistance", "High52", "Gap", "Warning", "Reasons", "Events", "EventAdj",
           "Surveillance", "ASM", "GSM", "RS", "IsLeader"]
out = pd.DataFrame(rows, columns=columns)
out = out[out["Score"] >= MIN_SCORE].sort_values("Score", ascending=False)

rej_cols = ["Date", "Symbol", "Status", "Close", "Entry", "Stop", "StopTight", "Target", "StopDistPct",
            "TargetPct", "RR", "Reason", "StopReason", "TargetReason", "Surveillance"]
rej_out = pd.DataFrame(rej_rows, columns=rej_cols).sort_values("RR", ascending=False)

os.makedirs("data/history", exist_ok=True)
out.to_csv("data/ultra_short.csv", index=False)
out.to_csv("data/history/ultra_%s.csv" % date_str, index=False)
rej_out.to_csv("data/ultra_rejected.csv", index=False)
rej_out.to_csv("data/excluded_ultra.csv", index=False)
print("data తేదీ:", date_str)
print("Reward:Risk < 2.0 వల్ల తిరస్కరించినవి:", rejected["low_rr"])
print(f"Stop-loss > {MAX_STOP_PCT}% వల్ల తిరస్కరించినవి:", rejected["wide_stop"])
print("మొత్తం అల్ట్రా స్కాన్ ఫలితాలు:", len(out))
if len(out) > 0:
    print(out["Status"].value_counts().to_string())
    print(out.head(10)[["Symbol", "Status", "Score", "Band", "Entry", "Stop", "Target", "RR", "RS", "IsLeader"]].to_string(index=False))
