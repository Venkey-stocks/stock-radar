import os
import datetime
import numpy as np
import pandas as pd

MIN_PRICE = 50              # కనీస ధర
MIN_TRADED_VALUE = 8e7      # ₹10 కోట్ల నుండి ₹8 కోట్లకు కొద్దిగా సడలించాం (మంచి స్మాల్ క్యాప్స్ కోసం)
MIN_SCORE = 20              # కనీస స్కోర్
MIN_ROWS = 70               # కనీసం ఇన్ని రోజుల data ఉండాలి
MAX_STOP_PCT = 10.0         # 8.0% నుండి 10.0% కి పెంచాం (విన్నర్స్ మిస్ కాకుండా)

# ---- Stop / Target (టెక్నికల్) ----
ATR_N = 14                  # ATR కాలం
SWING_LOOKBACK = 30         # swing low కోసం గత రోజులు
ATR_BUFFER = 0.25           # swing low కింద ATR బఫర్
ATR_MIN_STOP = 1.0          # stop కనీసం ఇన్ని ATR దూరం
NO_RES_ATR = 3.5            # 3.0 నుండి 3.5 కి సర్దుబాటు
MAX_TARGET_ATR = 7.0        # target గరిష్టం
MIN_RR = 1.3                # 1.4 నుండి 1.3 కి సడలించాం
WIDE_STOP_PCT = 8.0         # 8% దాటితే "Wide stop" హెచ్చరిక

# ---- Event score ----
EV_BOOST_MAIN = 5
EV_BOOST_DEAL = 3
EV_BOOST_CAP = 8
EV_PEN_DEFAULT = -10
EV_PEN_DISRUPT = -5
EV_PEN_AUDITOR = -3

rejected = {"low_rr": 0, "wide_stop": 0}
rej_rows = []

def clip01(x):
    return float(min(max(x, 0.0), 1.0))

# ---------- data చదవడం ----------
df = pd.read_csv("data/prices.csv.gz", parse_dates=["Date"])
df = df.dropna(subset=["Open", "High", "Low", "Close", "Volume"])
last_date = df["Date"].max()
date_str = last_date.strftime("%Y-%m-%d")

ist = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=5, minutes=30)
if last_date.date() == ist.date() and (ist.hour, ist.minute) < (15, 45):
    print("హెచ్చరిక: market ఇంకా ముగియకపోవచ్చు, ఈ రోజు candle అసంపూర్ణం కావచ్చు.")

# ---------- Events & Surveillance ----------
EV = {}
SURV_MAP = {}

if os.path.exists("data/events.csv"):
    try:
        evdf = pd.read_csv("data/events.csv")
        for _, e in evdf.iterrows():
            k = str(e.get("symbol", "")).upper().replace(".NS", "").strip()
            cat = str(e.get("category", "")).strip()
            EV.setdefault(k, set()).add(cat)
            cat_upper = cat.upper()
            if "GSM" in cat_upper:
                SURV_MAP[k] = "GSM"
            elif "ASM" in cat_upper:
                SURV_MAP[k] = "ASM"
        print("events చదివాం, symbols:", len(EV))
    except Exception as ex:
        print("హెచ్చరిక: events.csv చదవడం కుదరలేదు:", ex)

if os.path.exists("data/surveillance.csv"):
    try:
        surv_df = pd.read_csv("data/surveillance.csv")
        for _, row in surv_df.iterrows():
            sym_clean = str(row.get("Symbol", "")).upper().replace(".NS", "").strip()
            stype = str(row.get("Type", "ASM")).upper().strip()
            SURV_MAP[sym_clean] = "GSM" if "GSM" in stype else "ASM"
        print("ప్రత్యేక surveillance లిస్ట్ లోడ్ అయ్యింది, stocks:", len(SURV_MAP))
    except Exception as e:
        print("surveillance.csv చదవడం విఫలమైంది:", e)

groups = {sym: g.sort_values("Date").reset_index(drop=True) for sym, g in df.groupby("Symbol")}

# ---------- Pass 1: మాన్స్‌ఫీల్డ్ RS లోడ్ చేయడం ----------
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
        print("మాన్స్‌ఫీల్డ్ RS ర్యాంకులు లోడ్ అయ్యాయి:", len(rs_data))
    except Exception as e:
        print("rs_rank.csv లోడింగ్ లోపం:", e)

