import os
import datetime
import numpy as np
import pandas as pd

MIN_PRICE = 50
MIN_TRADED_VALUE = 10e7
MIN_SCORE = 40
MIN_ROWS = 210
ATR_N = 14
MIN_RR = 2.0
BREAKOUT_VOL = 1.3          # breakout రోజు volume కనీసం ఇంత రెట్లు (అంచనా)
LOOKBACK_DAYS = 10          # గత ఇన్ని రోజుల్లో breakout అయితే "early"

# Short / Long horizon కి stop-target గుణకాలు (అంచనా)
PARAMS = {
    "Short Term": dict(swing=40, buf=0.3, minatr=1.5, maxatr=10.0, nores=5.0, wide=10.0),
    "Long Term": dict(swing=120, buf=0.5, minatr=2.5, maxatr=25.0, nores=15.0, wide=25.0),
}
# Stage: breakout level నుండి పెరుగుదల % (అంచనా) -> (పేరు, score తగ్గింపు, order)
STAGES = [(3, "Fresh", 0, 0), (8, "Early", -4, 2), (15, "Extended", -10, 3), (9999, "Late", -15, 4)]

rej_rows = []


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


def norm(s):
    return str(s).upper().replace(".NS", "").strip()


# ---------- Fundamentals (data/fundamentals.csv, column పేర్లు ఆటోమాటిక్ గా గుర్తిస్తాం) ----------
FUND = {}
if os.path.exists("data/fundamentals.csv"):
    fd = pd.read_csv("data/fundamentals.csv")
    cols = {c.lower().replace(" ", "").replace("_", ""): c for c in fd.columns}

    def pick(*keys):
        for lc, orig in cols.items():
            if all(k in lc for k in keys):
                return orig
        return None

    c_sym = pick("symbol") or fd.columns[0]
    c_sales = pick("sales", "growth") or pick("revenue", "growth")
    c_prof = pick("profit", "growth") or pick("pat", "growth") or pick("earnings", "growth")
    c_roce = pick("roce")
    c_debt = pick("debt")
    print("fundamentals columns గుర్తించినవి -> symbol:", c_sym, "| sales:", c_sales,
          "| profit:", c_prof, "| roce:", c_roce, "| debt:", c_debt)

    def numcol(name):
        return pd.to_numeric(fd[name], errors="coerce") if name else pd.Series([np.nan] * len(fd))

    sales_s, prof_s, roce_s, debt_s = numcol(c_sales), numcol(c_prof), numcol(c_roce), numcol(c_debt)
    # growth fraction (0.15) గా ఉంటే % (15) గా మారుస్తాం
    if sales_s.abs().median() < 2:
        sales_s = sales_s * 100
    if prof_s.abs().median() < 2:
        prof_s = prof_s * 100
    if debt_s.median() > 5:
        debt_s = debt_s / 100
    for i, s_ in enumerate(fd[c_sym].astype(str)):
        FUND[norm(s_)] = (sales_s.iloc[i], prof_s.iloc[i], roce_s.iloc[i], debt_s.iloc[i])
else:
    print("హెచ్చరిక: data/fundamentals.csv లేదు, fundamentals n/a గా ఉంటాయి.")


def fund_eval(sym):
    t = FUND.get(norm(sym))
    if t is None:
        return None, "Fundamentals: n/a"
    sg, pg, roce, de = t
    pts, known = 0, 0
    if not np.isnan(sg):
        known += 1
        pts += sg > 10
    if not np.isnan(pg):
        known += 1
        pts += pg > 15
    if not np.isnan(roce):
        known += 1
        pts += roce > 15
    if not np.isnan(de):
        known += 1
        pts += de < 1
    f = lambda x, u="": ("%.1f%s" % (x, u)) if not np.isnan(x) else "n/a"
    txt = "Sales growth %s | Profit growth %s | ROCE %s | Debt/Equity %s" % (
        f(sg, "%"), f(pg, "%"), f(roce, "%"), f(de))
    if known < 2:
        return None, txt
    return pts / known, txt


# ---------- data చదవడం ----------
df = pd.read_csv("data/prices.csv.gz", parse_dates=["Date"])
df = df.dropna(subset=["Open", "High", "Low", "Close", "Volume"])
last_date = df["Date"].max()
date_str = last_date.strftime("%Y-%m-%d")

ist = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=5, minutes=30)
if last_date.date() == ist.date() and (ist.hour, ist.minute) < (15, 45):
    print("హెచ్చరిక: market ఇంకా మూసి ఉండకపోవచ్చు, ఈ రోజు candle అసంపూర్ణం కావచ్చు.")

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
print("పోలిక index:", main_name, "| market 50-రోజుల average పైన:", market_ok)

groups = {sym: g.sort_values("Date").reset_index(drop=True) for sym, g in df.groupby("Symbol")}
ret63 = {}
for sym, g in groups.items():
    if len(g) > 64 and g["Date"].iloc[-1] == last_date:
        cc = g["Close"].values
        ret63[sym] = cc[-1] / cc[-64] - 1
