import io
import os
import time
import datetime
import numpy as np
import pandas as pd
import requests
import yfinance as yf

MIN_TV = 2e7            # 20 రోజుల సగటు Traded Value Rs 2 కోట్లు
MCAP_MIN = 500          # Rs కోట్లు
MCAP_MAX = 20000        # కొద్దిగా పెంచాం (15,000 నుండి 20,000 వరకు మిడ్‌క్యాప్ రన్నర్స్ కోసం)
MAX_1Y_RET = 120.0      # గత 1 సంవత్సరంలో 120%+ పెరిగినవి వద్దు (రన్నింగ్ ర్యాలీలకు కాస్త వెసులుబాటు)
MIN_ROCE = 15.0
MIN_CAGR = 15.0         # కనీస బేస్ 15% (20%+ ఉంటే ఎక్కువ స్కోర్ వస్తుంది)
MAX_MINUTES = 150       # గరిష్ట సమయం
QUICK_LIMIT = 120
MIN_SCORE = 40

# ---- Stop / Target (టెక్నికల్) ----
ATR_N = 14
SWING_LOOKBACK = 120
ATR_BUFFER = 0.5
ATR_MIN_STOP = 2.5
NO_RES_ATR = 15.0
MAX_TARGET_ATR = 25.0
MIN_RR = 1.8            # 2.0 నుండి 1.8 కి మార్చాం (మంచి సెటప్‌లు మిస్ కాకుండా)
WIDE_STOP_PCT = 25.0

START = time.time()
QUICK = os.environ.get("QUICK", "") == "yes"

def time_ok():
    return (time.time() - START) / 60.0 < MAX_MINUTES

def clip01(x):
    return float(min(max(x, 0.0), 1.0))

def num(x):
    try:
        v = float(str(x).replace(",", "").replace("%", "").strip())
        return None if v != v else v
    except Exception:
        return None

# ---------- ధర data ----------
px = pd.read_csv("data/prices.csv.gz", parse_dates=["Date"])
px = px.dropna(subset=["Open", "High", "Low", "Close", "Volume"])
last_date = px["Date"].max()
date_str = last_date.strftime("%Y-%m-%d")
ist = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=5, minutes=30)
today = pd.Timestamp(ist.date())
print("data తేదీ:", date_str, "| QUICK:", QUICK)

