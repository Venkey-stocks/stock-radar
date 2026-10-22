import io
import os
import time
import datetime
import numpy as np
import pandas as pd
import requests
import yfinance as yf

MIN_TV = 5e7            # 20 రోజుల సగటు traded value Rs 5 కోట్లు (అంచనా)
MCAP_MIN = 15000        # Rs కోట్లు, ఇంతకంటే పైన మాత్రమే
MAX_1Y_RET = 100.0      # 1 సంవత్సరంలో 100%+ పెరిగినవి వద్దు
MIN_ROCE = 15.0
MIN_ROE = 12.0          # banks/NBFC కి (అంచనా)
MIN_SALES_CAGR = 12.0
MIN_PROFIT_CAGR = 15.0
MAX_MINUTES = 150
QUICK_LIMIT = 120
MIN_SCORE = 40

# ---- Stop / Target (టెక్నికల్, అంచనా సంఖ్యలు) ----
ATR_N = 14              # ATR కాలం
SWING_LOOKBACK = 120    # swing low కోసం గత రోజులు
ATR_BUFFER = 0.5        # swing low కింద ATR బఫర్
ATR_MIN_STOP = 2.5      # stop కనీసం ఇన్ని ATR దూరం
NO_RES_ATR = 12.0       # resistance లేకపోతే target = Entry + ఇన్ని ATR
MAX_TARGET_ATR = 20.0   # target గరిష్టం
MIN_RR = 2.0            # కనీస Reward:Risk
WIDE_STOP_PCT = 20.0    # దీని కంటే stop దూరమైతే "Wide stop" హెచ్చరిక (తొలగింపు కాదు)

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

# ---------- Nifty 6 నెలల రాబడి ----------
nifty6 = None
try:
    nh = yf.Ticker("^NSEI").history(period="1y")["Close"].dropna()
    if len(nh) > 130:
        nifty6 = (float(nh.iloc[-1]) / float(nh.iloc[-127]) - 1) * 100
except Exception as e:
    print("Nifty:", e)
