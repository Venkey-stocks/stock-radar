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
    "exul": "data/ultra_rejected.csv", "exsh": "data/short_rejected.csv",
    "exea": "data/early_rejected.csv", "exnl": "data/newlistings_rejected.csv"
}
SEEN = "data/first_seen.csv"
SEEN_COLS = ["Scan", "Date", "Symbol", "Status", "Class", "Band", "Score",
             "Entry", "Stop", "Target", "Target1", "Target2", "Target3", "Close",
             "IsVCP", "VCPType", "Surveillance", "ASM", "GSM"]


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


def detect_vcp_flag(row):
    is_vcp = str(row.get("IsVCP", "")).strip().lower()
    is_dry = str(row.get("IsDryUp", "")).strip().lower()
    reasons = str(row.get("Reasons", "")) + " " + str(row.get("Setup", ""))
    
    if is_vcp in ("yes", "true", "1") or "coiling" in reasons.lower() or "vcp" in reasons.lower():
        return "Yes", "VCP Tight"
    elif is_dry in ("yes", "true", "1") or "dried up" in reasons.lower():
        return "Yes", "Vol Dry-up"
    return "No", "-"


def get_surv_info(row):
    surv = str(row.get("Surveillance", "")).strip().upper()
    asm = str(row.get("ASM", "")).strip().upper()
    gsm = str(row.get("GSM", "")).strip().upper()
    warn = str(row.get("Warning", "")).strip().upper()

    if "GSM" in surv or gsm == "YES" or "GSM" in warn:
        return "GSM", "", "Yes"
    if "ASM" in surv or asm == "YES" or "ASM" in warn:
        return "ASM", "Yes", ""
    return "", "", ""


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
        
        # VCP గుర్తింపు
        vcp_info = [detect_vcp_flag(r) for r in s.to_dict("records")]
        s["IsVCP"] = [x[0] for x in vcp_info]
        s["VCPType"] = [x[1] for x in vcp_info]

        # Surveillance గుర్తింపు
        surv_data = [get_surv_info(r) for r in s.to_dict("records")]
        s["Surveillance"] = [x[0] for x in surv_data]
        s["ASM"] = [x[1] for x in surv_data]
        s["GSM"] = [x[2] for x in surv_data]
        
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
            vcp_info = [detect_vcp_flag(r) for r in ed.to_dict("records")]
            ed["IsVCP"] = [x[0] for x in vcp_info]
            ed["VCPType"] = [x[1] for x in vcp_info]

            surv_data = [get_surv_info(r) for r in ed.to_dict("records")]
            ed["Surveillance"] = [x[0] for x in surv_data]
            ed["ASM"] = [x[1] for x in surv_data]
            ed["GSM"] = [x[2] for x in surv_data]
            
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
seen = seen.reindex(columns=SEEN_COLS)
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
        v_flag, v_type = detect_vcp_flag(r)
        s_type, s_asm, s_gsm = get_surv_info(r)

        risk = max(0.1, entry - stop)
    t1 = fnum(r.get("Target1")) if fnum(r.get("Target1")) else round(entry + 1.2 * risk, 2)
    t2 = fnum(r.get("Target2")) if fnum(r.get("Target2")) else round(target, 2)
    # T3 ఎల్లప్పుడూ T2 కంటే ఎక్కువగా ఉండేలా చూడటం
    calc_t3 = round(max(entry + 4.5 * risk, t2 + 1.5 * risk), 2)
    t3 = fnum(r.get("Target3")) if fnum(r.get("Target3")) else calc_t3
    if t3 <= t2:
        t3 = round(t2 + 1.5 * risk, 2)

        add.append({"Scan": scan, "Date": date, "Symbol": sym, "Status": LABEL[scan],
                    "Class": "", "Band": r.get("Band", ""), "Score": fnum(r.get("Score")),
                    "Entry": entry, "Stop": stop, "Target": target,
                    "Target1": t1, "Target2": t2, "Target3": t3,
                    "Close": entry,
                    "IsVCP": v_flag, "VCPType": v_type,
                    "Surveillance": s_type, "ASM": s_asm, "GSM": s_gsm})
        known.add((scan, sym))
if add:
    seen = pd.concat([seen, pd.DataFrame(add, columns=SEEN_COLS)], ignore_index=True)
    print("కొత్తగా track మొదలైనవి:", len(add))
os.makedirs("data", exist_ok=True)
seen.to_csv(SEEN, index=False)
if len(seen):
    parts.append(seen.copy())

# ---------- Excluded Scans ----------
EXCL_FILES = {
    "exul": "data/ultra_rejected.csv",
    "exsh": "data/short_rejected.csv",
    "exea": "data/early_rejected.csv",
    "exnl": "data/newlistings_rejected.csv"
}

