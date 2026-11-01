import os
import datetime
import numpy as np
import pandas as pd
import yfinance as yf

# Stage 1B -> 2A ఇంజిన్ ఇంపోర్ట్
try:
    from stage_engine import evaluate_stage_and_rationale
except ImportError:
    evaluate_stage_and_rationale = None

MIN_PRICE = 50
MIN_TRADED_VALUE = 8e7      # ₹10 కోట్ల నుండి ₹8 కోట్లకు కొద్దిగా సర్దుబాటు
MIN_SCORE = 25              # మార్కెట్ కన్సాలిడేషన్ సర్దుబాటు స్కోర్
MIN_ROWS = 210
ATR_N = 14
MIN_RR = 1.3                # 1.4 నుండి 1.3 కి సడలించాం (మంచి సెటప్‌లు మిస్ కాకుండా)
MAX_STOP_SHORT = 10.0       # 8.0% నుండి 10.0% కి పెంచాం (విన్నర్స్ మిస్ కాకుండా)
BREAKOUT_VOL = 1.25         # 1.3 నుండి 1.25 కి స్వల్ప సడలింపు
LOOKBACK_DAYS = 12          # 10 నుండి 12 రోజులకు పొడిగించాం
RUNUP_WARN = 100            # 6 నెలల్లో 100%+ రనప్ వార్నింగ్
RUNUP_PEN = -6

PARAMS = {
    "Short Term": dict(swing=40, buf=0.3, minatr=1.5, maxatr=10.0, nores=5.0, wide=8.0),
    "Long Term": dict(swing=120, buf=0.5, minatr=2.5, maxatr=25.0, nores=15.0, wide=20.0),
}
STAGES = [(3, "Fresh", 0, 0), (8, "Early", -4, 2), (15, "Extended", -10, 3), (9999, "Late", -15, 4)]

def load_q_turnaround():
    p = 'data/q2_turnaround.csv'
    if not os.path.exists(p):
        return {}
    try:
        df = pd.read_csv(p)
        m = {}
        for _, r in df.iterrows():
            sym = str(r.get('Symbol', '')).replace('.NS', '').replace('.BO', '').strip().upper()
            if not sym:
                continue
            is_turn = str(r.get('Turnaround', '')).strip().lower() == 'yes'
            score = float(r.get('Score', 0) or 0)
            m[sym] = {'turnaround': is_turn, 'score': score}
        return m
    except Exception:
        return {}

Q_TURNAROUND = load_q_turnaround()

rejected = {"low_rr": 0, "wide_stop": 0}
rej_rows = []

def clip01(x):
    return float(min(max(x, 0.0), 1.0))

def detect_vcp(h, l, c, v):
    """Detects Volatility Contraction Pattern (VCP) and Volume Dry-Up."""
    if len(c) < 40:
        return False, False, "", 0.0

    vol_20_avg = np.mean(v[-21:-1]) if len(v) >= 21 else np.mean(v)
    vol_recent_avg = np.mean(v[-4:])

    is_dryup = False
    dryup_pct = 0.0
    if vol_20_avg > 0:
        dryup_ratio = vol_recent_avg / vol_20_avg
        if dryup_ratio < 0.70:
            is_dryup = True
            dryup_pct = round((1.0 - dryup_ratio) * 100, 1)

    is_vcp = False
    vcp_desc = ""
    r1 = (np.max(h[-40:-20]) - np.min(l[-40:-20])) / np.mean(c[-40:-20]) * 100
    r2 = (np.max(h[-20:-8]) - np.min(l[-20:-8])) / np.mean(c[-20:-8]) * 100
    r3 = (np.max(h[-8:]) - np.min(l[-8:])) / np.mean(c[-8:]) * 100

    if r1 > r2 and r2 > r3 and r3 <= 8.0:
        is_vcp = True
        vcp_desc = f"3-Stage Contraction ({r1:.1f}% -> {r2:.1f}% -> {r3:.1f}%)"
    elif r2 > r3 and r3 <= 6.5:
        is_vcp = True
        vcp_desc = f"Tight Contraction ({r2:.1f}% -> {r3:.1f}%)"

    return is_vcp, is_dryup, vcp_desc, dryup_pct

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

def norm(s):
    return str(s).upper().replace(".NS", "").strip()

