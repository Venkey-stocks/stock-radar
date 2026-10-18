import os
import glob
import numpy as np
import pandas as pd

# పాత ఫైల్స్ మరియు పెర్ఫార్మెన్స్ పాత్స్
PERF_FILE = "data/performance.csv"
PRICES_FILE = "data/prices.csv.gz"

if not os.path.exists(PRICES_FILE):
    print("prices.csv.gz ఫైల్ లేదు, రికవరీ ఆగిపోయింది.")
    exit(0)

# ధరల డేటా లోడ్ చేయడం
print("ధరల హిస్టరీ డేటా లోడ్ అవుతోంది...")
px = pd.read_csv(PRICES_FILE, parse_dates=["Date"])
px = px.dropna(subset=["Open", "High", "Low", "Close", "Volume"])
px_grouped = {sym: g.sort_values("Date").reset_index(drop=True) for sym, g in px.groupby("Symbol")}

# ఇప్పటికే performance.csv లో ఉన్న రికార్డులను చదవడం
existing_keys = set()
if os.path.exists(PERF_FILE):
    try:
        cur_perf = pd.read_csv(PERF_FILE)
        for _, r in cur_perf.iterrows():
            existing_keys.add((str(r.get("Scan")), str(r.get("SignalDate")), str(r.get("Symbol"))))
    except Exception as e:
        print("Performance file reading error:", e)

backfilled_rows = []

# హిస్టరీ ఫోల్డర్ లోని ఫైల్స్ నుండి గత ఎక్స్‌క్లూడెడ్ స్టాక్స్ ను ప్రాసెస్ చేయడం
history_files = glob.glob("data/history/*_*.csv")
print(f"మొత్తం {len(history_files)} హిస్టరీ ఫైల్స్ పరిశీలించబడుతున్నాయి...")

# ATR కాలిక్యులేషన్ ఫంక్షన్
def calc_atr(df_slice, n=14):
    h = df_slice["High"].values
    l = df_slice["Low"].values
    c = df_slice["Close"].values
    pc = c[:-1]
    tr = np.maximum.reduce([h[1:] - l[1:], np.abs(h[1:] - pc), np.abs(l[1:] - pc)])
    if len(tr) < n:
        return 0.0
    return float(tr[-n:].mean())

# ఒక్కో హిస్టరీ ఫైల్ పరిశీలన
for hf in history_files:
    fname = os.path.basename(hf)
    # ఉదాహరణ: short_2026-10-05.csv
    parts = fname.replace(".csv", "").split("_")
    if len(parts) < 2:
        continue
    scan_prefix, file_date = parts[0], parts[1]
    
    scan_map = {
        "short": "exsh",
        "ultra": "exul",
        "early": "exea",
        "newlistings": "exnl"
    }
    escan = scan_map.get(scan_prefix)
    if not escan:
        continue

    try:
        hdf = pd.read_csv(hf)
        if hdf.empty or "Symbol" not in hdf.columns:
            continue
            
        for _, row in hdf.iterrows():
            sym = str(row["Symbol"]).strip()
            key = (escan, file_date, sym)
            if key in existing_keys:
                continue

            # స్టాక్ ప్రైస్ హిస్టరీ నుండి ఆ రోజు నాటి లెవెల్స్ రికవరీ
            if sym not in px_grouped:
                continue
            sym_df = px_grouped[sym]
            idx_list = sym_df.index[sym_df["Date"] == file_date].tolist()
            if not idx_list:
                continue
            curr_idx = idx_list[0]
            if curr_idx < 30:
                continue

            sub_df = sym_df.iloc[:curr_idx + 1]
            close_val = float(sub_df["Close"].iloc[-1])
            atr_val = calc_atr(sub_df, 14)
            if atr_val <= 0:
                continue

            # ఒరిజినల్ స్ట్రాటజీ లెవల్స్ రికవరీ లాజిక్
            entry = float(row.get("Entry", close_val))
            stop = row.get("Stop")
            target = row.get("Target")

            # ఫైల్ లో ఒరిజినల్ Stop, Target లేకపోతే స్వింగ్ లో ఆధారంగా అసలైన లెక్క
            if pd.isna(stop) or stop is None:
                seg_l = sub_df["Low"].iloc[-30:].values
                sw = float(seg_l.min())
                stop = round(max(sw - 0.3 * atr_val, entry - 1.5 * atr_val), 2)
            else:
                stop = float(stop)

            if pd.isna(target) or target is None:
                target = round(entry + 4.0 * atr_val, 2)
            else:
                target = float(target)

            if stop >= entry:
                continue

            backfilled_rows.append({
                "Scan": escan,
                "SignalDate": file_date,
                "Symbol": sym,
                "SignalStatus": "Excluded",
                "Class": str(row.get("Class", "Standard")),
                "Band": str(row.get("Band", "Good Setup")),
                "Score": float(row.get("Score", 60.0)),
                "Entry": round(entry, 2),
                "Stop": round(stop, 2),
                "Target": round(target, 2),
                "Result": "Pending",
                "DaysHeld": 0,
                "ResultDate": "",
                "ExitPrice": None,
                "PnLPct": 0.0,
                "AfterStopMaxPct": None,
                "AfterStopObsDays": None,
                "Whipsaw": "No",
                "DaysToTargetAfterStop": None,
                "NowOnRadar": "No"
            })
            existing_keys.add(key)
    except Exception as e:
        print(f"Error processing {hf}:", e)

if backfilled_rows:
    b_df = pd.DataFrame(backfilled_rows)
    print(f"మొత్తం {len(b_df)} గత ఎక్స్‌క్లూడెడ్ స్టాక్స్ రికవర్ అయ్యాయి!")
    if os.path.exists(PERF_FILE):
        cur_perf = pd.read_csv(PERF_FILE)
        final_df = pd.concat([cur_perf, b_df], ignore_index=True)
    else:
        final_df = b_df
    final_df.to_csv(PERF_FILE, index=False)
    print("performance.csv లోకి పాత డేటా విజయవంతంగా చేర్చబడింది.")
else:
    print("కొత్తగా రికవర్ చేయడానికి పాత రికార్డులేవీ లేవు.")
