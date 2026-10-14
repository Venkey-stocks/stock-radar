import io
import os
import time
import requests
import numpy as np
import pandas as pd

MIN_DAYS = 25             # కనీసం ఇన్ని రోజుల data
MAX_DAYS = 120            # సుమారు 6 నెలల లోపు listings మాత్రమే
MIN_TURNOVER = 2e7        # రోజుకు సగటున Rs 2 crore (అంచనా)

# ---- Stop / Target (టెక్నికల్, అంచనా సంఖ్యలు) ----
ATR_N = 14                # ATR కాలం
SWING_LOOKBACK = 30       # swing low కోసం గత రోజులు
ATR_BUFFER = 0.3          # swing low కింద ATR బఫర్
ATR_MIN_STOP = 1.5        # stop కనీసం ఇన్ని ATR దూరం (new listings ఎక్కువ ఊగుతాయి)
NO_RES_ATR = 4.0          # పైన resistance లేకపోతే target = Entry + ఇన్ని ATR
MAX_TARGET_ATR = 8.0      # target గరిష్టం
MIN_RR = 2.0              # కనీస Reward:Risk
WIDE_STOP_PCT = 10.0      # దీని కంటే stop దూరమైతే "Wide stop" హెచ్చరిక (తొలగింపు కాదు)

# ---------- NSE session (fetch_fundamentals.py లో లాగే) ----------
UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}
sess = requests.Session()
sess.headers.update(UA)
try:
    sess.get("https://www.nseindia.com", timeout=30)
except Exception as e:
    print("NSE home:", e)


def nse(url):
    for _ in range(2):
        try:
            r = sess.get(url, timeout=30)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        time.sleep(1.5)
    return None


def walk(o, out):
    if isinstance(o, dict):
        if "isin" in o or "symbol" in o:
            out.append(o)
        for v in o.values():
            walk(v, out)
    elif isinstance(o, list):
        for v in o:
            walk(v, out)


def flag_sets(url):
    d = nse(url)
    if d is None:
        return None, None
    items = []
    walk(d, items)
    isins, syms = set(), set()
    for it in items:
        if it.get("isin"):
            isins.add(str(it["isin"]).strip())
        if it.get("symbol"):
            syms.add(str(it["symbol"]).strip())
    return isins, syms