def num(x):
    try:
        v = float(x)
        return v if not np.isnan(v) else np.nan
    except Exception:
        return np.nan

# ---------- Fundamentals ----------
FUND = {}

def load_csv(path, fields, tag):
    if not os.path.exists(path):
        return
    d = pd.read_csv(path)
    lower = {c.lower(): c for c in d.columns}
    found = {}
    for key, names in fields.items():
        for nm in names:
            if nm.lower() in lower:
                found[key] = lower[nm.lower()]
                break
    if "symbol" not in lower:
        return
    sc = lower["symbol"]
    for _, r in d.iterrows():
        k = norm(r[sc])
        e = FUND.setdefault(k, {})
        for key, col in found.items():
            val = r[col]
            if key == "Sector":
                if isinstance(val, str) and val.strip():
                    e[key] = val.strip()
            else:
                v = num(val)
                if not np.isnan(v):
                    e[key] = v
        if tag == "scan":
            e["Src"] = "Multibagger/Quality scan"

load_csv("data/fundamentals.csv", {
    "Sector": ["Sector"], "Promoter": ["PromoterPct"], "Pledge": ["PledgePct"],
    "Debt": ["DebtEquity"], "DaysRes": ["DaysToResults"], "MCap": ["MarketCapCr"]}, "base")
for p in ("data/quality.csv", "data/multibagger.csv"):
    load_csv(p, {
        "Sector": ["Sector"], "ROCE": ["ROCE"], "SalesCAGR": ["SalesCAGR3"],
        "ProfitCAGR": ["ProfitCAGR3"], "Debt": ["DebtEquity"], "QSales": ["QSalesYoY"],
        "QProfit": ["QProfitYoY"], "Promoter": ["PromoterPct"],
        "Pledge": ["PledgeOfPromoterPct", "PledgePct"]}, "scan")

def fetch_yf_fund(sym):
    k = norm(sym)
    e = FUND.setdefault(k, {})
    try:
        t = yf.Ticker(k + ".NS")
        info = t.info or {}
        if "Sector" not in e and info.get("sector"):
            e["Sector"] = info["sector"]
        if "Promoter" not in e and info.get("heldPercentInsiders") is not None:
            e["Promoter"] = round(info["heldPercentInsiders"] * 100, 1)
        if "Debt" not in e and info.get("debtToEquity") is not None:
            e["Debt"] = round(info["debtToEquity"] / 100, 2)
        if "QSales" not in e and info.get("revenueGrowth") is not None:
            e["QSales"] = round(info["revenueGrowth"] * 100, 1)
        if "QProfit" not in e and info.get("earningsGrowth") is not None:
            e["QProfit"] = round(info["earningsGrowth"] * 100, 1)
        e["Src"] = "yfinance direct"
    except Exception:
        pass

def fund_eval(sym):
    e = FUND.get(norm(sym))
    if not e:
        return None, "Fundamentals: n/a"
    checks = [("ROCE", "ROCE", lambda x: x > 15, "%"),
              ("SalesCAGR", "Sales growth 3y", lambda x: x > 15, "%"),
              ("ProfitCAGR", "Profit growth 3y", lambda x: x > 15, "%"),
              ("QSales", "Qtr sales YoY", lambda x: x > 10, "%"),
              ("QProfit", "Qtr profit YoY", lambda x: x > 10, "%"),
              ("Debt", "Debt/Equity", lambda x: x < 1, "")]
    pts, known, parts = 0, 0, []
    for key, label, ok, unit in checks:
        v = e.get(key, np.nan)
        if np.isnan(v):
            parts.append("%s n/a" % label)
        else:
            known += 1
            pts += 1 if ok(v) else 0
            parts.append("%s %.1f%s" % (label, v, unit))
    txt = " | ".join(parts)
    if known < 3:
        return None, txt
    return pts / known, txt

# ---------- data చదవడం ----------
df = pd.read_csv("data/prices.csv.gz", parse_dates=["Date"])
df = df.dropna(subset=["Open", "High", "Low", "Close", "Volume"])
last_date = df["Date"].max()
date_str = last_date.strftime("%Y-%m-%d")

ist = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=5, minutes=30)
if last_date.date() == ist.date() and (ist.hour, ist.minute) < (15, 45):
    print("హెచ్చరిక: market ఇంకా ముగియకపోవచ్చు.")