for escan, ef in EXCL_FILES.items():
    if not os.path.exists(ef):
        continue
    try:
        ex_df = pd.read_csv(ef)
        if ex_df.empty or "Symbol" not in ex_df.columns:
            continue
        
        ex_df["Scan"] = escan
        vcp_info = [detect_vcp_flag(r) for r in ex_df.to_dict("records")]
        ex_df["IsVCP"] = [x[0] for x in vcp_info]
        ex_df["VCPType"] = [x[1] for x in vcp_info]
        
        surv_data = [get_surv_info(r) for r in ex_df.to_dict("records")]
        ex_df["Surveillance"] = [x[0] for x in surv_data]
        ex_df["ASM"] = [x[1] for x in surv_data]
        ex_df["GSM"] = [x[2] for x in surv_data]
        
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
            
        for c in ("Entry", "Stop", "Target", "Target1", "Target2", "Target3", "Close"):
            if c not in ex_df.columns:
                ex_df[c] = None
            ex_df[c] = pd.to_numeric(ex_df[c], errors="coerce")
            
        ex_df["Close"] = ex_df["Close"].fillna(ex_df["Entry"])
        ex_df = ex_df.dropna(subset=["Entry", "Stop", "Target"])
        if not ex_df.empty:
            parts.append(ex_df)
    except Exception as e:
        print(f"{ef} చదవలేకపోయాం:", e)

cols = ["Scan", "SignalDate", "Symbol", "SignalStatus", "Class", "Band", "Score", "Entry", "Stop",
        "Target", "Target1", "Target2", "Target3", "Result", "StageResult", "DaysHeld", "ResultDate", "ExitPrice", "PnLPct",
        "T1Date", "T2Date", "T3Date",
        "PeakGainPct", "PeakPrice", "IsVCP", "VCPType",
        "Surveillance", "ASM", "GSM",
        "AfterStopMaxPct", "AfterStopObsDays", "Whipsaw", "DaysToTargetAfterStop", "NowOnRadar"]

perf_path = "data/performance.csv"
if os.path.exists(perf_path):
    try:
        old_perf = pd.read_csv(perf_path)
        if not old_perf.empty and "SignalDate" in old_perf.columns:
            old_excl = old_perf[old_perf["Scan"].astype(str).str.startswith("ex")].copy()
            if not old_excl.empty:
                old_excl = old_excl.rename(columns={"SignalDate": "Date", "SignalStatus": "Status"})
                for req_c in ("Scan", "Date", "Symbol", "Entry", "Stop", "Target"):
                    if req_c in old_excl.columns:
                        old_excl[req_c] = old_excl[req_c]
                parts.append(old_excl)
    except Exception as e:
        print("పాత performance data కలపడంలో లోపం:", e)

if not parts:
    pd.DataFrame(columns=cols).to_csv("data/performance.csv", index=False)
    print("history snapshots లేవు")
    raise SystemExit(0)

sig = pd.concat(parts, ignore_index=True)
sig = sig.drop_duplicates(subset=["Scan", "Date", "Symbol"], keep="first")
if "Class" not in sig.columns:
    sig["Class"] = ""
sig["Class"] = sig["Class"].fillna("")
sig["Date"] = pd.to_datetime(sig["Date"])
sig = sig.sort_values(["Date", "Score"], ascending=[True, False])
for tc in ("Target1", "Target2", "Target3"):
    if tc not in sig.columns:
        sig[tc] = None