print("Nifty 6 నెలల రాబడి %:", "n/a" if nifty6 is None else round(nifty6, 1))

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
    ret1y = (close / c[0] - 1) * 100
    if ret1y >= MAX_1Y_RET:
        continue
    if close <= c[-200:].mean():
        continue

    # ---- ATR (14 రోజులు) ----
    pc = c[:-1]
    tr = np.maximum.reduce([h[1:] - l[1:], np.abs(h[1:] - pc), np.abs(l[1:] - pc)])
    atr = float(tr[-ATR_N:].mean())
    if atr <= 0:
        continue

    # ---- STOP: swing low కింద (ATR బఫర్), కనీసం 2.5 ATR దూరం ----
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
        stop_reason = "%s is too close; stop set %.1f ATR below entry (ATR Rs %.1f)" % (
            sw_name, ATR_MIN_STOP, atr)
    if stop <= 0 or stop >= close:
        continue
    risk = close - stop
    stop_pct = risk / close * 100

    # ---- TARGET: పైన దగ్గరి నిజమైన resistance ----
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
            target_reason = "Nearest resistance (%s Rs %.1f) is far; capped at %.0f ATR" % (
                lvl_name, lvl, MAX_TARGET_ATR)
        else:
            target = lvl
            target_reason = "Nearest resistance: %s Rs %.1f (+%.1f%%)" % (
                lvl_name, lvl, (lvl / close - 1) * 100)
    else:
        target = close + NO_RES_ATR * atr
        target_reason = "At or near the 52-week high, no overhead resistance; %.0f ATR projection (estimate)" % NO_RES_ATR
    rr = (target - close) / risk

    stage1.append({"Symbol": sym, "Close": close, "tv": tv, "Ret1Y": ret1y,
                   "Ret6M": (close / c[-127] - 1) * 100,
                   "Trend": "Above 200-day average",
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
            if "GSM" in stype:
                SURV_MAP[sym_clean] = "GSM"
            else:
                SURV_MAP[sym_clean] = "ASM"
        print("Quality: data/surveillance.csv లోడ్ అయ్యింది, stocks:", len(SURV_MAP))
    except Exception as e:
        print("surveillance.csv చదవడం విఫలమైంది:", e)

UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}
sess = requests.Session()
sess.headers.update(UA)
try:
    sess.get("https://www.nseindia.com", timeout=15)
except Exception:
    pass


def nse(url):
    for _ in range(2):
        try:
            r = sess.get(url, timeout=15)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        time.sleep(1.0)
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


asm_i, asm_s = flag_sets("https://www.nseindia.com/api/reportASM")
gsm_i, gsm_s = flag_sets("https://www.nseindia.com/api/reportGSM")
lists_ok = (len(SURV_MAP) > 0) or (asm_i is not None and gsm_i is not None)
print("Surveillance వ్యవస్థ స్థితి:", "OK" if lists_ok else "అందలేదు")


def get_surv(sym):
    s_clean = sym.upper().replace(".NS", "").strip()
    if s_clean in SURV_MAP:
        return SURV_MAP[s_clean]
    if asm_s and s_clean in asm_s:
        return "ASM"
    if gsm_s and s_clean in gsm_s:
        return "GSM"
    return ""


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


def evaluate(sym):
    """Financials తనిఖీ. తిరిగి ఇచ్చేది: (metrics లేదా None, తిరస్కరణ కారణం)"""
    t = yf.Ticker(sym + ".NS")
    m = {}
    inc = t.income_stmt
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
    if sc is None or sc < MIN_SALES_CAGR:
        return None, "Sales growth below 12% a year" if sc is not None else "Sales growth not computable"
    if pc is None or pc < MIN_PROFIT_CAGR:
        return None, "Profit growth below 15% a year" if pc is not None else "Profit not positive over 3 years"
    yo = sales.pct_change().dropna().iloc[-3:]
    if len(yo) < 3 or (yo <= 0).any() or (ni.iloc[-4:] <= 0).any():
        return None, "Sales or profit did not grow steadily every year"
    m["SalesCAGR"], m["ProfitCAGR"] = sc, pc

    bs = t.balance_sheet
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

    cf = t.cashflow
    ocf = sr(cf, ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"])
    if ocf is None:
        return None, "Cash flow not available"
    if float(ocf.iloc[-1]) <= 0:
        return None, "Operating cash flow negative"
    c3 = ocf.index.intersection(ni.index)[-3:]
    conv = None
    if len(c3) >= 2 and float(ni[c3].sum()) > 0:
        conv = float(ocf[c3].sum()) / float(ni[c3].sum())
    m["OCFConv"] = conv

    fcf = sr(cf, ["Free Cash Flow"])
    if fcf is None:
        capex = sr(cf, ["Capital Expenditure", "Purchase Of PPE"])
        if capex is not None:
            both = (ocf + capex).dropna().sort_index()
            fcf = both if len(both) else None
    m["FCFLast"] = None if fcf is None else float(fcf.iloc[-1]) / 1e7
    m["FCF3Sum"] = None
    if fcf is not None and len(fcf) >= 3:
        m["FCF3Sum"] = float(fcf.iloc[-3:].sum()) / 1e7

    rec = sr(bs, ["Accounts Receivable", "Receivables"])
    rc = cagr(rec, 3)
    m["RecCAGR"] = rc
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


def evaluate_fin(sym):
    """Banks/NBFC/financials కి: ROE + profit growth (ROCE, cash flow, debt వద్దు)"""
    t = yf.Ticker(sym + ".NS")
    m = {"IsFin": True}
    inc = t.income_stmt
    sales = sr(inc, ["Total Revenue", "Operating Revenue"])
    ni = sr(inc, ["Net Income", "Net Income Common Stockholders"])
    if ni is None or len(ni) < 4:
        return None, "Fewer than 4 years of annual data"
    if sales is None or len(sales) < 4:
        return None, "Revenue data not available (financial)"
    if (today - ni.index[-1]).days > 550:
        return None, "Annual data is out of date"
    if (ni.iloc[-4:] <= 0).any():
        return None, "Profit not positive over 3 years"
    prev, n_last = float(ni.iloc[-2]), float(ni.iloc[-1])
    if prev > 0 and n_last / prev > 4:
        return None, "Profit looks one-time (jumped or is over half of sales)"
    sc = cagr(sales, 3)
    pc = cagr(ni, 3)
    if sc is None or sc < MIN_SALES_CAGR:
        return None, "Sales growth below 12% a year" if sc is not None else "Sales growth not computable"
    if pc is None or pc < MIN_PROFIT_CAGR:
        return None, "Profit growth below 15% a year" if pc is not None else "Profit not positive over 3 years"
    m["SalesCAGR"], m["ProfitCAGR"] = sc, pc

    bs = t.balance_sheet
    eq = sr(bs, ["Stockholders Equity", "Common Stock Equity", "Total Equity Gross Minority Interest"])
    if eq is None:
        return None, "Balance sheet not available"
    common = ni.index.intersection(eq.index)
    if len(common) < 1:
        return None, "ROE not computable"
    eq_c = eq[common]
    ok = eq_c > 0
    roe_s = (ni[common][ok] / eq_c[ok] * 100)
    if len(roe_s) < 1:
        return None, "ROE not computable"
    m["ROCE"] = float(roe_s.iloc[-1])      # financials కి ఇది ROE
    m["ROCEavg"] = float(roe_s.iloc[-3:].mean())
    if m["ROCE"] < MIN_ROE:
        return None, "ROE below 12%"

    m["OCFConv"] = None
    m["FCFLast"] = None
    m["FCF3Sum"] = None
    m["RecCAGR"] = None
    m["MarginChange"] = None
    sh = sr(bs, ["Ordinary Shares Number", "Share Issued"])
    dil = None
    if sh is not None and len(sh) >= 4 and float(sh.iloc[-4]) > 0:
        dil = (float(sh.iloc[-1]) / float(sh.iloc[-4]) - 1) * 100
    m["Dilution"] = dil

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


# ---------- దశ 2: market cap ----------
rejected = []
pool = []
n_nomcap = 0
for s1 in stage1:
    if not time_ok():
        print("సమయ పరిమితి చేరింది, దశ 2 ఆపేశాం")
        break
    sym = s1["Symbol"]
    try:
        info = yf.Ticker(sym + ".NS").info or {}
    except Exception:
        info = {}
    mc = num(info.get("marketCap"))
    if not mc:
        n_nomcap += 1
        rejected.append({"Symbol": sym, "Reason": "Market cap not available (Yahoo)"})
        continue
    mcr = mc / 1e7
    if mcr >= MCAP_MIN:
        pool.append((s1, info, mcr))
    time.sleep(0.2)
print("దశ 2 తర్వాత (market cap Rs 15,000 కోట్లు పైన):", len(pool), "| market cap తెలియనివి:", n_nomcap)

# ---------- దశ 3: Reward:Risk, తర్వాత financials ----------
passed = []
n_fin = 0
for s1, info, mcr in pool:
    if not time_ok():
        print("సమయ పరిమితి చేరింది, దశ 3 ఆపేశాం")
        break
    sym = s1["Symbol"]
    if s1["RR"] < MIN_RR:
        rejected.append({"Symbol": sym, "Reason": "Reward:Risk below 1:%.0f" % MIN_RR})
        continue
    fin = (info.get("sector") or "") == "Financial Services"
    try:
        if fin:
            n_fin += 1
            m, why = evaluate_fin(sym)
        else:
            m, why = evaluate(sym)
    except Exception:
        m, why = None, "Financial data error"
    if m is None:
        rejected.append({"Symbol": sym, "Reason": why})
    else:
        passed.append((s1, info, mcr, m))
    time.sleep(0.3)
print("దశ 3 తర్వాత (Reward:Risk + financials నియమాలు):", len(passed), "| Financial Services stocks:", n_fin)

# ---------- NSE promoter / pledge, score ----------
rows = []
for s1, info, mcr, m in passed:
    sym = s1["Symbol"]
    surv_val = get_surv(sym)
    isfin = bool(m.get("IsFin"))
    promoter, pledge_of_promoter = None, None
    shd = nse("https://www.nseindia.com/api/corporate-share-holdings-master?index=equities&symbol=" + sym)
    try:
        recs = shd["data"] if isinstance(shd, dict) and "data" in shd else shd
        if isinstance(recs, list) and recs:
            recs = sorted(recs, key=lambda x: pd.to_datetime(x.get("date"), errors="coerce"), reverse=True)
            promoter = num(recs[0].get("pr_and_prgrp"))
    except Exception:
        pass
    pl = nse("https://www.nseindia.com/api/corporate-pledgedata?index=equities&symbol=" + sym)
    try:
        data = pl.get("data") if isinstance(pl, dict) else None
        if data:
            pp = num(data[0].get("percSharesPledged"))
            if pp is not None and promoter:
                pledge_of_promoter = round(pp / promoter * 100, 1)
    except Exception:
        pass
    time.sleep(0.4)

    pos, warn = [], []
    score = 40.0
    score += clip01((m["SalesCAGR"] - 12) / 18.0) * 8
    score += clip01((m["ProfitCAGR"] - 15) / 25.0) * 8
    if isfin:
        score += clip01((m["ROCE"] - 12) / 13.0) * 8
    else:
        score += clip01((m["ROCE"] - 15) / 20.0) * 8
    pos.append("Sales grew %.0f%% a year and profit %.0f%% a year over 3 years, rising every year" % (m["SalesCAGR"], m["ProfitCAGR"]))
    if isfin:
        pos.append("ROE %.0f%% (3-year average %.0f%%). Bank/NBFC: judged on ROE and profit growth, not ROCE, debt or cash flow" % (m["ROCE"], m["ROCEavg"]))
    else:
        pos.append("ROCE %.0f%% (3-year average %.0f%%)" % (m["ROCE"], m["ROCEavg"]))

    de = num(info.get("debtToEquity"))
    de = None if (de is None or isfin) else round(de / 100.0, 2)
    if de is not None:
        if de <= 0.2:
            score += 6
            pos.append("Almost debt-free (debt/equity %.2f)" % de)
        elif de <= 0.5:
            score += 4
            pos.append("Low debt (debt/equity %.2f)" % de)
        elif de <= 1.0:
            score += 1
        else:
            score -= 5
            warn.append("High debt: debt/equity %.2f" % de)
    if m["OCFConv"] is not None and m["OCFConv"] >= 0.7:
        score += 4
        pos.append("Profit is backed by real cash flow")
    elif m["OCFConv"] is not None:
        warn.append("Cash flow is weak compared with profit")

    if isfin:
        pass
    elif m["FCFLast"] is None:
        warn.append("Free cash flow: n/a (not available)")
    elif m["FCF3Sum"] is not None and m["FCF3Sum"] < 0:
        warn.append("Free cash flow negative over the last 3 years (total Rs %.0f crore, last year Rs %.0f crore). Check capex and funding before buying" % (m["FCF3Sum"], m["FCFLast"]))
    elif m["FCFLast"] < 0:
        warn.append("Free cash flow negative last year (Rs %.0f crore), check capex" % m["FCFLast"])

    if m["QSalesYoY"] is not None and m["QSalesYoY"] >= 15:
        score += 3
        pos.append("Latest quarter sales up %.0f%% year on year" % m["QSalesYoY"])
    if m["QProfitYoY"] is not None and m["QProfitYoY"] >= 15:
        score += 3
        pos.append("Latest quarter profit up %.0f%% year on year" % m["QProfitYoY"])
    if m["QSalesYoY"] is not None and m["QSalesYoY"] > 100:
        warn.append("Latest quarter sales more than doubled; please verify (one-time item or data issue?)")
    if m["ProfitCAGR"] > 100 or (m["QProfitYoY"] is not None and m["QProfitYoY"] > 150):
        warn.append("Base effect: very high profit growth (3-year %.0f%% a year) may come from a low starting base. Check absolute profit on screener.in" % m["ProfitCAGR"])
    if m["MarginChange"] is not None and m["MarginChange"] > 0.5:
        score += 3
        pos.append("Operating margin improved over 2 years")
    if promoter is not None:
        if promoter >= 50:
            score += 3
            pos.append("Promoter holds %.1f%%" % promoter)
        elif promoter < 25:
            score -= 3
            warn.append("Promoter holding only %.1f%%" % promoter)
    if pledge_of_promoter is not None:
        if pledge_of_promoter >= 25:
            score -= 10
            warn.append("High promoter pledge: %.1f%% of promoter shares" % pledge_of_promoter)
        elif pledge_of_promoter >= 10:
            score -= 5
            warn.append("Promoter pledge %.1f%% of promoter shares" % pledge_of_promoter)
        elif pledge_of_promoter <= 5:
            score += 2
    else:
        warn.append("Promoter pledge: n/a (not reported)")
    inst = num(info.get("heldPercentInstitutions"))
    inst = None if inst is None else round(inst * 100, 1)
    if inst is not None and inst >= 20:
        score += 3
        pos.append("Institutions hold %.1f%% (professional backing)" % inst)
    ana = num(info.get("numberOfAnalystOpinions"))
    peg = num(info.get("trailingPegRatio")) or num(info.get("pegRatio"))
    if peg is not None and peg > 0:
        if peg <= 1.5:
            score += 4
            pos.append("PEG %.2f (price reasonable for the growth)" % peg)
        elif peg > 2.5:
            score -= 3
            warn.append("PEG %.2f looks expensive for the growth" % peg)
    rs = None if nifty6 is None else s1["Ret6M"] - nifty6
    if rs is not None:
        if rs >= 10:
            score += 5
            pos.append("Beat Nifty by %.0f%% over 6 months (strong relative price)" % rs)
        elif rs >= 0:
            score += 2
            pos.append("Ahead of Nifty over 6 months")
        elif rs < -10:
            score -= 3
            warn.append("Lagging Nifty by %.0f%% over 6 months" % abs(rs))
    if s1["Ret1Y"] < 50:
        score += 3
        pos.append("Up only %.0f%% in 1 year (not stretched)" % s1["Ret1Y"])
    if m["Dilution"] is not None and m["Dilution"] > 5:
        score -= 8
        warn.append("Share count rose %.1f%% in 3 years (dilution)" % m["Dilution"])
    if m["RecCAGR"] is not None and m["RecCAGR"] > m["SalesCAGR"] + 10:
        score -= 5
        warn.append("Receivables growing faster than sales")
    if s1["StopDistPct"] > WIDE_STOP_PCT:
        warn.append("Wide stop (%.1f%% away); position size should be small" % s1["StopDistPct"])
    
    if surv_val:
        warn.append(f"Exchange {surv_val} Surveillance (100% Margin / Circuit risk)")

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
        "PledgeOfPromoterPct": "" if pledge_of_promoter is None else pledge_of_promoter,
        "InstPct": "" if inst is None else inst, "Analysts": "" if ana is None else int(ana),
        "PEG": "" if peg is None else round(peg, 2), "Ret1Y": round(s1["Ret1Y"], 1), "Trend": s1["Trend"],
        "RS6M": "" if rs is None else round(rs, 1),
        "Positives": "; ".join(pos), "Warning": "; ".join(warn),
        "Surveillance": surv_val,
        "ASM": "Yes" if surv_val == "ASM" else "",
        "GSM": "Yes" if surv_val == "GSM" else ""
    })