rs_rank = pd.Series(ret63).rank(pct=True)


def find_breakout(h, l, c, v):
    """గత 10 రోజుల్లో 100 లేదా 50-రోజుల high పైన మొదటి breakout (volume తో), ఇంకా నిలబడి ఉంటే"""
    n = len(c)
    for N in (100, 50):
        for d in range(LOOKBACK_DAYS - 1, -1, -1):      # పాతదాని నుంచి కొత్తదాని వైపు
            i = n - 1 - d
            if i - N < 0:
                continue
            level = h[i - N:i].max()
            va = v[i - 20:i].mean()
            if va <= 0:
                continue
            vr = v[i] / va
            if c[i] > level and vr >= BREAKOUT_VOL and c[-1] >= level * 0.99:
                hb, lb = h[i - 30:i], l[i - 30:i]
                depth = (hb.max() - lb.min()) / hb.max()
                return level, d, vr, N, depth
    return None


def find_pre(h, l, c, v, dry):
    """breakout కి 2% లోపు, ఇరుకు range, volume తగ్గుతోంది"""
    for N in (100, 50):
        level = h[-N - 1:-1].max()
        close = c[-1]
        rng10 = (h[-10:].max() - l[-10:].min()) / close
        if close <= level and (level / close - 1) <= 0.02 and rng10 <= 0.08 and dry < 1.0:
            return level, N
    return None


def analyze(sym, g):
    if len(g) < MIN_ROWS or g["Date"].iloc[-1] != last_date:
        return None
    o = g["Open"].values
    h = g["High"].values
    l = g["Low"].values
    c = g["Close"].values
    v = g["Volume"].values.astype(float)
    close = c[-1]
    if close < MIN_PRICE or (c[-20:] * v[-20:]).mean() < MIN_TRADED_VALUE:
        return None
    sma20, sma50, sma200 = c[-20:].mean(), c[-50:].mean(), c[-200:].mean()
    if close <= sma50:
        return None
    ext = (close / sma20 - 1) * 100
    r63 = c[-1] / c[-64] - 1
    vol_avg20 = v[-21:-1].mean()
    if vol_avg20 <= 0:
        return None
    vol_ratio = v[-1] / vol_avg20
    dry = v[-6:-1].mean() / vol_avg20

    # ---------- Trigger ----------
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
        days_ago, bvr, depth = 0, vol_ratio, (h[-30:].max() - l[-30:].min()) / h[-30:].max()
        gain = (close / level - 1) * 100
        stage, stage_pen, stage_ord = "Ready", 0, 1
        entry = level * 1.002
        trig = "%.1f%% below %d-day high Rs %.1f; tight range, volume drying up (%.1fx)" % (-gain, N_used, level, dry)

    # ---------- Fundamentals & Horizon ----------
    ffrac, ftxt = fund_eval(sym)
    horizon = "Long Term" if (N_used == 100 and ffrac is not None and ffrac >= 0.5) else "Short Term"
    P = PARAMS[horizon]

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
        stop_reason = "Below %s with %.1f ATR buffer (ATR Rs %.1f)" % (sw_name, P["buf"], atr)
    else:
        stop = atr_stop
        stop_reason = "%s is too close; stop set %.1f ATR below entry (ATR Rs %.1f)" % (sw_name, P["minatr"], atr)
    if stop >= entry:
        return None
    risk = entry - stop
    stop_pct = risk / entry * 100

    # ---------- TARGET ----------
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
            target = cap_price
            target_reason = "Nearest resistance (%s Rs %.1f) is far; capped at %.0f ATR" % (lvl_name, lvl, P["maxatr"])
        else:
            target = lvl
            target_reason = "Nearest resistance: %s Rs %.1f (+%.1f%%)" % (lvl_name, lvl, (lvl / entry - 1) * 100)
    else:
        target = entry + P["nores"] * atr
        target_reason = "No overhead resistance found; %.0f ATR projection (estimate)" % P["nores"]
    target_pct = (target / entry - 1) * 100
    rr = (target - entry) / risk
    if rr < MIN_RR:
        rej_rows.append({
            "Date": date_str, "Symbol": sym, "Status": status, "Stage": stage, "Horizon": horizon,
            "Close": round(close, 2), "Entry": round(entry, 2), "Stop": round(stop, 2),
            "Target": round(target, 2), "StopDistPct": round(stop_pct, 2),
            "TargetPct": round(target_pct, 1), "RR": round(rr, 2),
            "Reason": "Reward:Risk below 1:2", "StopReason": stop_reason, "TargetReason": target_reason})
        return None

    # ---------- Indicators ----------
    rsi = rsi14(c)
    mh = macd_hist(c)
    adx, adx_prev = adx14(h, l, c)
    wk = weekly_bullish(g["Date"].values, c)
    rsr = float(rs_rank.get(sym, 0.0))
    d52 = (high52 / close - 1) * 100

    warns = []
    if stage == "Extended":
        warns.append("Extended: %.1f%% above breakout level" % gain)
    if stage == "Late":
        warns.append("Late: %.1f%% above breakout level" % gain)
    if stop_pct > P["wide"]:
        warns.append("Wide stop (%.1f%% away)" % stop_pct)
    if ext > 12:
        warns.append("%.1f%% above 20-DMA" % ext)
    if not market_ok:
        warns.append("Nifty is below its 50-day average")
    if ffrac is None:
        warns.append("Fundamentals n/a")

    rs_ = [trig]
    if depth <= 0.25:
        rs_.append("Consolidated in a %.0f%% range before the move" % (depth * 100))
    rs_.append("RSI %.0f" % rsi)
    rs_.append("MACD bullish" if mh > 0 else "MACD not yet bullish")
    if close > sma200:
        rs_.append("Above 200-DMA")
    if wk:
        rs_.append("Weekly trend is up")
    if adx >= 20:
        rs_.append("ADX %.0f" % adx)
    if main_ret is not None:
        rs_.append("3-month return %.0f%% vs index %.0f%%" % (r63 * 100, main_ret * 100))
    rs_.append(ftxt)
    if next_res is not None:
        rs_.append("Next resistance Rs %.1f (+%.1f%%)" % (next_res, (next_res / entry - 1) * 100))
    else:
        rs_.append("No major resistance overhead")

    # ---------- Score (అంచనా బరువులు) ----------
    s = 25 if status == "Breakout" else 15
    if status == "Breakout":
        s += clip01((bvr - 1) / 1.5) * 10
    else:
        s += clip01((1 - dry) / 0.4) * 10
    s += rsr * 15
    s += (ffrac * 20) if ffrac is not None else 8        # n/a అయితే తటస్థం
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
    if depth <= 0.25:
        s += 6
    if d52 <= 10:
        s += 5
    if main_ret is not None and r63 > main_ret:
        s += 3
    s += stage_pen
    if not market_ok:
        s -= 5
    s = round(max(min(s, 100), 0), 1)
    band = "High Conviction" if s >= 80 else ("Good Setup" if s >= 65 else "Early Watch")

    return {
        "Date": date_str, "Symbol": sym, "Status": status, "Stage": stage, "StageOrd": stage_ord,
        "Horizon": horizon, "Score": s, "Band": band, "Level": round(level, 2),
        "DaysSince": days_ago, "GainPct": round(gain, 1), "Close": round(close, 2),
        "Entry": round(entry, 2), "Stop": round(stop, 2), "Target": round(target, 2),
        "StopDistPct": round(stop_pct, 2), "TargetPct": round(target_pct, 1), "RR": round(rr, 2),
        "StopReason": stop_reason, "TargetReason": target_reason, "VolRatio": round(vol_ratio, 2),
        "RSI": round(rsi, 1), "FundScore": ("n/a" if ffrac is None else round(ffrac * 100)),
        "Fundamentals": ftxt, "Warning": "; ".join(warns), "Reasons": " | ".join(rs_),
    }


