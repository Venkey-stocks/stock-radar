import os
import pandas as pd

CAPITAL = 100000          # placeholder, మీరే నిర్ణయించండి
RISK_PCT = 0.01
MIN_DAYS = 25             # కనీసం ఇన్ని రోజుల data
MAX_DAYS = 199            # 200 కంటే తక్కువ మాత్రమే (మిగతా scans లో రానివి)
MIN_TURNOVER = 2e7        # రోజుకు సగటున Rs 2 crore (అంచనా)
MAX_STOP_PCT = 0.075

px = pd.read_csv("data/prices.csv.gz", parse_dates=["Date"])
last_date = px["Date"].max()

nifty = None
try:
    idx = pd.read_csv("data/index.csv", parse_dates=["Date"])
    nifty = idx[idx["Symbol"] == "NIFTY50"].set_index("Date")["Close"].sort_index()
except Exception as e:
    print("Index not available:", e)

rows = []
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
    if score < 40:
        continue
    band = "Good Setup" if score >= 65 else "Early Watch"

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
