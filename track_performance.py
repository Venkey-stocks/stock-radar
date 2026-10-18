import os
import glob
import bisect
import pandas as pd

# ట్రేడింగ్ రోజుల్లో గరిష్ట track కాలం (Excluded scans కూడా చేర్చబడ్డాయి)
WINDOW = {
    "ultra": 5, "short": 20, "multi": 250, "quality": 250, "newl": 60, "early": 20,
    "exul": 5, "exsh": 20, "exea": 20, "exnl": 60
}
EARLY_LONG_WINDOW = 250    # Early Movers లో Long Term horizon కి

# వారం/కొత్త scans: ఈ csv లలో కనిపించిన మొదటి రోజు నుంచి track
LONG = {"multi": "data/multibagger.csv", "quality": "data/quality.csv",
        "newl": "data/newlistings.csv"}
LABEL = {"multi": "Multibagger", "quality": "Quality", "newl": "New listing"}

# ఇప్పుడు radar లో ఉన్నాయా తెలుసుకోవడానికి తాజా జాబితాలు
CURRENT = {
    "ultra": "data/ultra_short.csv", "short": "data/short_term.csv",
    "multi": "data/multibagger.csv", "quality": "data/quality.csv",
    "newl": "data/newlistings.csv", "early": "data/early_movers.csv",
    "exul": "data/excluded_ultra.csv", "exsh": "data/excluded_short.csv",
    "exea": "data/excluded_early.csv", "exnl": "data/excluded_newlistings.csv"
}
SEEN = "data/first_seen.csv"
SEEN_COLS = ["Scan", "Date", "Symbol", "Status", "Class", "Band", "Score",
             "Entry", "Stop", "Target", "Close"]


def fnum(x):
    try:
        v = float(x)
        return None if pd.isna(v) else v
    except Exception:
        return None


def band_of(score):
    v = fnum(score)
    if v is None:
        return ""
    if v >= 80:
        return "High Conviction"
    if v >= 65:
        return "Good Setup"
    return "Early Watch"


px = pd.read_csv("data/prices.csv.gz", parse_dates=["Date"])
px = px.dropna(subset=["Open", "High", "Low", "Close"])
bysym = {s: g.sort_values("Date").reset_index(drop=True) for s, g in px.groupby("Symbol")}
all_dates = sorted(pd.to_datetime(px["Date"].unique()))
date_idx = {d: i for i, d in enumerate(all_dates)}
last_px = all_dates[-1].strftime("%Y-%m-%d")


def close_on(sym, ts):
    g = bysym.get(sym)
    if g is None:
        return None
    h = g[g["Date"] <= ts]
    if h.empty:
        return None
    return float(h["Close"].iloc[-1])


# ---------- ఇప్పుడు radar లో ఉన్న stocks ----------
now_on = {}
for scan, f in CURRENT.items():
    syms = set()
    if os.path.exists(f):
        try:
            cd = pd.read_csv(f)
            if "Symbol" in cd.columns:
                syms = set(cd["Symbol"].astype(str).str.strip())
        except Exception as e:
            print("చదవలేకపోయాం", f, e)
    now_on[scan] = syms

# ---------- Ultra / Short / Early: history snapshots ----------
parts = []
early_snap_found = False
for scan in ("ultra", "short", "early"):
    for f in sorted(glob.glob("data/history/%s_*.csv" % scan)):
        try:
            s = pd.read_csv(f)
        except Exception:
            continue
        if s.empty or "Symbol" not in s.columns:
            continue
        s["Scan"] = scan
        if scan == "early":
            early_snap_found = True
            name = os.path.basename(f)
            fdate = name[len("early_"):-len(".csv")]
            if "Date" not in s.columns:
                s["Date"] = fdate
            if "Status" not in s.columns:
                s["Status"] = s["Stage"] if "Stage" in s.columns else "Early"
            s["Class"] = s["Horizon"] if "Horizon" in s.columns else ""
            if "Band" not in s.columns:
                s["Band"] = s["Score"].apply(band_of) if "Score" in s.columns else ""
            if "Close" not in s.columns:
                closes = []
                for rr in s.to_dict("records"):
                    cts = pd.to_datetime(rr.get("Date"), errors="coerce")
                    c = close_on(str(rr["Symbol"]).strip(), cts) if pd.notna(cts) else None
                    closes.append(c)
                s["Close"] = closes
            for c in ("Entry", "Stop", "Target", "Close"):
                if c not in s.columns:
                    s[c] = None
                s[c] = pd.to_numeric(s[c], errors="coerce")
            s = s.dropna(subset=["Entry", "Stop", "Target", "Close"])
            if s.empty:
                continue
        parts.append(s)