# ---------- దశ 1: ధర filters + టెక్నికల్ Stop/Target ----------
stage1 = []
for sym, g in px.groupby("Symbol"):
    g = g.sort_values("Date")
    if len(g) < 200 or g["Date"].iloc[-1] != last_date:
        continue
    c = g["Close"].values
    h = g["High"].values
    l = g["Low"].values
    v = g["Volume"].values.astype(float)
    close = c[-1]
    
    tv = (c[-20:] * v[-20:]).mean()
    if tv < MIN_TV:
        continue
    
    # ఫిక్స్: సరిగ్గా గత 250 ట్రేడింగ్ రోజుల (1 సంవత్సరం) రిటర్న్ మాత్రమే లెక్కించాలి
    idx_1y = max(0, len(c) - 250)
    ret1y = (close / c[idx_1y] - 1) * 100
    if ret1y >= MAX_1Y_RET:
        continue
        
    sma200 = c[-200:].mean()
    depth = (h[-30:].max() - l[-30:].min()) / h[-30:].max()
    above = close > sma200
    near_base = close >= 0.9 * sma200 and depth <= 0.25
    if not (above or near_base):
        continue

    # ---- ATR (14 రోజులు) ----
    pc = c[:-1]
    tr = np.maximum.reduce([h[1:] - l[1:], np.abs(h[1:] - pc), np.abs(l[1:] - pc)])
    atr = float(tr[-ATR_N:].mean())
    if atr <= 0:
        continue

    # ---- STOP: swing low కింద ----
    seg_l = l[-SWING_LOOKBACK:]
    pivl = pd.Series(seg_l).rolling(11, center=True).min().values
    swing_lows = seg_l[(seg_l == pivl) & (seg_l < close * 0.98)]
    if len(swing_lows) > 0:
        sw = float(swing_lows.max())
        sw_name = "swing low Rs %.1f" % sw
    else:
        sw = float(l[-60:].min())
        sw_name = "60-day low Rs %.1f" % sw
        
    swing_stop = sw - ATR_BUFFER * atr
    atr_stop = close - ATR_MIN_STOP * atr
    if swing_stop <= atr_stop:
        stop = swing_stop
        stop_reason = "Below %s with %.1f ATR buffer (ATR Rs %.1f)" % (sw_name, ATR_BUFFER, atr)
    else:
        stop = atr_stop
        stop_reason = "%s is too close; stop set %.1f ATR below entry (ATR Rs %.1f)" % (sw_name, ATR_MIN_STOP, atr)
        
    if stop <= 0 or stop >= close:
        continue
    risk = close - stop
    stop_pct = risk / close * 100

    # ---- TARGET: Resistance levels ----
    hi250 = h[-250:]
    high52 = float(hi250.max())
    piv = pd.Series(hi250).rolling(11, center=True).max().values
    levels = np.append(hi250[hi250 == piv], high52)
    levels = levels[levels > close * 1.02]
    cap_price = close + MAX_TARGET_ATR * atr
    
    if len(levels) > 0:
        lvl = float(levels.min())
        lvl_name = "52-week high" if abs(lvl - high52) < 1e-9 else "swing high"
        if lvl > cap_price:
            target = cap_price
            target_reason = "Nearest resistance (%s Rs %.1f) is far; capped at %.0f ATR" % (lvl_name, lvl, MAX_TARGET_ATR)
        else:
            target = lvl
            target_reason = "Nearest resistance: %s Rs %.1f (+%.1f%%)" % (lvl_name, lvl, (lvl / close - 1) * 100)
    else:
        target = close + NO_RES_ATR * atr
        target_reason = "At or near 52W high, no overhead resistance; %.0f ATR projection" % NO_RES_ATR
        
    rr = (target - close) / risk

    stage1.append({"Symbol": sym, "Close": close, "tv": tv, "Ret1Y": ret1y,
                   "Trend": "Above 200-day average" if above else "Near base below 200-day average",
                   "Stop": stop, "Target": target, "RR": rr,
                   "StopReason": stop_reason, "TargetReason": target_reason,
                   "StopDistPct": stop_pct, "TargetPct": (target / close - 1) * 100})

stage1.sort(key=lambda x: -x["tv"])
print("దశ 1 తర్వాత:", len(stage1))
if QUICK:
    stage1 = stage1[:QUICK_LIMIT]
    print("QUICK: మొదటి", len(stage1), "stocks మాత్రమే")

# ---------- Surveillance (ASM / GSM) Mapping ----------
SURV_MAP = {}
if os.path.exists("data/surveillance.csv"):
    try:
        surv_df = pd.read_csv("data/surveillance.csv")
        for _, row in surv_df.iterrows():
            sym_clean = str(row.get("Symbol", "")).upper().replace(".NS", "").strip()
            stype = str(row.get("Type", "ASM")).upper().strip()
            SURV_MAP[sym_clean] = "GSM" if "GSM" in stype else "ASM"
        print("Multibagger: surveillance.csv లోడ్ అయ్యింది, stocks:", len(SURV_MAP))
    except Exception as e:
        print("surveillance.csv చదవడం విఫలమైంది:", e)

def get_surv(sym):
    s_clean = sym.upper().replace(".NS", "").strip()
    return SURV_MAP.get(s_clean, "")

# ---------- helpers: financial statements ----------
def sr(df, names):
    if df is None or getattr(df, "empty", True):
        return None
    for n in names:
        if n in df.index:
            s = df.loc[n].dropna()
            if len(s):
                return s.sort_index()
    return None

def cagr(s, years=3):
    if s is None or len(s) < years + 1:
        return None
    a, b = float(s.iloc[-years - 1]), float(s.iloc[-1])
    if a <= 0 or b <= 0:
        return None
    return ((b / a) ** (1.0 / years) - 1) * 100