idx = {}
if os.path.exists("data/index.csv"):
    ix = pd.read_csv("data/index.csv", parse_dates=["Date"])
    for name, gi in ix.groupby("Symbol"):
        arr = gi.sort_values("Date")["Close"].dropna().values
        if len(arr) > 64:
            idx[name] = arr
main_name = "NIFTY500" if "NIFTY500" in idx else ("NIFTY50" if "NIFTY50" in idx else None)
main_ret, market_ok = None, True
if main_name:
    a = idx[main_name]
    main_ret = a[-1] / a[-64] - 1
    market_ok = bool(a[-1] > a[-50:].mean())

# ---------- Surveillance Mapping ----------
SURV_MAP = {}
if os.path.exists("data/surveillance.csv"):
    try:
        surv_df = pd.read_csv("data/surveillance.csv")
        for _, row in surv_df.iterrows():
            sym_clean = str(row.get("Symbol", "")).upper().replace(".NS", "").strip()
            stype = str(row.get("Type", "ASM")).upper().strip()
            SURV_MAP[sym_clean] = "GSM" if "GSM" in stype else "ASM"
    except Exception:
        pass

groups = {sym: g.sort_values("Date").reset_index(drop=True) for sym, g in df.groupby("Symbol")}
ret63 = {}
for sym, g in groups.items():
    if len(g) > 64 and g["Date"].iloc[-1] == last_date:
        cc = g["Close"].values
        ret63[sym] = cc[-1] / cc[-64] - 1

# ---------- Pass 1: మాన్స్‌ఫీల్డ్ RS ----------
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
    except Exception:
        pass

# Sector Relative Strength Ranking
sec_returns = {}
for sym, r_val in ret63.items():
    fe = FUND.get(norm(sym), {})
    s_name = fe.get("Sector", "n/a")
    if s_name and s_name != "n/a":
        sec_returns.setdefault(s_name, []).append(r_val)

sec_median = {s: float(np.median(vals)) for s, vals in sec_returns.items() if len(vals) >= 2}
sec_rs_rank = pd.Series(sec_median).rank(pct=True) if sec_median else pd.Series(dtype=float)

def find_breakout(h, l, c, v):
    n = len(c)
    for N in (100, 50):
        for d in range(LOOKBACK_DAYS - 1, -1, -1):
            i = n - 1 - d
            if i - N < 0 or i - 30 < 0:
                continue
            level = h[i - N:i].max()
            va = v[i - 20:i].mean()
            if va <= 0:
                continue
            vr = v[i] / va
            if c[i] > level and vr >= BREAKOUT_VOL and c[-1] >= level * 0.985:
                hb, lb = h[i - 30:i], l[i - 30:i]
                depth = (hb.max() - lb.min()) / hb.max()
                return level, d, vr, N, depth
    return None

def find_pre(h, l, c, v, dry):
    for N in (100, 50):
        level = h[-N - 1:-1].max()
        close = c[-1]
        rng10 = (h[-10:].max() - l[-10:].min()) / close
        # 0.02 నుండి 0.035 మరియు rng10 0.08 నుండి 0.10 కి సర్దుబాటు
        if close <= level and (level / close - 1) <= 0.035 and rng10 <= 0.10 and dry < 1.15:
            return level, N
    return None

