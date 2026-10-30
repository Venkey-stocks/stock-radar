import os
import datetime
import numpy as np
import pandas as pd

MIN_PRICE = 50
MIN_TRADED_VALUE = 10e7     # 20 రోజుల సగటు traded value కనీసం Rs 10 కోట్లు
MIN_SCORE = 25              # మార్కెట్ కన్సాలిడేషన్ సర్దుబాటు స్కోర్
MIN_ROWS = 210              # 200-రోజుల average కి కనీసం ఇన్ని రోజుల data
MAX_STOP_PCT = 8.0          # ఫైన్-ట్యూన్డ్ గరిష్ట స్టాప్‌లాస్ పరిమితి (8.0%)

# ---- Stop / Target (టెక్నికల్, అంచనా సంఖ్యలు) ----
ATR_N = 14                  # ATR కాలం
SWING_LOOKBACK = 40         # swing low కోసం గత రోజులు
ATR_BUFFER = 0.3            # swing low కింద ATR బఫర్
ATR_MIN_STOP = 1.5          # stop కనీసం ఇన్ని ATR దూరం
NO_RES_ATR = 5.0            # resistance లేకపోతే target = Entry + ఇన్ని ATR
NO_RES_ATR_HP = 7.0         # High Potential కి
MAX_TARGET_ATR = 10.0       # target గరిష్టం
MIN_RR = 1.4                # కనీస Reward:Risk (క్వాలిటీ గేట్)
WIDE_STOP_PCT = 10.0        # దీని కంటే stop దూరమైతే "Wide stop" హెచ్చరిక

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


def rsi14(c):
    s = pd.Series(c)
    d = s.diff()
    up = d.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    rs = up / dn.replace(0, np.nan)
    r = (100 - 100 / (1 + rs)).iloc[-1]
    return 50.0 if np.isnan(r) else float(r)


def macd_hist(c):
    s = pd.Series(c)
    m = s.ewm(span=12, adjust=False).mean() - s.ewm(span=26, adjust=False).mean()
    sig = m.ewm(span=9, adjust=False).mean()
    return float((m - sig).iloc[-1])


def adx14(h, l, c):
    hh, ll, cc = pd.Series(h), pd.Series(l), pd.Series(c)
    up = hh.diff()
    down = -ll.diff()
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    pc = cc.shift(1)
    tr = pd.concat([hh - ll, (hh - pc).abs(), (ll - pc).abs()], axis=1).max(axis=1)
    a = 1 / 14
    atr = tr.ewm(alpha=a, adjust=False).mean()
    pdi = 100 * pd.Series(plus_dm).ewm(alpha=a, adjust=False).mean() / atr
    mdi = 100 * pd.Series(minus_dm).ewm(alpha=a, adjust=False).mean() / atr
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    adx = dx.ewm(alpha=a, adjust=False).mean()
    last, prev = adx.iloc[-1], adx.iloc[-4]
    if np.isnan(last) or np.isnan(prev):
        return 0.0, 0.0
    return float(last), float(prev)


def weekly_bullish(dates, c):
    w = pd.Series(c, index=pd.DatetimeIndex(dates)).resample("W").last().dropna()
    if len(w) < 15:
        return False
    sma = w.rolling(10).mean()
    return bool(w.iloc[-1] > sma.iloc[-1] and sma.iloc[-1] > sma.iloc[-5])


def camarilla_r4(dates, h, l, c):
    w = pd.DataFrame({"H": h, "L": l, "C": c}, index=pd.DatetimeIndex(dates))
    w = w.resample("W").agg({"H": "max", "L": "min", "C": "last"}).dropna()
    if len(w) < 3:
        return None
    p = w.iloc[-2]
    r4 = float(p["C"] + (p["H"] - p["L"]) * 1.1 / 2)
    return r4, float(p["H"]), float(p["L"]), float(p["C"])