# ---------- Early Movers స్నాప్‌షాట్ లేకపోతే తాజా daily csv నుండి తీసుకోవడం ----------
if not early_snap_found and os.path.exists("data/early_movers.csv"):
    try:
        ed = pd.read_csv("data/early_movers.csv")
        if not ed.empty and "Symbol" in ed.columns:
            ed["Scan"] = "early"
            if "Date" not in ed.columns:
                ed["Date"] = last_px
            if "Status" not in ed.columns:
                ed["Status"] = ed["Stage"] if "Stage" in ed.columns else "Early"
            ed["Class"] = ed["Horizon"] if "Horizon" in ed.columns else ""
            if "Band" not in ed.columns:
                ed["Band"] = ed["Score"].apply(band_of) if "Score" in ed.columns else ""
            if "Close" not in ed.columns:
                closes = []
                for rr in ed.to_dict("records"):
                    cts = pd.to_datetime(rr.get("Date"), errors="coerce")
                    c = close_on(str(rr["Symbol"]).strip(), cts) if pd.notna(cts) else None
                    closes.append(c)
                ed["Close"] = closes
            for c in ("Entry", "Stop", "Target", "Close"):
                if c not in ed.columns:
                    ed[c] = None
                ed[c] = pd.to_numeric(ed[c], errors="coerce")
            ed = ed.dropna(subset=["Entry", "Stop", "Target", "Close"])
            if not ed.empty:
                parts.append(ed)
    except Exception as e:
        print("early_movers.csv చదవలేకపోయాం:", e)

# ---------- Multibagger / Quality / New listings: మొదటిసారి కనిపించిన రోజు నమోదు ----------
if os.path.exists(SEEN):
    try:
        seen = pd.read_csv(SEEN)
    except Exception:
        seen = pd.DataFrame(columns=SEEN_COLS)
else:
    seen = pd.DataFrame(columns=SEEN_COLS)
seen = seen.reindex(columns=SEEN_COLS)     # పాత Qty column ఉంటే తొలగిపోతుంది
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
        add.append({"Scan": scan, "Date": date, "Symbol": sym, "Status": LABEL[scan],
                    "Class": "", "Band": r.get("Band", ""), "Score": fnum(r.get("Score")),
                    "Entry": entry, "Stop": stop, "Target": target, "Close": entry})
        known.add((scan, sym))
if add:
    seen = pd.concat([seen, pd.DataFrame(add, columns=SEEN_COLS)], ignore_index=True)
    print("కొత్తగా track మొదలైనవి:", len(add))
os.makedirs("data", exist_ok=True)
seen.to_csv(SEEN, index=False)
if len(seen):
    parts.append(seen.copy())

# ---------- Excluded Scans (Ultra, Short, Early, New Listings) ట్రాకింగ్ ----------
EXCL_FILES = {
    "exul": "data/excluded_ultra.csv",
    "exsh": "data/excluded_short.csv",
    "exea": "data/excluded_early.csv",
    "exnl": "data/excluded_newlistings.csv"
}

