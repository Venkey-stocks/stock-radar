import os
import glob
import pandas as pd

WINDOW = {"ultra": 5, "short": 20}   # ట్రేడింగ్ రోజుల్లో గరిష్ట కాలం

px = pd.read_csv("data/prices.csv.gz", parse_dates=["Date"])
px = px.dropna(subset=["Open", "High", "Low", "Close"])
bysym = {s: g.sort_values("Date").reset_index(drop=True) for s, g in px.groupby("Symbol")}
all_dates = sorted(px["Date"].unique())

# ---------- history snapshots చదవడం ----------
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

date_idx = {pd.Timestamp(d): i for i, d in enumerate(all_dates)}

out = []
last_idx = {}   # (scan, symbol) -> చివరి signal రోజు index
for r in sig.to_dict("records"):
    scan, sym = r["Scan"], r["Symbol"]
    win = WINDOW[scan]
    di = date_idx.get(pd.Timestamp(r["Date"]))
    if di is None:
        continue
    key = (scan, sym)
    # అదే stock ఇంకా track లో ఉంటే (window లోపు) మళ్ళీ లెక్కించం
    if key in last_idx and di - last_idx[key] < win:
        continue
    last_idx[key] = di

    g = bysym.get(sym)
    if g is None:
        continue
    after = g[g["Date"] > r["Date"]].head(win)
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
        "Scan": scan, "SignalDate": pd.Timestamp(r["Date"]).strftime("%Y-%m-%d"), "Symbol": sym,
        "SignalStatus": r["Status"], "Class": r["Class"], "Band": r["Band"], "Score": r["Score"],
        "Entry": round(entry, 2), "Stop": round(stop, 2), "Target": round(target, 2), "Qty": qty,
        "Result": result, "DaysHeld": days if active or result == "No entry" else days,
        "ResultDate": pd.Timestamp(res_date).strftime("%Y-%m-%d") if res_date is not None else "",
        "ExitPrice": round(exit_price, 2) if exit_price is not None else "",
        "PnLPct": pnl_pct, "PnLRs": pnl_rs,
    })

res = pd.DataFrame(out, columns=cols)
res.to_csv("data/performance.csv", index=False)
print("మొత్తం signals:", len(res))
if len(res):
    print(res["Result"].value_counts().to_string())
