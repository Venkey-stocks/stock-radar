import os
import datetime
import numpy as np
import pandas as pd

# ================= మీరు మార్చవలసిన సంఖ్య =================
CAPITAL = 100000   # <-- మీ నిజమైన capital ఇక్కడ మార్చండి (Step C లో)
# ==========================================================

RISK_PCT = 0.01
MIN_PRICE = 50
MIN_TRADED_VALUE = 10e7     # 20 రోజుల సగటు traded value కనీసం Rs 10 కోట్లు
MIN_STOP_PCT = 2.0
MAX_STOP_PCT = 7.5
TARGET_STD = 15.0           # Standard target %
TARGET_HP = 20.0            # High Potential target %
MIN_SCORE = 40
MIN_ROWS = 210              # 200-రోజుల average కి కనీసం ఇన్ని రోజుల data

# ---- Event score (అంచనా బరువులు) ----
EV_BOOST_MAIN = 5           # Order win / Acquisition / Buyback
EV_BOOST_DEAL = 3           # Bulk BUY / Block BUY
EV_BOOST_CAP = 8
EV_PEN_DEFAULT = -10        # Default/Insolvency
EV_PEN_DISRUPT = -5         # Disruption/Suspension
EV_PEN_AUDITOR = -3         # Auditor change


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
    """గత పూర్తి వారం High/Low/Close నుంచి R4 = Close + (High-Low)*1.1/2"""
    w = pd.DataFrame({"H": h, "L": l, "C": c}, index=pd.DatetimeIndex(dates))
    w = w.resample("W").agg({"H": "max", "L": "min", "C": "last"}).dropna()
    if len(w) < 3:
        return None
    p = w.iloc[-2]          # చివరి వారం = ఈ వారం (అసంపూర్ణం కావచ్చు), దానికి ముందు వారం = గత పూర్తి వారం
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

# ---------- Pass 1: 63 రోజుల relative strength ర్యాంక్ ----------
ret63 = {}
for sym, g in groups.items():
    if len(g) > 64 and g["Date"].iloc[-1] == last_date:
        cc = g["Close"].values
        ret63[sym] = cc[-1] / cc[-64] - 1