# ---------- Symbol -> ISIN ----------
isin_of = {}
for u in ("https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv",
          "https://archives.nseindia.com/content/equities/EQUITY_L.csv"):
    try:
        r = requests.get(u, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
        if r.status_code == 200:
            lst = pd.read_csv(io.StringIO(r.text))
            lst.columns = [c.strip() for c in lst.columns]
            col = [c for c in lst.columns if "ISIN" in c.upper()][0]
            isin_of = dict(zip(lst["SYMBOL"].str.strip(), lst[col].astype(str).str.strip()))
            break
    except Exception as e:
        print("ISIN list:", e)
print("ISIN map:", len(isin_of))

# ---------- ASM / GSM ----------
asm_i, asm_s = flag_sets("https://www.nseindia.com/api/reportASM")
gsm_i, gsm_s = flag_sets("https://www.nseindia.com/api/reportGSM")
print("ASM list:", None if asm_i is None else (len(asm_i), len(asm_s)))
print("GSM list:", None if gsm_i is None else (len(gsm_i), len(gsm_s)))


def flag(sym, isins, syms):
    if isins is None:
        return "Unknown"
    return "Yes" if (isin_of.get(sym) in isins or sym in syms) else "No"


# ---------- prices ----------
px = pd.read_csv("data/prices.csv.gz", parse_dates=["Date"])
last_date = px["Date"].max()
date_str = last_date.strftime("%Y-%m-%d")

nifty = None
try:
    idx = pd.read_csv("data/index.csv", parse_dates=["Date"])
    nifty = idx[idx["Symbol"] == "NIFTY50"].set_index("Date")["Close"].sort_index()
except Exception as e:
    print("Index not available:", e)

rows = []
rej_rows = []             # RR వల్ల తొలగిన stocks (Excluded tab కోసం)
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

    turnover = (c[-20:] * v[-20:]).mean()
    if turnover < MIN_TURNOVER:
        continue

    score = 0
    why = []
    sma20 = c[-20:].mean()
    if c[-1] > sma20:
        score += 20
        why.append("Above 20-day average")
    if n >= 50:
        sma50 = c[-50:].mean()
        if sma20 > sma50:
            score += 15
            why.append("20-day above 50-day")

    hi = h.max()
    from_high = (hi - c[-1]) / hi * 100
    if from_high <= 10:
        score += 20
        why.append("Within 10% of high")
    elif from_high <= 20:
        score += 10
        why.append("Within 20% of high")

    base = v[max(0, n - 60):n - 10]
    if len(base) > 0 and pd.Series(base).median() > 0:
        if v[-10:].mean() / pd.Series(base).median() >= 1.2:
            score += 15
            why.append("Volume rising")

    r20 = (c[-1] / c[-21] - 1) * 100
    if nifty is not None and len(nifty) > 0:
        try:
            n_then = nifty.asof(g["Date"].iloc[-21])
            n_now = nifty.iloc[-1]
            n_r20 = (n_now / n_then - 1) * 100
            if r20 > n_r20:
                score += 15
                why.append("Beats Nifty (20d)")
        except Exception:
            pass

    if c[-1] >= c[0]:
        score += 15
        why.append("Above listing-day close")

    score = min(score, 79)   # తక్కువ history వల్ల High Conviction ఇవ్వం
    if score < 50:
        continue
    band = "Good Setup" if score >= 65 else "Early Watch"

    # ASM/GSM hard filter
    a_flag = flag(sym, asm_i, asm_s)
    g_flag = flag(sym, gsm_i, gsm_s)
    if a_flag == "Yes" or g_flag == "Yes":
        removed.append(sym + (" (ASM)" if a_flag == "Yes" else " (GSM)"))
        continue

    entry = float(c[-1])

    # ---------- ATR (14 రోజులు) ----------
    pc = c[:-1]
    tr = np.maximum.reduce([h[1:] - l[1:], np.abs(h[1:] - pc), np.abs(l[1:] - pc)])
    atr = float(tr[-ATR_N:].mean())
    if atr <= 0:
        continue

    # ---------- STOP: swing low కింద (ATR బఫర్), కనీసం 1.5 ATR దూరం ----------
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
        stop_reason = "Below %s with %.1f ATR buffer (ATR Rs %.1f)" % (sw_name, ATR_BUFFER, atr)
    else:
        stop = atr_stop
        stop_reason = "%s is too close; stop set %.1f ATR below entry (ATR Rs %.1f)" % (
            sw_name, ATR_MIN_STOP, atr)
    risk = entry - stop
    if risk <= 0:
        continue
    stop_pct = risk / entry * 100

    # ---------- TARGET: పైన దగ్గరి నిజమైన resistance ----------
    pivh = pd.Series(h).rolling(11, center=True).max().values
    levels = np.append(h[h == pivh], hi)      # swing highs + listing తర్వాత గరిష్ట high
    levels = levels[levels > entry * 1.02]
    cap_price = entry + MAX_TARGET_ATR * atr
    if len(levels) > 0:
        lvl = float(levels.min())
        lvl_name = "post-listing high" if abs(lvl - hi) < 1e-9 else "swing high"
        if lvl > cap_price:
            target = cap_price
            target_reason = "Nearest resistance (%s Rs %.1f) is far; capped at %.0f ATR" % (
                lvl_name, lvl, MAX_TARGET_ATR)
        else:
            target = lvl
            target_reason = "Nearest resistance: %s Rs %.1f (+%.1f%%)" % (
                lvl_name, lvl, (lvl / entry - 1) * 100)
    else:
        target = entry + NO_RES_ATR * atr
        target_reason = "At or near the post-listing high, no overhead resistance; %.0f ATR projection (estimate)" % NO_RES_ATR
    rr = (target - entry) / risk
    if rr < MIN_RR:
        rejected["low_rr"] += 1
        rej_rows.append({
            "Date": date_str, "Symbol": sym, "Score": score, "Band": band,
            "DataDays": n, "Entry": round(entry, 2), "Stop": round(stop, 2),
            "Target": round(target, 2), "StopDistPct": round(stop_pct, 2),
            "TargetPct": round((target / entry - 1) * 100, 1),
            "RR": round(rr, 2), "Reason": "Reward:Risk below 1:2",
            "StopReason": stop_reason, "TargetReason": target_reason,
        })
        continue

    warn = "Low history (%d days)" % n
    if n < 60:
        warn += ", very short history"
    if stop_pct > WIDE_STOP_PCT:
        warn += "; Wide stop (%.1f%% away), position size should be small" % stop_pct
    if a_flag == "Unknown" or g_flag == "Unknown":
        warn += "; ASM/GSM list could not be checked today"

    rows.append({
        "Symbol": sym,
        "Score": score,
        "Band": band,
        "DataDays": n,
        "ListedOn": g["Date"].iloc[0].strftime("%Y-%m-%d"),
        "ChangeSinceListing%": round((c[-1] / c[0] - 1) * 100, 1),
        "Return20d%": round(r20, 1),
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
    })

cols = ["Symbol", "Score", "Band", "DataDays", "ListedOn", "ChangeSinceListing%",
        "Return20d%", "FromHigh%", "Entry", "Stop", "Target", "RiskPct", "RR",
        "StopReason", "TargetReason", "Why", "Warning"]
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
rej_out.to_csv("data/newlistings_rejected.csv", index=False)       # RR వల్ల తొలగినవి (Excluded tab కి)
print("Reward:Risk %.0f కంటే తక్కువ అని తొలగినవి:" % MIN_RR, rejected["low_rr"])
print("New listings found:", len(out))
print("ASM/GSM వల్ల తొలగించినవి:", len(removed), removed)
if len(rej_out) > 0:
    print("RR తొలగినవి (టాప్ 5, RR ఎక్కువ నుంచి):")
    print(rej_out.head(5)[["Symbol", "Entry", "Stop", "Target", "RR"]].to_string(index=False))