# ---------- data చదవడం ----------
df = pd.read_csv("data/prices.csv.gz", parse_dates=["Date"])
df = df.dropna(subset=["Open", "High", "Low", "Close", "Volume"])
last_date = df["Date"].max()
date_str = last_date.strftime("%Y-%m-%d")

ist = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=5, minutes=30)
if last_date.date() == ist.date() and (ist.hour, ist.minute) < (15, 45):
    print("హెచ్చరిక: market ఇంకా మూసి ఉండకపోవచ్చు, ఈ రోజు candle అసంపూర్ణం కావచ్చు.")

# ---------- Index data (Nifty) ----------
idx = {}
if os.path.exists("data/index.csv"):
    ix = pd.read_csv("data/index.csv", parse_dates=["Date"])
    for name, gi in ix.groupby("Symbol"):
        arr = gi.sort_values("Date")["Close"].dropna().values
        if len(arr) > 64:
            idx[name] = arr
else:
    print("హెచ్చరిక: data/index.csv లేదు, Nifty పోలిక లేకుండా నడుస్తోంది.")

main_name = "NIFTY500" if "NIFTY500" in idx else ("NIFTY50" if "NIFTY50" in idx else None)
main_ret = None
market_ok = True
if main_name:
    a = idx[main_name]
    main_ret = a[-1] / a[-64] - 1
    market_ok = bool(a[-1] > a[-50:].mean())
n50_ret = None
if "NIFTY50" in idx:
    a = idx["NIFTY50"]
    n50_ret = a[-1] / a[-64] - 1
print("పోలిక index:", main_name, "| market 50-రోజుల average పైన:", market_ok)

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