for escan, ef in EXCL_FILES.items():
    # ఒకవేళ excluded ఫైల్ లేకపోతే rejected ఫైల్ నుంచి నేరుగా తీసుకునే ఏర్పాటు
    alt_map = {
        "exsh": "data/short_rejected.csv",
        "exul": "data/ultra_rejected.csv"
    }
    target_file = ef if os.path.exists(ef) else alt_map.get(escan, ef)
    if not os.path.exists(target_file):
        continue
    try:
        ex_df = pd.read_csv(target_file)
        if ex_df.empty or "Symbol" not in ex_df.columns:
            continue
        
        ex_df["Scan"] = escan
        
        if "Date" not in ex_df.columns and "SignalDate" in ex_df.columns:
            ex_df["Date"] = ex_df["SignalDate"]
        elif "Date" not in ex_df.columns:
            ex_df["Date"] = last_px
            
        if "Status" not in ex_df.columns:
            ex_df["Status"] = "Excluded"
            
        if "Class" not in ex_df.columns:
            ex_df["Class"] = "Standard"
            
        if "Band" not in ex_df.columns:
            ex_df["Band"] = ex_df["Score"].apply(band_of) if "Score" in ex_df.columns else "Good Setup"
            
        for c in ("Entry", "Stop", "Target", "Close"):
            if c not in ex_df.columns:
                ex_df[c] = None
            ex_df[c] = pd.to_numeric(ex_df[c], errors="coerce")
            
        ex_df["Close"] = ex_df["Close"].fillna(ex_df["Entry"])
        
        # ఒరిజినల్ Entry, Stop, Target ఉన్న రికార్డులను ట్రాకింగ్‌లోకి తీసుకోవడం
        ex_df = ex_df.dropna(subset=["Entry", "Stop", "Target"])
        
        if not ex_df.empty:
            parts.append(ex_df)
    except Exception as e:
        print(f"{target_file} చదవలేకపోయాం:", e)
cols = ["Scan", "SignalDate", "Symbol", "SignalStatus", "Class", "Band", "Score", "Entry", "Stop",
        "Target", "Result", "DaysHeld", "ResultDate", "ExitPrice", "PnLPct",
        "AfterStopMaxPct", "AfterStopObsDays", "Whipsaw", "DaysToTargetAfterStop", "NowOnRadar"]
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
    if scan == "early" and str(r["Class"]) == "Long Term":
        win = EARLY_LONG_WINDOW
    ts = pd.Timestamp(r["Date"])
    if pd.isna(ts):
        continue                        # తేదీ లేని వరుసలు వదిలేస్తాం
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

    pnl_pct = ""
    if exit_price is not None:
        pnl_pct = round((exit_price / entry - 1) * 100, 2)

    # ---------- Stop hit తర్వాత ఏం జరిగింది (Whipsaw) ----------
    # stop తర్వాతి రోజు నుంచి, అదే window రోజుల పాటు చూస్తాం
    as_max, as_obs, whip, whip_days = "", "", "", ""
    if result == "Stop hit":
        post = g[g["Date"] > pd.Timestamp(res_date)].head(win)
        as_obs = len(post)
        if as_obs > 0:
            as_max = round((float(post["High"].max()) / exit_price - 1) * 100, 2)
            whip = "No"
            for j, p in enumerate(post.itertuples(), 1):
                if p.High >= target:
                    whip = "Yes"
                    whip_days = j
                    break

    out.append({
        "Scan": scan, "SignalDate": ts.strftime("%Y-%m-%d"), "Symbol": sym,
        "SignalStatus": r["Status"], "Class": r["Class"], "Band": r["Band"], "Score": r["Score"],
        "Entry": round(entry, 2), "Stop": round(stop, 2), "Target": round(target, 2),
        "Result": result, "DaysHeld": days,
        "ResultDate": pd.Timestamp(res_date).strftime("%Y-%m-%d") if res_date is not None else "",
        "ExitPrice": round(exit_price, 2) if exit_price is not None else "",
        "PnLPct": pnl_pct,
        "AfterStopMaxPct": as_max, "AfterStopObsDays": as_obs,
        "Whipsaw": whip, "DaysToTargetAfterStop": whip_days,
        "NowOnRadar": "Yes" if str(sym).strip() in now_on.get(scan, set()) else "No",
    })

res = pd.DataFrame(out, columns=cols)
res.to_csv("data/performance.csv", index=False)
print("మొత్తం signals:", len(res))
if len(res):
    print(res.groupby(["Scan", "Result"]).size().to_string())
    st = res[res["Result"] == "Stop hit"]
    if len(st):
        print("Stop hit తర్వాత Whipsaw (target తాకినవి):")
        for scan in st["Scan"].unique():
            s = st[st["Scan"] == scan]
            print(" ", scan, "stop:", len(s), "| whipsaw Yes:", int((s["Whipsaw"] == "Yes").sum()),
                  "| No:", int((s["Whipsaw"] == "No").sum()),
                  "| ఇంకా తెలియదు:", int((s["Whipsaw"] == "").sum()))