def evaluate(sym, t):
    """Financials తనిఖీ. Ticker ఆబ్జెక్ట్‌ను నేరుగా వాడుకుంటుంది."""
    m = {}
    try:
        inc = t.income_stmt
    except Exception:
        return None, "Income stmt fetch failed"
        
    sales = sr(inc, ["Total Revenue", "Operating Revenue"])
    ni = sr(inc, ["Net Income", "Net Income Common Stockholders"])
    ebit = sr(inc, ["EBIT", "Operating Income"])
    
    if sales is None or ni is None or ebit is None or len(sales) < 4 or len(ni) < 4:
        return None, "Fewer than 4 years of annual data"
    if (today - sales.index[-1]).days > 550:
        return None, "Annual data is out of date"
        
    s_last, n_last = float(sales.iloc[-1]), float(ni.iloc[-1])
    if s_last <= 0:
        return None, "No sales"
    prev = float(ni.iloc[-2])
    if n_last > 0.5 * s_last or (prev > 0 and n_last / prev > 4):
        return None, "Profit looks one-time (jumped or is over half of sales)"
        
    sc = cagr(sales, 3)
    pc = cagr(ni, 3)
    if sc is None or sc < MIN_CAGR:
        return None, "Sales growth below %.0f%% a year" % MIN_CAGR
    if pc is None or pc < MIN_CAGR:
        return None, "Profit growth below %.0f%% a year" % MIN_CAGR
    m["SalesCAGR"], m["ProfitCAGR"] = sc, pc

    try:
        bs = t.balance_sheet
    except Exception:
        return None, "Balance sheet fetch failed"
        
    ta = sr(bs, ["Total Assets"])
    cl = sr(bs, ["Current Liabilities", "Total Current Liabilities"])
    if ta is None or cl is None:
        return None, "Balance sheet not available"
    ce = (ta - cl).dropna()
    common = ebit.index.intersection(ce.index)
    if len(common) < 1:
        return None, "ROCE not computable"
    ce_c = ce[common]
    ok = ce_c > 0
    roce_s = (ebit[common][ok] / ce_c[ok] * 100)
    if len(roce_s) < 1:
        return None, "ROCE not computable"
    m["ROCE"] = float(roce_s.iloc[-1])
    m["ROCEavg"] = float(roce_s.iloc[-3:].mean())
    if m["ROCE"] < MIN_ROCE:
        return None, "ROCE below 15%"

    try:
        cf = t.cashflow
    except Exception:
        cf = None
        
    ocf = sr(cf, ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"])
    if ocf is None or float(ocf.iloc[-1]) <= 0:
        return None, "Operating cash flow negative or missing"
        
    c3 = ocf.index.intersection(ni.index)[-3:]
    conv = None
    if len(c3) >= 2 and float(ni[c3].sum()) > 0:
        conv = float(ocf[c3].sum()) / float(ni[c3].sum())
    m["OCFConv"] = conv

    fcf = sr(cf, ["Free Cash Flow"])
    if fcf is None and cf is not None:
        capex = sr(cf, ["Capital Expenditure", "Purchase Of PPE"])
        if capex is not None:
            both = (ocf + capex).dropna().sort_index()
            fcf = both if len(both) else None
    m["FCFLast"] = None if fcf is None else float(fcf.iloc[-1]) / 1e7
    m["FCF3Sum"] = None
    if fcf is not None and len(fcf) >= 3:
        m["FCF3Sum"] = float(fcf.iloc[-3:].sum()) / 1e7

    rec = sr(bs, ["Accounts Receivable", "Receivables"])
    m["RecCAGR"] = cagr(rec, 3)
    
    sh = sr(bs, ["Ordinary Shares Number", "Share Issued"])
    dil = None
    if sh is not None and len(sh) >= 4 and float(sh.iloc[-4]) > 0:
        dil = (float(sh.iloc[-1]) / float(sh.iloc[-4]) - 1) * 100
    m["Dilution"] = dil

    idx = ebit.index.intersection(sales.index)
    imp = None
    if len(idx) >= 3:
        mg_last = float(ebit[idx].iloc[-1]) / float(sales[idx].iloc[-1]) * 100
        mg_old = float(ebit[idx].iloc[-3]) / float(sales[idx].iloc[-3]) * 100
        imp = mg_last - mg_old
    m["MarginChange"] = imp

    qs = qn = None
    try:
        q = t.quarterly_income_stmt
        qsr = sr(q, ["Total Revenue", "Operating Revenue"])
        qnr = sr(q, ["Net Income", "Net Income Common Stockholders"])
        if qsr is not None and len(qsr) >= 5 and float(qsr.iloc[-5]) > 0:
            qs = (float(qsr.iloc[-1]) / float(qsr.iloc[-5]) - 1) * 100
        if qnr is not None and len(qnr) >= 5 and float(qnr.iloc[-5]) > 0:
            qn = (float(qnr.iloc[-1]) / float(qnr.iloc[-5]) - 1) * 100
    except Exception:
        pass
    m["QSalesYoY"], m["QProfitYoY"] = qs, qn
    return m, ""

# ---------- దశ 2 & 3: Market Cap + Financials Evaluation ----------
rejected = []
passed = []

for s1 in stage1:
    if not time_ok():
        print("సమయ పరిమితి చేరింది, స్కానింగ్ ఆపేశాం")
        break
    sym = s1["Symbol"]
    
    if s1["RR"] < MIN_RR:
        rejected.append({"Symbol": sym, "Reason": "Reward:Risk below 1:%.1f" % MIN_RR})
        continue
        
    try:
        t = yf.Ticker(sym + ".NS")
        info = t.info or {}
    except Exception:
        info = {}
        
    mc = num(info.get("marketCap"))
    if not mc:
        # info రాకపోతే close price * shares తో బ్యాకప్ లెక్కింపు
        sh_num = num(info.get("sharesOutstanding"))
        if sh_num:
            mc = s1["Close"] * sh_num
            
    if not mc:
        rejected.append({"Symbol": sym, "Reason": "Market cap unavailable"})
        continue
        
    mcr = mc / 1e7
    if not (MCAP_MIN <= mcr <= MCAP_MAX):
        rejected.append({"Symbol": sym, "Reason": "Market cap out of range (Rs %.0f Cr)" % mcr})
        continue

    # Financials Evaluation
    try:
        m, why = evaluate(sym, t)
    except Exception as e:
        m, why = None, f"Financial evaluation error: {e}"
        
    if m is None:
        rejected.append({"Symbol": sym, "Reason": why})
    else:
        passed.append((s1, info, mcr, m))
        
    time.sleep(0.2)

print("దశ 2 & 3 తర్వాత పాస్ అయిన stocks:", len(passed))

# ---------- స్కోరింగ్ & ర్యాంకింగ్ ----------
rows = []
for s1, info, mcr, m in passed:
    sym = s1["Symbol"]
    surv_val = get_surv(sym)
    
    # Promoter holdings (Yahoo info నుండి డైరెక్ట్ గా బ్యాకప్)
    promoter = None
    insiders = num(info.get("heldPercentInsiders"))
    if insiders is not None:
        promoter = round(insiders * 100, 1)

    pledge_of_promoter = None # Yahoo లో pledge ఉండదు కాబట్టి 0 గా పరిగణించకుండా వదిలేస్తాం

    pos, warn = [], []
    score = 40.0
    
    # 20%+ వృద్ధి ఉంటే పూర్తి మార్కులు
    score += clip01((m["SalesCAGR"] - 15) / 15.0) * 8
    score += clip01((m["ProfitCAGR"] - 15) / 20.0) * 8
    score += clip01((m["ROCE"] - 15) / 20.0) * 8
    pos.append("Sales CAGR %.0f%%, Profit CAGR %.0f%%" % (m["SalesCAGR"], m["ProfitCAGR"]))
    pos.append("ROCE %.0f%% (3Y Avg %.0f%%)" % (m["ROCE"], m["ROCEavg"]))

    de = num(info.get("debtToEquity"))
    de = None if de is None else round(de / 100.0, 2)
    if de is not None:
        if de <= 0.2:
            score += 6
            pos.append("Almost debt-free (D/E %.2f)" % de)
        elif de <= 0.5:
            score += 4
            pos.append("Low debt (D/E %.2f)" % de)
        elif de <= 1.0:
            score += 1
        else:
            score -= 5
            warn.append("High debt: D/E %.2f" % de)

    if m["OCFConv"] is not None and m["OCFConv"] >= 0.7:
        score += 4
        pos.append("Strong Cash Flow Conversion")
    elif m["OCFConv"] is not None:
        warn.append("Cash flow weaker than profit")

    if m["FCFLast"] is not None and m["FCFLast"] < 0:
        warn.append("Negative Free Cash Flow last year")

    if m["QSalesYoY"] is not None and m["QSalesYoY"] >= 20:
        score += 3
        pos.append("Qtr Sales YoY +%.0f%%" % m["QSalesYoY"])
    if m["QProfitYoY"] is not None and m["QProfitYoY"] >= 20:
        score += 3
        pos.append("Qtr Profit YoY +%.0f%%" % m["QProfitYoY"])

    if promoter is not None:
        if promoter >= 50:
            score += 3
            pos.append("Promoter holds %.1f%%" % promoter)
        elif promoter < 35:
            score -= 3
            warn.append("Low Promoter holding: %.1f%%" % promoter)

    inst = num(info.get("heldPercentInstitutions"))
    inst = None if inst is None else round(inst * 100, 1)
    if inst is not None and inst < 20:
        score += 3
        pos.append("Institutions hold only %.1f%% (Early)" % inst)

    peg = num(info.get("trailingPegRatio")) or num(info.get("pegRatio"))
    if peg is not None and 0 < peg <= 1.8:
        score += 4
        pos.append("Reasonable PEG (%.2f)" % peg)

    if s1["Trend"].startswith("Above"):
        score += 3
    if s1["Ret1Y"] < 50:
        score += 3
        pos.append("1Y Return only %.0f%% (Fresh)" % s1["Ret1Y"])

    if s1["StopDistPct"] > WIDE_STOP_PCT:
        warn.append("Wide stop (%.1f%%)" % s1["StopDistPct"])

    if surv_val:
        warn.append(f"Exchange {surv_val} Surveillance")

    score = round(max(min(score, 100), 0), 1)
    if score < MIN_SCORE:
        rejected.append({"Symbol": sym, "Reason": "Score below %d" % MIN_SCORE})
        continue

    band = "High Conviction" if score >= 80 else ("Good Setup" if score >= 65 else "Early Watch")
    close = float(s1["Close"])

    rows.append({
        "Date": date_str, "Symbol": sym, "Score": score, "Band": band,
        "Close": round(close, 2), "Entry": round(close, 2),
        "Stop": round(s1["Stop"], 2), "Target": round(s1["Target"], 2),
        "StopDistPct": round(s1["StopDistPct"], 1), "TargetPct": round(s1["TargetPct"], 1),
        "RR": round(s1["RR"], 2), "StopReason": s1["StopReason"], "TargetReason": s1["TargetReason"],
        "MarketCapCr": int(mcr), "Sector": info.get("sector") or "",
        "ROCE": round(m["ROCE"], 1), "SalesCAGR3": round(m["SalesCAGR"], 1), "ProfitCAGR3": round(m["ProfitCAGR"], 1),
        "DebtEquity": "" if de is None else de,
        "QSalesYoY": "" if m["QSalesYoY"] is None else round(m["QSalesYoY"], 1),
        "QProfitYoY": "" if m["QProfitYoY"] is None else round(m["QProfitYoY"], 1),
        "PromoterPct": "" if promoter is None else round(promoter, 1),
        "PledgeOfPromoterPct": "",
        "InstPct": "" if inst is None else inst, "Analysts": num(info.get("numberOfAnalystOpinions")) or "",
        "PEG": "" if peg is None else round(peg, 2), "Ret1Y": round(s1["Ret1Y"], 1), "Trend": s1["Trend"],
        "Positives": "; ".join(pos), "Warning": "; ".join(warn),
        "Surveillance": surv_val,
        "ASM": "Yes" if surv_val == "ASM" else "",
        "GSM": "Yes" if surv_val == "GSM" else ""
    })

cols = ["Date", "Symbol", "Score", "Band", "Close", "Entry", "Stop", "Target", "StopDistPct", "TargetPct",
        "RR", "StopReason", "TargetReason",
        "MarketCapCr", "Sector", "ROCE", "SalesCAGR3", "ProfitCAGR3", "DebtEquity", "QSalesYoY", "QProfitYoY",
        "PromoterPct", "PledgeOfPromoterPct", "InstPct", "Analysts", "PEG", "Ret1Y", "Trend", "Positives", "Warning",
        "Surveillance", "ASM", "GSM"]

out = pd.DataFrame(rows, columns=cols)
if len(out):
    out = out.sort_values("Score", ascending=False)
os.makedirs("data/history", exist_ok=True)
out.to_csv("data/multibagger.csv", index=False)
out.to_csv("data/history/multi_%s.csv" % date_str, index=False)
pd.DataFrame(rejected, columns=["Symbol", "Reason"]).to_csv("data/multibagger_rejected.csv", index=False)

print("---- సారాంశం ----")
print("తుది మల్టీబ్యాగర్ స్టాక్స్ సంఖ్య:", len(out))