def analyze(sym, g):
    if len(g) < MIN_ROWS or g["Date"].iloc[-1] != last_date:
        return None
    o = g["Open"].values
    h = g["High"].values
    l = g["Low"].values
    c = g["Close"].values
    v = g["Volume"].values.astype(float)
    close = c[-1]

    # Universe
    if close < MIN_PRICE:
        return None
    if (c[-20:] * v[-20:]).mean() < MIN_TRADED_VALUE:
        return None

    # Trend Checks
    sma20 = c[-20:].mean()
    sma50 = c[-50:].mean()
    sma150 = c[-150:].mean() if len(c) >= 150 else sma50
    sma200 = c[-200:].mean()
    sma50_prev = c[-60:-10].mean()

    trend_ok = (close > sma50 and sma50 > sma50_prev) or (close > sma200) or (close > sma20 * 1.02 and close > sma50)
    if not trend_ok:
        return None

    ext = (close / sma20 - 1) * 100
    if ext > 18:
        return None
    r63 = c[-1] / c[-64] - 1
    if main_ret is not None and r63 <= (main_ret - 0.05):
        return None

    vol_avg20 = v[-21:-1].mean()
    if vol_avg20 <= 0:
        return None
    vol_ratio = v[-1] / vol_avg20
    dry = v[-6:-1].mean() / vol_avg20

    # ---------- Setup ----------
    status = None
    level = None
    setup_kind = ""
    base_w = 0
    cam_info = None
    for N in (15, 25, 40):                 # 3, 5, 8 వారాల base
        bh = h[-N - 1:-1].max()
        bl = l[-N - 1:-1].min()
        depth = (bh - bl) / bh
        if depth > 0.20:
            continue
        if close > bh and close < bh * 1.05 and vol_ratio >= 1.5:
            status, level, setup_kind = "Breakout", bh, "Base %d వారాలు" % (N // 5)
            base_w = N // 5
            break
        if status is None and close <= bh and (bh / close - 1) <= 0.02 and dry < 1.0:
            status, level, setup_kind = "Near Miss", bh, "Base %d వారాలు" % (N // 5)
            base_w = N // 5
    if status is None:
        low5 = l[-5:].min()
        touched = (low5 <= sma20 * 1.02) or (low5 <= sma50 * 1.02)
        if touched and ext <= 6 and close > c[-2] and close > o[-1] and v[-1] > v[-2] and dry < 1.0:
            status, setup_kind = "Pullback", "Pullback"
    if status is None:
        cam = camarilla_r4(g["Date"].values[-30:], h[-30:], l[-30:], c[-30:])
        if cam is not None:
            r4 = cam[0]
            if close > r4 and close <= r4 * 1.05 and vol_ratio >= 1.2 and close > o[-1] and close > c[-2]:
                status, level, setup_kind = "Breakout", r4, "Camarilla R4"
                cam_info = cam
    if status is None:
        return None

    # ---------- Entry ----------
    entry = close if status in ("Breakout", "Pullback") else level * 1.002

    # ---------- ATR ----------
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
        stop_reason = "Below %s with 0.75%% dynamic buffer + %.1f ATR (ATR Rs %.1f)" % (sw_name, ATR_BUFFER, atr)
    else:
        stop = safe_atr_stop
        stop_reason = "%s is too close; safe stop set %.1f ATR below entry (ATR Rs %.1f)" % (
            sw_name, ATR_MIN_STOP + 0.25, atr)

    if stop >= entry:
        return None
    risk = entry - stop
    stop_pct = risk / entry * 100

    # ---------- Resistance Levels ----------
    high52 = h[-251:-1].max()
    hi250 = h[-251:]
    piv = pd.Series(hi250).rolling(11, center=True).max().values
    all_lv = np.append(hi250[hi250 == piv], high52)
    up_lv = all_lv[all_lv > entry * 1.02]
    levels = up_lv[(up_lv > entry * 1.03) & (up_lv <= entry * 1.15)]

    # ---------- Indicators & RS Data ----------
    rsi = rsi14(c)
    mh = macd_hist(c)
    adx, adx_prev = adx14(h, l, c)
    wk = weekly_bullish(g["Date"].values, c)
    d52 = (high52 / close - 1) * 100

    clean_sym = sym.upper().replace(".NS", "").strip()
    stock_rs_info = rs_data.get(clean_sym, {"RS": 50.0, "Mansfield_RS": 50.0, "Is_Leader": False})
    stock_rs = stock_rs_info["RS"]
    is_true_leader = stock_rs_info["Is_Leader"]

    # ---------- High Potential Check ----------
    tight_base = False
    for N in (30, 40, 60):
        if (h[-N:].max() - l[-N:].min()) / h[-N:].max() <= 0.22:
            tight_base = True
    chg = np.diff(c[-21:])
    vv = v[-20:]
    up_vol = vv[chg > 0].sum()
    dn_vol = vv[chg <= 0].sum()
    acc = bool(dn_vol > 0 and up_vol > 1.2 * dn_vol)
    near52 = d52 <= 10
    no_res = len(levels) == 0
    met = []
    if near52:
        met.append("52w high దగ్గర")
    if acc:
        met.append("Accumulation volume")
    if no_res:
        met.append("పైన resistance లేదు")
    is_hp = bool((stock_rs >= 80 or is_true_leader) and tight_base and len(met) >= 2)

    # ---------- TARGET ----------
    cap_price = entry + MAX_TARGET_ATR * atr
    next_res = None
    if len(up_lv) > 0:
        lvl = float(up_lv.min())
        next_res = lvl
        lvl_name = "52-week high" if abs(lvl - high52) < 1e-9 else "swing high"
        if lvl > cap_price:
            target = cap_price
            target_reason = "Nearest resistance (%s Rs %.1f) is far; capped at %.0f ATR" % (
                lvl_name, lvl, MAX_TARGET_ATR)
        else:
            target = lvl
            target_reason = "Nearest resistance: %s Rs %.1f (+%.1f%%)" % (lvl_name, lvl, (lvl / entry - 1) * 100)
    else:
        n_atr = NO_RES_ATR_HP if is_hp else NO_RES_ATR
        target = entry + n_atr * atr
        target_reason = "No overhead resistance found; %.0f ATR projection (estimate)" % n_atr
    target_pct = (target / entry - 1) * 100
    rr = (target - entry) / risk
    
    surv_status = SURV_MAP.get(clean_sym, "")

    if stop_pct > MAX_STOP_PCT:
        rejected["wide_stop"] += 1
        rej_rows.append({
            "Date": date_str, "Symbol": sym, "Status": status,
            "Class": "High Potential" if is_hp else "Standard",
            "Setup": setup_kind,
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
            "Class": "High Potential" if is_hp else "Standard",
            "Setup": setup_kind,
            "Close": round(close, 2), "Entry": round(entry, 2),
            "Stop": round(stop, 2), "StopTight": round(stop_tight, 2), "Target": round(target, 2),
            "StopDistPct": round(stop_pct, 2), "TargetPct": round(target_pct, 1),
            "RR": round(rr, 2), "Reason": f"Reward:Risk below 1:{MIN_RR}",
            "StopReason": stop_reason, "TargetReason": target_reason,
            "Surveillance": surv_status
        })
        return None

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

    warns = []
    if stop_pct > WIDE_STOP_PCT:
        warns.append("Wide stop (%.1f%% away); position size should be small" % stop_pct)
    if ext > 12:
        warns.append("20-రోజుల average కంటే %.1f%% పైన ఉంది" % ext)
    if not market_ok:
        warns.append("Nifty తన 50-రోజుల average కింద ఉంది")
    if surv_status:
        warns.append(f"Exchange {surv_status} Surveillance (100% Margin / Circuit risk)")
    if neg_names:
        warns.append("NSE event హెచ్చరిక: " + ", ".join(neg_names))
    warning = "; ".join(warns)

    # ---------- Technical reasons ----------
    rs_ = []
    if rsi >= 70:
        rs_.append("RSI %.0f: strong but stretched" % rsi)
    elif rsi >= 50:
        rs_.append("RSI %.0f: healthy momentum zone" % rsi)
    else:
        rs_.append("RSI %.0f: momentum still building" % rsi)
    rs_.append("MACD bullish" if mh > 0 else "MACD not yet bullish")
    rs_.append("Price above 50-DMA and 200-DMA")
    if wk:
        rs_.append("Weekly trend is up")
    if is_true_leader:
        rs_.append("True Market Leader (Mansfield RS > 0 & RS >= 80)")
    if adx >= 20:
        rs_.append("ADX %.0f: %s" % (adx, "trend strengthening" if adx > adx_prev else "trend present"))
    if main_ret is not None:
        rs_.append("3-month return %.0f%% vs index %.0f%%" % (r63 * 100, main_ret * 100))
    if status == "Breakout" and cam_info is not None:
        rs_.append("Closed above last week's Camarilla R4 Rs %.1f on volume %.1fx average" % (cam_info[0], vol_ratio))
    elif status == "Breakout":
        rs_.append("Broke above %d-week base high Rs %.1f on volume %.1fx average" % (base_w, level, vol_ratio))
    elif status == "Near Miss":
        rs_.append("Just below %d-week base high Rs %.1f; volume drying up" % (base_w, level))
    else:
        rs_.append("Pullback to 20/50-DMA support; volume %.1fx average" % vol_ratio)
    if next_res is not None:
        rs_.append("Next resistance Rs %.1f (+%.1f%%)" % (next_res, (next_res / entry - 1) * 100))
    else:
        rs_.append("No major resistance overhead")
    if events_txt:
        rs_.append("NSE events (last 7 days): %s, score %+d" % (events_txt, ev_adj))
    reasons = " | ".join(rs_)

    # ---------- Score ----------
    s = {"Breakout": 25, "Pullback": 20, "Near Miss": 12}[status]
    if status == "Pullback":
        s += clip01((1 - dry) / 0.4) * 10
    else:
        s += clip01((vol_ratio - 1) / 1.5) * 10

    # మాన్స్‌ఫీల్డ్ RS స్కోర్ (గరిష్టంగా 18 పాయింట్లు)
    s += (stock_rs / 100.0) * 15
    if is_true_leader:
        s += 3

    if 50 <= rsi <= 70:
        s += 6
    elif 45 <= rsi < 50 or 70 < rsi <= 75:
        s += 3
    if mh > 0:
        s += 5
    if adx >= 20:
        s += 4
        if adx > adx_prev:
            s += 2
    if wk:
        s += 4
    if n50_ret is not None:
        rel = (r63 - n50_ret) * 100
        if rel > 0:
            s += 3
        if rel > 10:
            s += 2
    if d52 <= 10:
        s += 5
    if d52 <= 5:
        s += 2
    if tight_base:
        s += 5
    if sma200 > c[-210:-10].mean():
        s += 2
    if is_hp:
        s += 5
    if ext > 12:
        s -= 8
    if not market_ok:
        s -= 5
    s += ev_adj
    s = round(max(min(s, 100), 0), 1)
    band = "High Conviction" if s >= 80 else ("Good Setup" if s >= 65 else "Early Watch")

    return {
        "Date": date_str, "Symbol": sym, "Status": status,
        "Class": "High Potential" if is_hp else "Standard",
        "Score": s, "Band": band, "Setup": setup_kind,
        "Close": round(close, 2), "Entry": round(entry, 2), "Stop": round(stop, 2),
        "StopTight": round(stop_tight, 2),
        "Target": round(target, 2), "StopDistPct": round(stop_pct, 2),
        "RR": round(rr, 2), "StopReason": stop_reason, "TargetReason": target_reason,
        "TargetPct": round(target_pct, 1), "VolRatio": round(vol_ratio, 2),
        "RSI": round(rsi, 1), "ADX": round(adx, 1), "Boosters": ", ".join(met),
        "High52": round(high52, 2), "Warning": warning, "Reasons": reasons,
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

columns = ["Date", "Symbol", "Status", "Class", "Score", "Band", "Setup", "Close", "Entry", "Stop", "StopTight",
           "Target", "StopDistPct", "RR", "StopReason", "TargetReason", "TargetPct", "VolRatio",
           "RSI", "ADX", "Boosters", "High52", "Warning", "Reasons", "Events", "EventAdj",
           "Surveillance", "ASM", "GSM", "RS", "IsLeader"]
out = pd.DataFrame(rows, columns=columns)
out = out[out["Score"] >= MIN_SCORE].sort_values("Score", ascending=False)

rej_cols = ["Date", "Symbol", "Status", "Class", "Setup", "Close", "Entry", "Stop", "StopTight", "Target",
            "StopDistPct", "TargetPct", "RR", "Reason", "StopReason", "TargetReason", "Surveillance"]
rej_out = pd.DataFrame(rej_rows, columns=rej_cols).sort_values("RR", ascending=False)

os.makedirs("data/history", exist_ok=True)
out.to_csv("data/short_term.csv", index=False)
out.to_csv("data/history/short_%s.csv" % date_str, index=False)
rej_out.to_csv("data/short_rejected.csv", index=False)
rej_out.to_csv("data/excluded_short.csv", index=False)

print("data తేదీ:", date_str)
print(f"Reward:Risk < {MIN_RR} వల్ల తిరస్కరించినవి:", rejected["low_rr"])
print(f"Stop-loss > {MAX_STOP_PCT}% వల్ల తిరస్కరించినవి:", rejected["wide_stop"])
print("మొత్తం షార్ట్-టర్మ్ ఫలితాలు:", len(out))
if len(out) > 0:
    print(out["Status"].value_counts().to_string())
    print(out["Class"].value_counts().to_string())
    print(out.head(10)[["Symbol", "Status", "Class", "Score", "Band", "Entry", "Stop", "Target", "RR", "RS", "IsLeader"]].to_string(index=False))
if len(rej_out) > 0:
    print("తిరస్కరించబడిన టాప్ 5 (RR ఎక్కువ నుంచి):")
    print(rej_out.head(5)[["Symbol", "Status", "Entry", "Stop", "Target", "RR", "Reason"]].to_string(index=False))