def analyze(sym, g):
    if len(g) < MIN_ROWS or g["Date"].iloc[-1] != last_date:
        return None
    h = g["High"].values
    l = g["Low"].values
    c = g["Close"].values
    v = g["Volume"].values.astype(float)
    close = c[-1]
    
    if close < MIN_PRICE or (c[-20:] * v[-20:]).mean() < MIN_TRADED_VALUE:
        return None
        
    vol_avg20 = v[-21:-1].mean()
    if vol_avg20 <= 0:
        return None
    vol_ratio = v[-1] / vol_avg20
    dry = v[-6:-1].mean() / vol_avg20

    sma20, sma50, sma200 = c[-20:].mean(), c[-50:].mean(), c[-200:].mean()
    
    # స్మార్ట్ ట్రెండ్ గేట్: 50-DMA పైన లేదా 20-DMA పైన ఉండి వాల్యూమ్ సర్జ్ ఉండటం
    trend_ok = (close > sma50) or (close > sma20 and vol_ratio >= 1.5)
    if not trend_ok:
        return None
        
    ext = (close / sma20 - 1) * 100
    r63 = c[-1] / c[-64] - 1

    is_vcp, is_dryup, vcp_desc, dryup_pct = detect_vcp(h, l, c, v)

    bo = find_breakout(h, l, c, v)
    if bo is not None:
        status = "Breakout"
        level, days_ago, bvr, N_used, depth = bo
        gain = (close / level - 1) * 100
        stage, stage_pen, stage_ord = "Late", -15, 4
        for lim, nm, pn, od in STAGES:
            if gain <= lim:
                stage, stage_pen, stage_ord = nm, pn, od
                break
        entry = close
        trig = "Broke above %d-day high Rs %.1f %d day(s) ago on volume %.1fx; now %+.1f%% from the level" % (
            N_used, level, days_ago, bvr, gain)
    else:
        pre = find_pre(h, l, c, v, dry)
        if pre is None:
            return None
        status = "Pre-Breakout"
        level, N_used = pre
        days_ago, bvr = 0, vol_ratio
        depth = (h[-30:].max() - l[-30:].min()) / h[-30:].max()
        gain = (close / level - 1) * 100
        stage, stage_pen, stage_ord = "Ready", 0, 1
        entry = level * 1.002
        trig = "%.1f%% below %d-day high Rs %.1f; tight range, volume drying up (%.1fx)" % (-gain, N_used, level, dry)

    k = norm(sym)
    if k not in FUND or "ROCE" not in FUND[k]:
        fetch_yf_fund(sym)

    ffrac, ftxt = fund_eval(sym)
    fe = FUND.get(k, {})
    sector = fe.get("Sector", "n/a")
    prom = fe.get("Promoter", np.nan)
    pled = fe.get("Pledge", np.nan)
    days_res = fe.get("DaysRes", np.nan)
    horizon = "Long Term" if (N_used == 100 and ffrac is not None and ffrac >= 0.5) else "Short Term"
    P = PARAMS[horizon]

    sec_pct = float(sec_rs_rank.get(sector, 0.50)) if sector != "n/a" else 0.50
    sec_score = int(round(sec_pct * 100))
    sec_status = "Leading Sector" if sec_score >= 75 else ("Neutral Sector" if sec_score >= 45 else "Lagging Sector")

    # ---------- ATR, STOP ----------
    pc = c[:-1]
    tr = np.maximum.reduce([h[1:] - l[1:], np.abs(h[1:] - pc), np.abs(l[1:] - pc)])
    atr = float(tr[-ATR_N:].mean())
    if atr <= 0:
        return None
        
    seg_l = l[-P["swing"]:]
    pivl = pd.Series(seg_l).rolling(5, center=True).min().values
    swing_lows = seg_l[(seg_l == pivl) & (seg_l < entry * 0.995)]
    if len(swing_lows) > 0:
        sw = float(swing_lows.max())
        sw_name = "swing low Rs %.1f" % sw
    else:
        sw = float(l[-10:].min())
        sw_name = "10-day low Rs %.1f" % sw
        
    swing_stop = sw - P["buf"] * atr
    atr_stop = entry - P["minatr"] * atr
    if swing_stop <= atr_stop:
        stop = swing_stop
        stop_reason = "Below %s with %.1f ATR buffer" % (sw_name, P["buf"])
    else:
        stop = atr_stop
        stop_reason = "Stop set %.1f ATR below entry" % P["minatr"]
        
    if stop >= entry:
        return None
    risk = entry - stop
    stop_pct = risk / entry * 100

    # ---------- Targets ----------
    high52 = h[-251:-1].max()
    hi250 = h[-251:]
    piv = pd.Series(hi250).rolling(11, center=True).max().values
    all_lv = np.append(hi250[hi250 == piv], high52)
    up_lv = all_lv[all_lv > entry * 1.02]
    cap_price = entry + P["maxatr"] * atr
    next_res = None
    if len(up_lv) > 0:
        lvl = float(up_lv.min())
        next_res = lvl
        lvl_name = "52-week high" if abs(lvl - high52) < 1e-9 else "swing high"
        if lvl > cap_price:
            target2 = cap_price
            target_reason = "Resistance far; capped at %.0f ATR" % P["maxatr"]
        else:
            target2 = lvl
            target_reason = "Nearest resistance: %s Rs %.1f (+%.1f%%)" % (lvl_name, lvl, (lvl / entry - 1) * 100)
    else:
        target2 = entry + P["nores"] * atr
        target_reason = "No overhead resistance found; %.0f ATR projection" % P["nores"]

    if horizon == "Short Term":
        target1 = entry + (1.2 * risk)
        target2 = max(target2, entry + (1.8 * risk))
        target3 = entry + (4.5 * risk)
    else:
        target1 = entry + (1.5 * risk)
        target2 = max(target2, entry + (2.5 * risk))
        target3 = entry + (5.5 * risk)

    target = target2
    target_pct = (target / entry - 1) * 100
    t1_pct = (target1 / entry - 1) * 100
    t2_pct = (target2 / entry - 1) * 100
    t3_pct = (target3 / entry - 1) * 100

    rr = (target - entry) / risk
    surv_status = SURV_MAP.get(k, "")

    # 10% హార్డ్ స్టాప్‌లాస్ కట్-ఆఫ్
    if horizon == "Short Term" and stop_pct > MAX_STOP_SHORT:
        rejected["wide_stop"] += 1
        rej_rows.append({
            "Date": date_str, "Symbol": sym, "Status": status, "Stage": stage, "Horizon": horizon,
            "Close": round(close, 2), "Entry": round(entry, 2), "Stop": round(stop, 2),
            "Target": round(target, 2), "Target1": round(target1, 2),
            "Target2": round(target2, 2), "Target3": round(target3, 2),
            "StopDistPct": round(stop_pct, 2), "TargetPct": round(target_pct, 1),
            "Target1Pct": round(t1_pct, 1), "Target2Pct": round(t2_pct, 1), "Target3Pct": round(t3_pct, 1),
            "RR": round(rr, 2),
            "Reason": f"Stop-loss too far ({stop_pct:.1f}%, limit {MAX_STOP_SHORT:.1f}%)",
            "StopReason": stop_reason, "TargetReason": target_reason,
            "Surveillance": surv_status})
        return None

    if rr < MIN_RR:
        rejected["low_rr"] += 1
        rej_rows.append({
            "Date": date_str, "Symbol": sym, "Status": status, "Stage": stage, "Horizon": horizon,
            "Close": round(close, 2), "Entry": round(entry, 2), "Stop": round(stop, 2),
            "Target": round(target, 2), "Target1": round(target1, 2),
            "Target2": round(target2, 2), "Target3": round(target3, 2),
            "StopDistPct": round(stop_pct, 2), "TargetPct": round(target_pct, 1),
            "Target1Pct": round(t1_pct, 1), "Target2Pct": round(t2_pct, 1), "Target3Pct": round(t3_pct, 1),
            "RR": round(rr, 2),
            "Reason": f"Reward:Risk below 1:{MIN_RR}", "StopReason": stop_reason, "TargetReason": target_reason,
            "Surveillance": surv_status})
        return None

    rsi = rsi14(c)
    mh = macd_hist(c)
    adx, adx_prev = adx14(h, l, c)
    wk = weekly_bullish(g["Date"].values, c)
    
    stock_rs_info = rs_data.get(k, {"RS": 50.0, "Mansfield_RS": 50.0, "Is_Leader": False})
    stock_rs = stock_rs_info["RS"]
    is_true_leader = stock_rs_info["Is_Leader"]

    d52 = (high52 / close - 1) * 100
    low126 = float(l[-126:].min())
    runup = (close / low126 - 1) * 100 if low126 > 0 else 0.0
    runup_pen = RUNUP_PEN if runup > RUNUP_WARN else 0

    warns = []
    if runup > RUNUP_WARN:
        warns.append("Big run-up: +%.0f%% from 6M low" % runup)
    if stage in ["Extended", "Late"]:
        warns.append(f"{stage}: %.1f%% above breakout" % gain)
    if stop_pct > P["wide"]:
        warns.append("Wide stop (%.1f%%)" % stop_pct)
    if ext > 14:
        warns.append("%.1f%% above 20-DMA" % ext)
    if not market_ok:
        warns.append("Nifty below 50-DMA")
    if surv_status:
        warns.append(f"Exchange {surv_status} Surveillance")
    if not np.isnan(days_res) and 0 <= days_res <= 7:
        warns.append("Results in %d day(s)" % days_res)

    rs_ = [trig]
    rs_.append("Up %.0f%% from 6M low" % runup)
    if depth <= 0.28:
        rs_.append("Consolidated in %.0f%% range" % (depth * 100))
    rs_.append("RSI %.0f" % rsi)
    rs_.append("MACD bullish" if mh > 0 else "MACD recovering")
    if close > sma200:
        rs_.append("Above 200-DMA")
    if wk:
        rs_.append("Weekly trend up")
    if is_true_leader:
        rs_.append("True Market Leader")
    if adx >= 20:
        rs_.append("ADX %.0f" % adx)
    rs_.append(ftxt)

    # Score
    s = 25 if status == "Breakout" else 15
    if status == "Breakout":
        s += clip01((bvr - 1) / 1.5) * 10
    else:
        s += clip01((1 - dry) / 0.4) * 10

    s += (stock_rs / 100.0) * 15
    if is_true_leader:
        s += 3

    s += (ffrac * 20) if ffrac is not None else 8
    if 50 <= rsi <= 70:
        s += 6
    if mh > 0:
        s += 5
    if adx >= 20:
        s += 4
    if wk:
        s += 4
    if close > sma200:
        s += 4
    if depth <= 0.28:
        s += 6
    if d52 <= 10:
        s += 5
    if is_vcp:
        s += 5
    if is_dryup:
        s += 3
    if sec_score >= 75:
        s += 4
    elif sec_score < 40:
        s -= 4

    # Quarterly Bonus
    q_info = Q_TURNAROUND.get(norm(sym), {})
    if q_info.get("turnaround"):
        s += 15
        rs_.append("Turnaround Champion (Q2 Result, +15)")
    elif q_info.get("score", 0) >= 70:
        s += 10
        rs_.append("High Growth Leader (Q2 Result, +10)")

    s += stage_pen
    s += runup_pen
    if not market_ok:
        s -= 4
    s = round(max(min(s, 100), 0), 1)
    band = "High Conviction" if s >= 80 else ("Good Setup" if s >= 65 else "Early Watch")

    st_badge = "WATCH"
    st_color = "gold"
    st_code = "Stage 1"
    st_reasons_list = []

    if evaluate_stage_and_rationale is not None:
        try:
            w_df = g.set_index("Date").resample("W").agg({
                "Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"
            }).dropna()
            
            st_info = evaluate_stage_and_rationale(
                daily_df=g, weekly_df=w_df, sector_name=sector, industry_name=""
            )
            if st_info:
                st_badge = st_info["badge"]
                st_color = st_info["badge_color"]
                st_code = st_info["stage_code"]
                for item in st_info.get("reasons", []):
                    st_reasons_list.append("%s: %s" % (item['title'], item['desc']))
        except Exception:
            pass

    if not st_reasons_list:
        if stage == "Fresh":
            st_badge, st_color, st_code = "PRIME ENTRY", "green", "Stage 2A"
            st_reasons_list.append(f"Early Breakout Zone: Level నుండి {gain:.1f}% వద్ద ఉంది.")
        elif stage == "Ready":
            st_badge, st_color, st_code = "WATCHLIST", "gold", "Stage 1B"
            st_reasons_list.append(f"Pivot Testing: Resistance (Rs {level:.1f}) కి సమీపంలో ఉంది.")
        else:
            st_badge, st_color, st_code = "EXTENDED", "red", "Stage 2B"
            st_reasons_list.append(f"Extended Move: {gain:.1f}% పెరిగింది.")

    if is_vcp:
        st_reasons_list.insert(0, f"💎 VCP Contraction: {vcp_desc}")
    if is_dryup:
        st_reasons_list.insert(1 if is_vcp else 0, f"💧 Volume Dry-Up: సప్లై {dryup_pct}% తగ్గింది.")

    st_reasons = " || ".join(st_reasons_list)

    return {
        "Date": date_str, "Symbol": sym, "Sector": sector, "Status": status, "Stage": stage,
        "StageOrd": stage_ord, "Horizon": horizon, "Score": s, "Band": band, "Level": round(level, 2),
        "DaysSince": days_ago, "GainPct": round(gain, 1), "RunUpPct": round(runup, 0), "Close": round(close, 2),
        "Entry": round(entry, 2), "Stop": round(stop, 2), "Target": round(target, 2),
        "Target1": round(target1, 2), "Target1Pct": round(t1_pct, 1),
        "Target2": round(target2, 2), "Target2Pct": round(t2_pct, 1),
        "Target3": round(target3, 2), "Target3Pct": round(t3_pct, 1),
        "StopDistPct": round(stop_pct, 2), "TargetPct": round(target_pct, 1), "RR": round(rr, 2),
        "StopReason": stop_reason, "TargetReason": target_reason, "VolRatio": round(vol_ratio, 2),
        "RSI": round(rsi, 1), "FundScore": ("n/a" if ffrac is None else round(ffrac * 100)),
        "Fundamentals": ftxt, "PromoterPct": ("n/a" if np.isnan(prom) else round(prom, 1)),
        "PledgePct": ("n/a" if np.isnan(pled) else round(pled, 1)),
        "Warning": "; ".join(warns), "Reasons": " | ".join(rs_),
        "StageBadge": st_badge, "StageColor": st_color, "StageCode": st_code, "SimpleReasons": st_reasons,
        "IsVCP": "Yes" if is_vcp else "No", "IsDryUp": "Yes" if is_dryup else "No", "VCPDesc": vcp_desc,
        "SectorRS": sec_score, "SectorStatus": sec_status,
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
    except Exception:
        pass

columns = ["Date", "Symbol", "Sector", "Status", "Stage", "StageOrd", "Horizon", "Score", "Band", "Level",
           "DaysSince", "GainPct", "RunUpPct", "Close", "Entry", "Stop", "Target",
           "Target1", "Target1Pct", "Target2", "Target2Pct", "Target3", "Target3Pct",
           "StopDistPct", "TargetPct", "RR",
           "StopReason", "TargetReason", "VolRatio", "RSI", "FundScore", "Fundamentals", "PromoterPct",
           "PledgePct", "Warning", "Reasons", "StageBadge", "StageColor", "StageCode", "SimpleReasons",
           "IsVCP", "IsDryUp", "VCPDesc", "SectorRS", "SectorStatus",
           "Surveillance", "ASM", "GSM", "RS", "IsLeader"]
out = pd.DataFrame(rows, columns=columns)
out = out[out["Score"] >= MIN_SCORE].sort_values(["StageOrd", "Score"], ascending=[True, False])

rej_cols = ["Date", "Symbol", "Status", "Stage", "Horizon", "Close", "Entry", "Stop", "Target",
            "Target1", "Target1Pct", "Target2", "Target2Pct", "Target3", "Target3Pct",
            "StopDistPct", "TargetPct", "RR", "Reason", "StopReason", "TargetReason", "Surveillance"]
rej_out = pd.DataFrame(rej_rows, columns=rej_cols).sort_values("RR", ascending=False)

# ---------- డూప్లికేట్ నివారణ లాజిక్ ----------
selected_syms = set(out["Symbol"].dropna().astype(str).str.upper().tolist())
for other_radar_file in ["data/ultra_short.csv", "data/short_term.csv"]:
    if os.path.exists(other_radar_file):
        try:
            odf = pd.read_csv(other_radar_file)
            if "Symbol" in odf.columns:
                selected_syms.update(odf["Symbol"].dropna().astype(str).str.upper().tolist())
        except Exception:
            pass

rej_out["Symbol_Clean"] = rej_out["Symbol"].astype(str).str.upper()
rej_out = rej_out[~rej_out["Symbol_Clean"].isin(selected_syms)].drop(columns=["Symbol_Clean"])

# ---------- ఫైల్స్ సేవ్ చేయడం ----------
os.makedirs("data/history", exist_ok=True)
out.to_csv("data/early_movers.csv", index=False)
out.to_csv("data/history/early_%s.csv" % date_str, index=False)
rej_out.to_csv("data/early_rejected.csv", index=False)
rej_out.to_csv("data/excluded_early.csv", index=False)

print("data తేదీ:", date_str)
print("ఎర్లీ మూవర్స్ ఫలితాలు:", len(out))