rows = []
for sym, g in groups.items():
    try:
        r = analyze(sym, g)
        if r is not None:
            rows.append(r)
    except Exception as e:
        print("దాటవేసాం", sym, e)

columns = ["Date", "Symbol", "Status", "Stage", "StageOrd", "Horizon", "Score", "Band", "Level",
           "DaysSince", "GainPct", "Close", "Entry", "Stop", "Target", "StopDistPct", "TargetPct", "RR",
           "StopReason", "TargetReason", "VolRatio", "RSI", "FundScore", "Fundamentals", "Warning", "Reasons"]
out = pd.DataFrame(rows, columns=columns)
out = out[out["Score"] >= MIN_SCORE].sort_values(["StageOrd", "Score"], ascending=[True, False])
rej_cols = ["Date", "Symbol", "Status", "Stage", "Horizon", "Close", "Entry", "Stop", "Target",
            "StopDistPct", "TargetPct", "RR", "Reason", "StopReason", "TargetReason"]
rej_out = pd.DataFrame(rej_rows, columns=rej_cols).sort_values("RR", ascending=False)

os.makedirs("data/history", exist_ok=True)
out.to_csv("data/early_movers.csv", index=False)
out.to_csv("data/history/early_%s.csv" % date_str, index=False)
rej_out.to_csv("data/early_rejected.csv", index=False)

print("data తేదీ:", date_str)
print("R:R తొలగినవి:", len(rej_out))
print("మొత్తం ఫలితాలు:", len(out))
if len(out) > 0:
    print(out["Stage"].value_counts().to_string())
    print(out["Horizon"].value_counts().to_string())
    print(out.head(10)[["Symbol", "Stage", "Horizon", "Score", "GainPct", "Entry", "Stop", "Target", "RR"]].to_string(index=False))
