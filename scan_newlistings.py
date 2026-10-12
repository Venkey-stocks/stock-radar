import io
import os
import time
import requests
import pandas as pd

CAPITAL = 100000          # placeholder, మీరే నిర్ణయించండి
RISK_PCT = 0.01
MIN_DAYS = 25             # కనీసం ఇన్ని రోజుల data
MAX_DAYS = 120            # సుమారు 6 నెలల లోపు listings మాత్రమే
MIN_TURNOVER = 2e7        # రోజుకు సగటున Rs 2 crore (అంచనా)
MAX_STOP_PCT = 0.075

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

nifty = None
try:
    idx = pd.read_csv("data/index.csv", parse_dates=["Date"])
    nifty = idx[idx["Symbol"] == "NIFTY50"].set_index("Date")["Close"].sort_index()
except Exception as e:
    print("Index not available:", e)

rows = []
removed = []
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
    stop = max(float(l[-10:].min()) * 0.99, entry * (1 - MAX_STOP_PCT))
    risk = entry - stop
    if risk <= 0:
        continue
    target = max(entry * 1.15, entry + 2 * risk)
    qty = int(CAPITAL * RISK_PCT / risk)

    warn = "Low history (%d days)" % n
    if n < 60:
        warn += ", very short history"
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
        "RiskPct": round(risk / entry * 100, 1),
        "Qty": qty,
        "Why": "; ".join(why),
        "Warning": warn,
    })

cols = ["Symbol", "Score", "Band", "DataDays", "ListedOn", "ChangeSinceListing%",
        "Return20d%", "FromHigh%", "Entry", "Stop", "Target", "RiskPct", "Qty",
        "Why", "Warning"]
out = pd.DataFrame(rows, columns=cols)
if len(out) > 0:
    out = out.sort_values("Score", ascending=False)
os.makedirs("data", exist_ok=True)
out.to_csv("data/newlistings.csv", index=False)
print("New listings found:", len(out))
print("ASM/GSM వల్ల తొలగించినవి:", len(removed), removed)