cols = ["Date", "Symbol", "Score", "Band", "Close", "Entry", "Stop", "Target", "StopDistPct", "TargetPct",
        "RR", "StopReason", "TargetReason",
        "MarketCapCr", "Sector", "ROCE", "SalesCAGR3", "ProfitCAGR3", "DebtEquity", "QSalesYoY", "QProfitYoY",
        "PromoterPct", "PledgeOfPromoterPct", "InstPct", "Analysts", "PEG", "Ret1Y", "Trend", "RS6M",
        "Positives", "Warning", "Surveillance", "ASM", "GSM"]
out = pd.DataFrame(rows, columns=cols)
if len(out):
    out = out.sort_values("Score", ascending=False)
os.makedirs("data/history", exist_ok=True)
out.to_csv("data/quality.csv", index=False)
out.to_csv("data/history/quality_%s.csv" % date_str, index=False)
pd.DataFrame(rejected, columns=["Symbol", "Reason"]).to_csv("data/quality_rejected.csv", index=False)

print("---- సారాంశం ----")
print("తుది ఫలితాలు:", len(out))
rj = pd.DataFrame(rejected, columns=["Symbol", "Reason"])
if len(rj):
    print("తిరస్కరణ కారణాలు:")
    print(rj["Reason"].value_counts().to_string())
if len(out):
    print(out.head(10)[["Symbol", "Score", "ROCE", "SalesCAGR3", "ProfitCAGR3", "MarketCapCr", "RR", "Surveillance"]].to_string(index=False))
print("సమయం: %.1f నిమిషాలు" % ((time.time() - START) / 60.0))