out = []
last_idx = {}
for r in sig.to_dict("records"):
    scan, sym = r["Scan"], r["Symbol"]
    win = WINDOW[scan]
    if scan == "early" and str(r["Class"]) == "Long Term":
        win = EARLY_LONG_WINDOW
    ts = pd.Timestamp(r["Date"])
    if pd.isna(ts):
        continue
    di = date_idx.get(ts)
    if di is None:
        di = bisect.bisect_right(all_dates, ts)
    key = (scan, sym)
    if key in last_idx and di - last_idx[key] < win:
        continue
    last_idx[key] = di

    g = bysym.get(sym)
    if g is None:
        continue
    after = g[g["Date"] > ts].head(win)
    entry = float(r["Entry"])
    stop = float(r["Stop"])
    target = float(r["Target"])
    close = float(r["Close"]) if "Close" in r and pd.notna(r["Close"]) else entry

    risk = max(0.1, entry - stop)
    t1 = fnum(r.get("Target1")) or round(entry + 1.2 * risk, 2)
    t2 = fnum(r.get("Target2")) or round(target, 2)
    t3 = fnum(r.get("Target3")) or round(entry + 4.5 * risk, 2)

    pending = entry > close * 1.001
    active = not pending
    result = "Pending" if pending else "Open"
    stage_result = "Pending" if pending else "Active"
    exit_price, res_date, days = None, None, 0

    highest_price = entry
    peak_gain_pct = 0.0

    t1_hit = False
    t2_hit = False
    t3_hit = False
    t1_date, t2_date, t3_date = "", "", ""
    effective_stop = stop

    for d in after.itertuples():
        days += 1
        if not active:
            if d.High >= entry:
                active = True
                stage_result = "Active"
            else:
                continue
                
        if d.High > highest_price:
            highest_price = float(d.High)

        # Check T1
        if not t1_hit and d.High >= t1:
            t1_hit = True
            t1_date = pd.Timestamp(d.Date).strftime("%Y-%m-%d")
            stage_result = "T1 Hit 🎯"
            effective_stop = max(effective_stop, entry)  # Breakeven Trail

        # Check T2
        if not t2_hit and d.High >= t2:
            t2_hit = True
            t2_date = pd.Timestamp(d.Date).strftime("%Y-%m-%d")
            stage_result = "T2 Hit 🎯🎯"
            effective_stop = max(effective_stop, t1)     # Trail to T1

        # Check T3
        if not t3_hit and d.High >= t3:
            t3_hit = True
            t3_date = pd.Timestamp(d.Date).strftime("%Y-%m-%d")
            stage_result = "T3 Hit 🚀"
            effective_stop = max(effective_stop, t2)     # Trail to T2

        # Check Stop Loss (Initial or Trailed)
        if d.Low <= effective_stop:
            if t1_hit:
                result = "Trailed SL"
                stage_result = "Trailed SL 🛡️"
                exit_price = max(effective_stop, d.Open) if d.Open > effective_stop else effective_stop
            else:
                result = "Stop hit"
                stage_result = "Stop hit 🛑"
                exit_price = min(stop, d.Open)
            res_date = d.Date
            break

        # Final Target Check for Legacy compatibility
        if d.High >= target:
            result = "Target hit"
            exit_price = target
            res_date = d.Date
            break

    if entry > 0 and highest_price > entry:
        peak_gain_pct = round(((highest_price - entry) / entry) * 100, 2)

    if result in ("Pending", "Open"):
        if len(after) >= win:
            if active:
                result = "Expired"
                stage_result = "Expired"
                exit_price = float(after["Close"].iloc[-1])
                res_date = after["Date"].iloc[-1]
            else:
                result = "No entry"
                stage_result = "No entry"
        elif active:
            exit_price = float(after["Close"].iloc[-1]) if len(after) else close

    pnl_pct = ""
    if exit_price is not None:
        pnl_pct = round((exit_price / entry - 1) * 100, 2)

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

    s_type, s_asm, s_gsm = get_surv_info(r)

    out.append({
        "Scan": scan, "SignalDate": ts.strftime("%Y-%m-%d"), "Symbol": sym,
        "SignalStatus": r["Status"], "Class": r["Class"], "Band": r["Band"], "Score": r["Score"],
        "Entry": round(entry, 2), "Stop": round(stop, 2),
        "Target": round(target, 2),
        "Target1": round(t1, 2),
        "Target2": round(t2, 2),
        "Target3": round(t3, 2),
        "Result": result,
        "StageResult": stage_result,
        "DaysHeld": days,
        "ResultDate": pd.Timestamp(res_date).strftime("%Y-%m-%d") if res_date is not None else "",
        "ExitPrice": round(exit_price, 2) if exit_price is not None else "",
        "PnLPct": pnl_pct,
        "T1Date": t1_date,
        "T2Date": t2_date,
        "T3Date": t3_date,
        "PeakGainPct": peak_gain_pct if peak_gain_pct > 0 else (pnl_pct if pnl_pct != "" else 0.0),
        "PeakPrice": round(highest_price, 2),
        "IsVCP": r.get("IsVCP", "No"),
        "VCPType": r.get("VCPType", "-"),
        "Surveillance": s_type,
        "ASM": s_asm,
        "GSM": s_gsm,
        "AfterStopMaxPct": as_max, "AfterStopObsDays": as_obs,
        "Whipsaw": whip, "DaysToTargetAfterStop": whip_days,
        "NowOnRadar": "Yes" if str(sym).strip() in now_on.get(scan, set()) else "No",
    })

res = pd.DataFrame(out, columns=cols)
res.to_csv("data/performance.csv", index=False)
print("మొత్తం signals:", len(res))
if len(res):
    print(res.groupby(["Scan", "StageResult"]).size().to_string())
    vcp_signals = res[res["IsVCP"] == "Yes"]
    print(f"VCP Setups లెక్కింపు: {len(vcp_signals)} signals ట్రాక్ చేయబడ్డాయి.")
