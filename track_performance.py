import os
import glob
import bisect
import pandas as pd

# ట్రేడింగ్ రోజుల్లో గరిష్ట track కాలం
WINDOW = {"ultra": 5, "short": 20, "multi": 250, "quality": 250, "newl": 60}
# వారం/కొత్త scans: ఈ csv లలో కనిపించిన మొదటి రోజు నుంచి track
LONG = {"multi": "data/multibagger.csv", "quality": "data/quality.csv",
        "newl": "data/newlistings.csv"}
LABEL = {"multi": "Multibagger", "quality": "Quality", "newl": "New listing"}
SEEN = "data/first_seen.csv"
SEEN_COLS = ["Scan", "Date", "Symbol", "Status", "Class", "Band", "Score",
             "Entry", "Stop", "Target", "Qty", "Close"]


def fnum(x):
    try:
        v = float(x)
        return None if pd.isna(v) else v
    except Exception:
        return None


px = pd.read_csv("data/prices.csv.gz", parse_dates=["Date"])
px = px.dropna(subset=["Open", "High", "Low", "Close"])
bysym = {s: g.sort_values("Date").reset_index(drop=True) for s, g in px.groupby("Symbol")}
all_dates = sorted(pd.to_datetime(px["Date"].unique()))
date_idx = {d: i for i, d in enumerate(all_dates)}
last_px = all_dates[-1].strftime("%Y-%m-%d")

# ---------- Ultra / Short: history snapshots ----------
parts = []
for scan in ("ultra", "short"):
    for f in sorted(glob.glob("data/history/%s_*.csv" % scan)):
        try:
            s = pd.read_csv(f)
        except Exception:
            continue
        if s.empty:
            continue
        s["Scan"] = scan
        parts.append(s)

# ---------- Multibagger / Quality / New listings: మొదటిసారి కనిపించిన రోజు నమోదు ----------
if os.path.exists(SEEN):
    try:
        seen = pd.read_csv(SEEN)
    except Exception:
        seen = pd.DataFrame(columns=SEEN_COLS)
else:
    seen = pd.DataFrame(columns=SEEN_COLS)
known = set(zip(seen["Scan"].astype(str), seen["Symbol"].astype(str)))

add = []
for scan, f in LONG.items():
    if not os.path.exists(f):
        continue
    try:
        d = pd.read_csv(f)
    except Exception as e:
        print("చదవలేకపోయాం", f, e)
        continue
    if d.empty or "Symbol" not in d.columns:
        continue
    for r in d.to_dict("records"):
        sym = str(r["Symbol"]).strip()
        if (scan, sym) in known:
            continue
        entry, stop, target = fnum(r.get("Entry")), fnum(r.get("Stop")), fnum(r.get("Target"))
        if entry is None or stop is None or target is None:
            continue
        dt = pd.to_datetime(r.get("Date"), errors="coerce")
        date = dt.strftime("%Y-%m-%d") if pd.notna(dt) else last_px
        qty = fnum(r.get("Qty"))
        add.append({"Scan": scan, "Date": date, "Symbol": sym, "Status": LABEL[scan],
                    "Class": "", "Band": r.get("Band", ""), "Score": fnum(r.get("Score")),
                    "Entry": entry, "Stop": stop, "Target": target,
                    "Qty": int(qty) if qty is not None else 0, "Close": entry})
        known.add((scan, sym))
if add:
    seen = pd.concat([seen, pd.DataFrame(add, columns=SEEN_COLS)], ignore_index=True)
    print("కొత్తగా track మొదలైనవి:", len(add))
os.makedirs("data", exist_ok=True)
seen.to_csv(SEEN, index=False)
if len(seen):
    parts.append(seen.copy())

cols = ["Scan", "SignalDate", "Symbol", "SignalStatus", "Class", "Band", "Score", "Entry", "Stop",
        "Target", "Qty", "Result", "DaysHeld", "ResultDate", "ExitPrice", "PnLPct", "PnLRs"]

if not parts:
    pd.DataFrame(columns=cols).to_csv("data/performance.csv", index=False)
    print("history snapshots లేవు")
    raise SystemExit(0)

sig = pd.concat(parts, ignore_index=True)
if "Class" not in sig.columns:
    sig["Class"] = ""
sig["Class"] = sig["Class"].fillna("")
sig["Date"] = pd.to_datetime(sig["Date"])
sig = sig.sort_values(["Date", "Score"], ascending=[True, False])

out = []
last_idx = {}   # (scan, symbol) -> చివరి signal రోజు index
for r in sig.to_dict("records"):
    scan, sym = r["Scan"], r["Symbol"]
    win = WINDOW[scan]
    ts = pd.Timestamp(r["Date"])
    di = date_idx.get(ts)
    if di is None:
        di = bisect.bisect_right(all_dates, ts)
    key = (scan, sym)
    # అదే stock ఇంకా track లో ఉంటే (window లోపు) మళ్ళీ లెక్కించం
    if key in last_idx and di - last_idx[key] < win:
        continue
    last_idx[key] = di

    g = bysym.get(sym)
    if g is None:
        continue
    after = g[g["Date"] > ts].head(win)
    entry, stop, target, close = float(r["Entry"]), float(r["Stop"]), float(r["Target"]), float(r["Close"])
    qty = int(r["Qty"]) if pd.notna(r["Qty"]) else 0
    pending = entry > close * 1.001      # entry ధర పైన ఉంటే, అక్కడికి చేరాకే trade మొదలు
    active = not pending
    result = "Pending" if pending else "Open"
    exit_price, res_date, days = None, None, 0

    for d in after.itertuples():
        days += 1
        if not active:
            if d.High >= entry:
                active = True
            else:
                continue
        if d.Low <= stop:                       # ఒకే రోజు stop, target రెండూ తగిలితే stop అనుకుంటాం (జాగ్రత్త)
            result = "Stop hit"
            exit_price = min(stop, d.Open)      # gap-down అయితే open ధర
            res_date = d.Date
            break
        if d.High >= target:
            result = "Target hit"
            exit_price = target
            res_date = d.Date
            break

    if result in ("Pending", "Open"):
        if len(after) >= win:
            if active:
                result = "Expired"
                exit_price = float(after["Close"].iloc[-1])
                res_date = after["Date"].iloc[-1]
            else:
                result = "No entry"
        elif active:
            exit_price = float(after["Close"].iloc[-1]) if len(after) else close

    pnl_pct, pnl_rs = "", ""
    if exit_price is not None:
        pnl_pct = round((exit_price / entry - 1) * 100, 2)
        pnl_rs = round(qty * (exit_price - entry), 0)

    out.append({
        "Scan": scan, "SignalDate": ts.strftime("%Y-%m-%d"), "Symbol": sym,
        "SignalStatus": r["Status"], "Class": r["Class"], "Band": r["Band"], "Score": r["Score"],
        "Entry": round(entry, 2), "Stop": round(stop, 2), "Target": round(target, 2), "Qty": qty,
        "Result": result, "DaysHeld": days,
        "ResultDate": pd.Timestamp(res_date).strftime("%Y-%m-%d") if res_date is not None else "",
        "ExitPrice": round(exit_price, 2) if exit_price is not None else "",
        "PnLPct": pnl_pct, "PnLRs": pnl_rs,
    })

res = pd.DataFrame(out, columns=cols)
res.to_csv("data/performance.csv", index=False)
print("మొత్తం signals:", len(res))
if len(res):
    print(res.groupby(["Scan", "Result"]).size().to_string())