# ---------- Pass 2: ఒక్కో stock విశ్లేషణ ----------
def analyze(sym, g):
    if len(g) < MIN_ROWS or g["Date"].iloc[-1] != last_date:
        return None

    o = g["Open"].values
    h = g["High"].values
    l = g["Low"].values
    c = g["Close"].values
    v = g["Volume"].values.astype(float)
    close = c[-1]

    # Universe filters
    if close < MIN_PRICE:
        return None
    if (c[-20:] * v[-20:]).mean() < MIN_TRADED_VALUE:
        return None
        
    # 2 రోజుల ర్యాలీ పరిమితిని 10% నుండి 14% కి సడలించాం
    if close / c[-3] - 1 > 0.14:
        return None

    res = h[-21:-1].max()          # 20 రోజుల రెసిస్టెన్స్
    high52 = h[-251:-1].max() if len(h) > 251 else h[:-1].max()
    vol_avg20 = v[-21:-1].mean()
    if vol_avg20 <= 0:
        return None
    vol_ratio = v[-1] / vol_avg20

    day_range = h[-1] - l[-1]
    close_pos = (close - l[-1]) / day_range if day_range > 0 else 0.5

    gap = bool(o[-1] > res and c[-2] <= res)
    above = close > res
    dist_res = (res / close - 1) * 100

    # Range contraction
    rng = (h - l) / c
    contr = rng[-11:-1].mean() / rng[-51:-1].mean() if len(rng) > 51 else 1.0
    dry = v[-6:-1].mean() / vol_avg20

    # ---------- Status (స్మార్ట్ ఫిల్టర్ అప్‌గ్రేడ్) ----------
    cp_need = 0.5 if (gap and close >= o[-1]) else 0.60
    if above:
        if close > res * 1.10:     # 1.08 నుండి 1.10 కి కాస్త వెసులుబాటు
            return None
        if vol_ratio >= 1.6 and close_pos >= cp_need:
            status = "Breakout"
        elif vol_ratio >= 1.2:
            status = "Near Miss"
        else:
            return None
    else:
        # రెసిస్టెన్స్ కింద ఉన్న సెటప్‌లు (విన్నర్స్ మిస్ కాకుండా)
        if 0 <= dist_res <= 2.0 and vol_ratio >= 1.5:
            status = "Near Miss"
        elif 0 <= dist_res <= 10.0 and contr < 1.20 and dry < 1.20:
            status = "Setup"
        elif 10.0 < dist_res <= 16.0 and vol_ratio >= 2.0 and close_pos >= 0.7:
            # బాటమ్ రివర్సల్ విన్నర్ల కోసం కొత్త కేటగిరీ (AGIIL, SBFC లాంటివి క్యాచ్ అవ్వడానికి)
            status = "Setup"
        else:
            return None

    # ---------- Entry ----------
    entry = res * 1.002 if status == "Setup" and dist_res <= 5.0 else close

    # ---------- ATR (14 రోజులు) ----------
    pc = c[:-1]
    tr = np.maximum.reduce([h[1:] - l[1:], np.abs(h[1:] - pc), np.abs(l[1:] - pc)])
    atr = float(tr[-ATR_N:].mean())
    if atr <= 0:
        return None

    # ---------- STOP ----------
    seg_l = l[-SWING_LOOKBACK:]
    pivl = pd.Series(seg_l).rolling(5, center=True).min().values
    swing_lows = seg_l[(seg_l == pivl) & (seg_l < entry * 0.995)]
    if len(swing_lows) > 0:
        sw = float(swing_lows.max())
        sw_name = "swing low Rs %.1f" % sw
    else:
        sw = float(l[-10:].min())
        sw_name = "10-day low Rs %.1f" % sw

    tight_swing_stop = sw - ATR_BUFFER * atr
    tight_atr_stop = entry - ATR_MIN_STOP * atr
    stop_tight = min(tight_swing_stop, tight_atr_stop)

    whipsaw_buffer = sw * 0.0075
    safe_swing_stop = (sw - whipsaw_buffer) - (ATR_BUFFER * atr)
    safe_atr_stop = entry - (ATR_MIN_STOP + 0.25) * atr

    if safe_swing_stop <= safe_atr_stop:
        stop = safe_swing_stop
        stop_reason = "Below %s with dynamic buffer + %.2f ATR" % (sw_name, ATR_BUFFER)
    else:
        stop = safe_atr_stop
        stop_reason = "Safe stop set %.2f ATR below entry" % (ATR_MIN_STOP + 0.25)

    if stop >= entry:
        return None
    risk = entry - stop
    stop_pct = risk / entry * 100

    clean_sym = sym.upper().replace(".NS", "").strip()
    surv_status = SURV_MAP.get(clean_sym, "")

    # ---------- MULTI-LEVEL TARGETS ----------
    hi250 = h[-251:] if len(h) >= 251 else h
    piv = pd.Series(hi250).rolling(11, center=True).max().values
    levels = hi250[hi250 == piv]
    levels = np.append(levels, high52)
    levels = levels[levels > entry * 1.02]
    cap_price = entry + MAX_TARGET_ATR * atr
    
    if len(levels) > 0:
        lvl = float(levels.min())
        lvl_name = "52-week high" if abs(lvl - high52) < 1e-9 else "swing high"
        if lvl > cap_price:
            target2 = cap_price
            target_reason = "Resistance far; capped at %.0f ATR" % MAX_TARGET_ATR
        else:
            target2 = lvl
            target_reason = "Nearest resistance: %s Rs %.1f (+%.1f%%)" % (lvl_name, lvl, (lvl / entry - 1) * 100)
    else:
        target2 = entry + NO_RES_ATR * atr
        target_reason = "No overhead resistance; %.0f ATR projection" % NO_RES_ATR

    target1 = entry + (1.2 * risk)
    target2 = max(target2, entry + (1.8 * risk))
    target3 = entry + (3.0 * risk)

    target = target2
    target_pct = (target / entry - 1) * 100
    t1_pct = (target1 / entry - 1) * 100
    t2_pct = (target2 / entry - 1) * 100
    t3_pct = (target3 / entry - 1) * 100

    rr = (target - entry) / risk

    # 10% హార్డ్ స్టాప్‌లాస్ కట్-ఆఫ్
    if stop_pct > MAX_STOP_PCT:
        rejected["wide_stop"] += 1
        rej_rows.append({
            "Date": date_str, "Symbol": sym, "Status": status,
            "Close": round(close, 2), "Entry": round(entry, 2),
            "Stop": round(stop, 2), "StopTight": round(stop_tight, 2),
            "Target": round(target, 2), "Target1": round(target1, 2),
            "Target2": round(target2, 2), "Target3": round(target3, 2),
            "StopDistPct": round(stop_pct, 2), "TargetPct": round(target_pct, 1),
            "Target1Pct": round(t1_pct, 1), "Target2Pct": round(t2_pct, 1), "Target3Pct": round(t3_pct, 1),
            "RR": round(rr, 2), "Reason": f"Stop-loss too far ({stop_pct:.1f}%, limit {MAX_STOP_PCT:.1f}%)",
            "StopReason": stop_reason, "TargetReason": target_reason,
            "Surveillance": surv_status
        })
        return None

    if rr < MIN_RR:
        rejected["low_rr"] += 1
        rej_rows.append({
            "Date": date_str, "Symbol": sym, "Status": status,
            "Close": round(close, 2), "Entry": round(entry, 2),
            "Stop": round(stop, 2), "StopTight": round(stop_tight, 2),
            "Target": round(target, 2), "Target1": round(target1, 2),
            "Target2": round(target2, 2), "Target3": round(target3, 2),
            "StopDistPct": round(stop_pct, 2), "TargetPct": round(target_pct, 1),
            "Target1Pct": round(t1_pct, 1), "Target2Pct": round(t2_pct, 1), "Target3Pct": round(t3_pct, 1),
            "RR": round(rr, 2), "Reason": f"Reward:Risk below 1:{MIN_RR}",
            "StopReason": stop_reason, "TargetReason": target_reason,
            "Surveillance": surv_status
        })
        return None

    warns = []
    if stop_pct > WIDE_STOP_PCT:
        warns.append("Wide stop (%.1f%%); position size should be small" % stop_pct)
    if surv_status:
        warns.append(f"Exchange {surv_status} Surveillance")

    # ---------- Events ----------
    cats = EV.get(clean_sym, set())
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
    if neg_names:
        warns.append("Event warning: " + ", ".join(neg_names))
    warning = "; ".join(warns)

    # ---------- ట్రెండ్ టెంప్లేట్ & RS ----------
    sma50 = c[-50:].mean()
    sma150 = c[-150:].mean() if len(c) >= 150 else sma50
    sma200 = c[-200:].mean() if len(c) >= 200 else sma150

    trend_template_pass = bool(close > sma50 and sma50 > sma150 and sma150 > sma200)

    stock_rs_info = rs_data.get(clean_sym, {"RS": 50.0, "Mansfield_RS": 50.0, "Is_Leader": False})
    stock_rs = stock_rs_info["RS"]
    is_true_leader = stock_rs_info["Is_Leader"]

    rs_ = []
    if status == "Breakout":
        rs_.append("Closed above 20-day high Rs %.1f on volume %.1fx" % (res, vol_ratio))
    elif status == "Near Miss":
        rs_.append("Near 20-day high Rs %.1f; volume %.1fx" % (res, vol_ratio))
    else:
        rs_.append("Tightening %.1f%% below resistance Rs %.1f" % (dist_res, res))
    
    if trend_template_pass:
        rs_.append("Trend Template Passed")
    if is_true_leader:
        rs_.append("True Market Leader")
    if vol_ratio >= 2.0:
        rs_.append("Heavy Institutional Volume (%.1fx)" % vol_ratio)

    reasons = " | ".join(rs_)

    # ---------- స్కోరింగ్ ----------
    s = {"Breakout": 30, "Near Miss": 20, "Setup": 12}[status]
    if status != "Setup":
        s += clip01((vol_ratio - 1) / 2) * 10
        s += close_pos * 5
        if vol_ratio >= 2.0:
            s += 5
    s += clip01((1 - contr) / 0.5) * 10
    s += clip01((1 - dry) / 0.4) * 5

    s += (stock_rs / 100.0) * 15
    if is_true_leader:
        s += 5

    if trend_template_pass:
        s += 8
    elif close > sma50:
        s += 4

    d52 = (high52 / close - 1) * 100
    if d52 <= 5:
        s += 5
    elif d52 <= 10:
        s += 2

    s += ev_adj
    s = round(max(min(s, 100), 0), 1)

    band = "High Conviction" if s >= 80 else ("Good Setup" if s >= 65 else "Early Watch")

    return {
        "Date": date_str, "Symbol": sym, "Status": status, "Score": s, "Band": band,
        "Close": round(close, 2), "Entry": round(entry, 2), "Stop": round(stop, 2),
        "StopTight": round(stop_tight, 2), "Target": round(target, 2),
        "Target1": round(target1, 2), "Target1Pct": round(t1_pct, 1),
        "Target2": round(target2, 2), "Target2Pct": round(t2_pct, 1),
        "Target3": round(target3, 2), "Target3Pct": round(t3_pct, 1),
        "StopDistPct": round(stop_pct, 2), "RR": round(rr, 2),
        "StopReason": stop_reason, "TargetReason": target_reason,
        "VolRatio": round(vol_ratio, 2),
        "TargetPct": round(target_pct, 1), "Resistance": round(res, 2),
        "High52": round(high52, 2), "Gap": "Yes" if gap else "",
        "Warning": warning, "Reasons": reasons,
        "Events": events_txt, "EventAdj": ev_adj,
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
    except Exception as e:
        pass

columns = ["Date", "Symbol", "Status", "Class", "Score", "Band", "Setup", "Close", "Entry", "Stop", "StopTight",
           "Target", "Target1", "Target1Pct", "Target2", "Target2Pct", "Target3", "Target3Pct",
           "StopDistPct", "RR", "StopReason", "TargetReason", "TargetPct", "VolRatio",
           "RSI", "ADX", "Boosters", "High52", "Warning", "Reasons", "Events", "EventAdj",
           "Surveillance", "ASM", "GSM", "RS", "IsLeader"]
out = pd.DataFrame(rows, columns=columns)

# ---------- Quarterly Turnaround Boost ----------
turnaround_file = "data/q2_turnaround.csv"
if os.path.exists(turnaround_file) and len(out) > 0:
    try:
        df_q = pd.read_csv(turnaround_file)
        t_champs = set(df_q[df_q["Turnaround"].astype(str).str.upper() == "YES"]["Symbol"].astype(str).str.upper().tolist())
        g_leaders = set(df_q[(df_q["Turnaround"].astype(str).str.upper() != "YES") & (pd.to_numeric(df_q["Score"], errors='coerce') >= 70)]["Symbol"].astype(str).str.upper().tolist())

        for idx_row, row_val in out.iterrows():
            sym_clean = str(row_val["Symbol"]).replace(".NS", "").strip().upper()
            bonus = 0
            tag = ""

            if sym_clean in t_champs:
                bonus = 15
                tag = "Q2 Turnaround Champion (+15)"
            elif sym_clean in g_leaders:
                bonus = 10
                tag = "Q2 High Growth Leader (+10)"

            if bonus > 0:
                new_score = round(min(100.0, float(row_val["Score"]) + bonus), 1)
                out.at[idx_row, "Score"] = new_score
                out.at[idx_row, "Band"] = "High Conviction" if new_score >= 80 else ("Good Setup" if new_score >= 65 else "Early Watch")
                old_reasons = str(row_val.get("Reasons", ""))
                out.at[idx_row, "Reasons"] = f"{tag} | {old_reasons}" if old_reasons else tag

        print(f"Ultra Short: Turnaround Boost పూర్తయింది.")
    except Exception as ex_q:
        pass

out = out[out["Score"] >= MIN_SCORE].sort_values("Score", ascending=False)

rej_cols = ["Date", "Symbol", "Status", "Close", "Entry", "Stop", "StopTight",
            "Target", "Target1", "Target1Pct", "Target2", "Target2Pct", "Target3", "Target3Pct",
            "StopDistPct", "TargetPct", "RR", "Reason", "StopReason", "TargetReason", "Surveillance"]
rej_out = pd.DataFrame(rej_rows, columns=rej_cols).sort_values("RR", ascending=False)

# ---------- డూప్లికేట్ నివారణ లాజిక్ ----------
selected_syms = set(out["Symbol"].dropna().astype(str).str.upper().tolist())
for other_radar_file in ["data/short_term.csv", "data/early_movers.csv"]:
    if os.path.exists(other_radar_file):
        try:
            odf = pd.read_csv(other_radar_file)
            if "Symbol" in odf.columns:
                selected_syms.update(odf["Symbol"].dropna().astype(str).str.upper().tolist())
        except Exception:
            pass

rej_out["Symbol_Clean"] = rej_out["Symbol"].astype(str).str.upper()
rej_out = rej_out[~rej_out["Symbol_Clean"].isin(selected_syms)].drop(columns=["Symbol_Clean"])

# ---------- ఫైల్స్ సేవ్ చేయడం & ఎక్స్‌క్లూడెడ్ హిస్టరీ అపెండ్ లాజిక్ ----------
os.makedirs("data/history", exist_ok=True)
out.to_csv("data/ultra_short.csv", index=False)
out.to_csv("data/history/ultra_%s.csv" % date_str, index=False)
rej_out.to_csv("data/ultra_rejected.csv", index=False)

# ఎక్స్‌క్లూడెడ్ హిస్టరీ ఓవర్‌రైట్ అవ్వకుండా పాత తేదీల డేటాకు జోడించడం (Append)
ex_file = "data/excluded_ultra.csv"
if os.path.exists(ex_file):
    try:
        old_rej = pd.read_csv(ex_file)
        combined_rej = pd.concat([old_rej, rej_out], ignore_index=True)
        combined_rej = combined_rej.drop_duplicates(subset=["Date", "Symbol", "Status"], keep="last")
        combined_rej.sort_values(by=["Date", "RR"], ascending=[False, False]).to_csv(ex_file, index=False)
    except Exception:
        rej_out.to_csv(ex_file, index=False)
else:
    rej_out.to_csv(ex_file, index=False)

print("data తేదీ:", date_str)
print("అల్ట్రా స్కాన్ ఫలితాలు:", len(out))