rs_rank = pd.Series(ret63).rank(pct=True)


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

    # తప్పనిసరి Trend
    sma20 = c[-20:].mean()
    sma50 = c[-50:].mean()
    sma200 = c[-200:].mean()
    sma50_prev = c[-60:-10].mean()
    if not (close > sma50 and close > sma200 and sma50 > sma50_prev):
        return None
    ext = (close / sma20 - 1) * 100
    if ext > 15:
        return None                       # 20-రోజుల average నుంచి చాలా పైకి వెళ్ళింది
    r63 = c[-1] / c[-64] - 1
    if main_ret is not None and r63 <= main_ret:
        return None                       # Nifty కంటే బలం లేదు

    vol_avg20 = v[-21:-1].mean()
    if vol_avg20 <= 0:
        return None
    vol_ratio = v[-1] / vol_avg20
    dry = v[-6:-1].mean() / vol_avg20

    # ---------- Setup (ఒకటి) ----------
    status = None
    level = None
    setup_kind = ""
    base_w = 0
    cam_info = None
    for N in (15, 25, 40):                # 3, 5, 8 వారాల base
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
        # Camarilla R4 breakout (గత పూర్తి వారం పరిధి పైకి దాటడం)
        cam = camarilla_r4(g["Date"].values[-30:], h[-30:], l[-30:], c[-30:])
        if cam is not None:
            r4 = cam[0]
            if close > r4 and close <= r4 * 1.05 and vol_ratio >= 1.2 and close > o[-1] and close > c[-2]:
                status, level, setup_kind = "Breakout", r4, "Camarilla R4"
                cam_info = cam
    if status is None:
        return None
            # ---------- Entry / Stop ----------
    entry = close if status in ("Breakout", "Pullback") else level * 1.002
    stop = l[-7:].min() * 0.999
    risk = entry - stop
    stop_pct = risk / entry * 100
    if stop_pct < MIN_STOP_PCT:
        stop = entry * (1 - MIN_STOP_PCT / 100)
        risk = entry - stop
        stop_pct = MIN_STOP_PCT
    if stop_pct > MAX_STOP_PCT:
        return None

    # ---------- పైన resistance హెచ్చరిక (15% లోపు) ----------
    high52 = h[-251:-1].max()
    hi250 = h[-251:]
    piv = pd.Series(hi250).rolling(11, center=True).max().values
    levels = hi250[hi250 == piv]
    if entry * 1.03 < high52 <= entry * 1.15:
        levels = np.append(levels, high52)
    levels = levels[(levels > entry * 1.03) & (levels <= entry * 1.15)]

    # ---------- Indicators ----------
    rsi = rsi14(c)
    mh = macd_hist(c)
    adx, adx_prev = adx14(h, l, c)
    wk = weekly_bullish(g["Date"].values, c)
    rsr = float(rs_rank.get(sym, 0.0))
    d52 = (high52 / close - 1) * 100

    # ---------- High Potential పరీక్ష ----------
    tight_base = False
    for N in (30, 40, 60):                # 6-12 వారాలు
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
    is_hp = bool(rsr >= 0.85 and tight_base and len(met) >= 2)

    tp = TARGET_HP if is_hp else TARGET_STD
    target = max(entry * (1 + tp / 100), entry + 2 * risk)
    target_pct = (target / entry - 1) * 100
    qty = int(max(min(CAPITAL * RISK_PCT / risk, CAPITAL / entry), 0))

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

    warns = []
    if len(levels) > 0:
        lvl = levels.min()
        warns.append("పైన %.1f%% వద్ద పాత high (Rs %.1f), target కి అడ్డు కావచ్చు" % ((lvl / entry - 1) * 100, lvl))
    if ext > 12:
        warns.append("20-రోజుల average కంటే %.1f%% పైన ఉంది" % ext)
    if not market_ok:
        warns.append("Nifty తన 50-రోజుల average కింద ఉంది")
    if neg_names:
        warns.append("NSE event హెచ్చరిక: " + ", ".join(neg_names))
    warning = "; ".join(warns)

    # ---------- Technical reasons (website లో చూపడానికి, English) ----------
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
    if adx >= 20:
        rs_.append("ADX %.0f: %s" % (adx, "trend strengthening" if adx > adx_prev else "trend present"))
    if main_ret is not None:
        rs_.append("3-month return %.0f%% vs index %.0f%%" % (r63 * 100, main_ret * 100))
    if status == "Breakout" and cam_info is not None:
        rs_.append("Closed above last week's Camarilla R4 Rs %.1f (last week high %.1f, low %.1f, close %.1f) on volume %.1fx average"
                   % (cam_info[0], cam_info[1], cam_info[2], cam_info[3], vol_ratio))
    elif status == "Breakout":
        rs_.append("Broke above %d-week base high Rs %.1f on volume %.1fx average" % (base_w, level, vol_ratio))
    elif status == "Near Miss":
        rs_.append("Just below %d-week base high Rs %.1f; volume drying up" % (base_w, level))
    else:
        rs_.append("Pullback to 20/50-DMA support; volume %.1fx average" % vol_ratio)
    if len(levels) > 0:
        lv_ = levels.min()
        rs_.append("Next resistance Rs %.1f (+%.1f%%)" % (lv_, (lv_ / entry - 1) * 100))
    else:
        rs_.append("No major resistance within 15%")
    if events_txt:
        rs_.append("NSE events (last 7 days): %s, score %+d" % (events_txt, ev_adj))
    reasons = " | ".join(rs_)

    # ---------- Score (100 లో, నా అంచనా బరువులు) ----------
    s = {"Breakout": 25, "Pullback": 20, "Near Miss": 12}[status]
    if status == "Pullback":
        s += clip01((1 - dry) / 0.4) * 10
    else:
        s += clip01((vol_ratio - 1) / 1.5) * 10
    s += rsr * 15
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
    if len(levels) > 0:
        s -= 10
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
        "Target": round(target, 2), "StopDistPct": round(stop_pct, 2), "Qty": qty,
        "TargetPct": round(target_pct, 1), "VolRatio": round(vol_ratio, 2),
        "RSI": round(rsi, 1), "ADX": round(adx, 1), "Boosters": ", ".join(met),
        "High52": round(high52, 2), "Warning": warning, "Reasons": reasons,
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

columns = ["Date", "Symbol", "Status", "Class", "Score", "Band", "Setup", "Close", "Entry", "Stop",
           "Target", "StopDistPct", "Qty", "TargetPct", "VolRatio", "RSI", "ADX", "Boosters",
           "High52", "Warning", "Reasons", "Events", "EventAdj"]
out = pd.DataFrame(rows, columns=columns)
out = out[out["Score"] >= MIN_SCORE].sort_values("Score", ascending=False)

os.makedirs("data/history", exist_ok=True)
out.to_csv("data/short_term.csv", index=False)
out.to_csv("data/history/short_%s.csv" % date_str, index=False)

print("data తేదీ:", date_str)
print("మొత్తం ఫలితాలు:", len(out))
if len(out) > 0:
    print(out["Status"].value_counts().to_string())
    print(out["Class"].value_counts().to_string())
    print(out.head(10)[["Symbol", "Status", "Class", "Score", "Entry", "Stop", "Target"]].to_string(index=False))
