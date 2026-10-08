import io
import os
import time
import datetime
import pandas as pd
import requests
import yfinance as yf

# ================= మీరు మార్చవలసిన సంఖ్య =================
CAPITAL = 100000   # <-- మీ నిజమైన capital ఇక్కడ మార్చండి
# ==========================================================

RISK_PCT = 0.01
MIN_TV = 2e7            # 20 రోజుల సగటు traded value Rs 2 కోట్లు
MCAP_MIN = 500          # Rs కోట్లు
MCAP_MAX = 15000
MAX_1Y_RET = 100.0      # 1 సంవత్సరంలో 100%+ పెరిగినవి వద్దు
MIN_ROCE = 15.0
MIN_CAGR = 20.0
MAX_MINUTES = 150       # భద్రత కోసం గరిష్ట సమయం
QUICK_LIMIT = 120       # quick test లో ఎన్ని stocks
MIN_SCORE = 40

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

# ---------- దశ 1: ధర filters ----------
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
    sma200 = c[-200:].mean()
    depth = (h[-30:].max() - l[-30:].min()) / h[-30:].max()
    above = close > sma200
    near_base = close >= 0.9 * sma200 and depth <= 0.25
    if not (above or near_base):
        continue
    stage1.append({"Symbol": sym, "Close": close, "tv": tv, "Ret1Y": ret1y,
                   "Trend": "Above 200-day average" if above else "Near a base below 200-day average",
                   "Low120": l[-120:].min()})
stage1.sort(key=lambda x: -x["tv"])
print("దశ 1 తర్వాత:", len(stage1))
if QUICK:
    stage1 = stage1[:QUICK_LIMIT]
    print("QUICK: మొదటి", len(stage1), "stocks మాత్రమే")

# ---------- NSE: ISIN map, ASM/GSM ----------
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

asm_i, asm_s = flag_sets("https://www.nseindia.com/api/reportASM")
gsm_i, gsm_s = flag_sets("https://www.nseindia.com/api/reportGSM")
lists_ok = asm_i is not None and gsm_i is not None
print("ASM/GSM lists:", "OK" if lists_ok else "అందలేదు")


def flagged(sym):
    isin = isin_of.get(sym)
    if asm_i is not None and (isin in asm_i or sym in asm_s):
        return "ASM list"
    if gsm_i is not None and (isin in gsm_i or sym in gsm_s):
        return "GSM list"
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
    if sc is None or sc < MIN_CAGR:
        return None, "Sales growth below 20% a year" if sc is not None else "Sales growth not computable"
    if pc is None or pc < MIN_CAGR:
        return None, "Profit growth below 20% a year" if pc is not None else "Profit not positive over 3 years"
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

    # ---- Free Cash Flow (హెచ్చరిక కోసం మాత్రమే, తొలగింపు కాదు) ----
    fcf = sr(cf, ["Free Cash Flow"])
    if fcf is None:
        capex = sr(cf, ["Capital Expenditure", "Purchase Of PPE"])
        if capex is not None:
            both = (ocf + capex).dropna().sort_index()
            fcf = both if len(both) else None
    m["FCFLast"] = None if fcf is None else float(fcf.iloc[-1]) / 1e7      # Rs కోట్లు
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


# ---------- దశ 2: market cap ----------
rejected = []
pool = []
n_nomcap = 0
for s1 in stage1:
    if not time_ok():
        print("సమయ పరిమితి చేరింది, దశ 2 ఆపేశాం")
        break
    sym = s1["Symbol"]
    why = flagged(sym)
    if why:
        rejected.append({"Symbol": sym, "Reason": why})
        continue
    try:
        info = yf.Ticker(sym + ".NS").info or {}
    except Exception:
        info = {}
    mc = num(info.get("marketCap"))
    if not mc:
        n_nomcap += 1
        continue
    mcr = mc / 1e7
    if MCAP_MIN <= mcr <= MCAP_MAX:
        pool.append((s1, info, mcr))
    time.sleep(0.2)
print("దశ 2 తర్వాత (market cap Rs 500-15,000 కోట్లు):", len(pool), "| market cap తెలియనివి:", n_nomcap)

# ---------- దశ 3: financials ----------
passed = []
for s1, info, mcr in pool:
    if not time_ok():
        print("సమయ పరిమితి చేరింది, దశ 3 ఆపేశాం")
        break
    sym = s1["Symbol"]
    try:
        m, why = evaluate(sym)
    except Exception as e:
        m, why = None, "Financial data error"
    if m is None:
        rejected.append({"Symbol": sym, "Reason": why})
    else:
        passed.append((s1, info, mcr, m))
    time.sleep(0.3)
print("దశ 3 తర్వాత (financials తప్పనిసరి నియమాలు):", len(passed))

# ---------- NSE promoter / pledge, score ----------
rows = []
for s1, info, mcr, m in passed:
    sym = s1["Symbol"]
    promoter, pledge_of_promoter = None, None
    sh = nse("https://www.nseindia.com/api/corporate-share-holdings-master?index=equities&symbol=" + sym)
    try:
        recs = sh["data"] if isinstance(sh, dict) and "data" in sh else sh
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
    score += clip01((m["SalesCAGR"] - 20) / 20.0) * 8
    score += clip01((m["ProfitCAGR"] - 20) / 30.0) * 8
    score += clip01((m["ROCE"] - 15) / 20.0) * 8
    pos.append("Sales grew %.0f%% a year and profit %.0f%% a year over 3 years" % (m["SalesCAGR"], m["ProfitCAGR"]))
    pos.append("ROCE %.0f%% (3-year average %.0f%%)" % (m["ROCE"], m["ROCEavg"]))

    de = num(info.get("debtToEquity"))
    de = None if de is None else round(de / 100.0, 2)
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

    # ---- Free Cash Flow హెచ్చరికలు (score మారదు) ----
    if m["FCFLast"] is None:
        warn.append("Free cash flow: n/a (not available)")
    elif m["FCF3Sum"] is not None and m["FCF3Sum"] < 0:
        warn.append("Free cash flow negative over the last 3 years (total Rs %.0f crore, last year Rs %.0f crore). Heavy spending is eating the cash; check capex and funding before buying" % (m["FCF3Sum"], m["FCFLast"]))
    elif m["FCFLast"] < 0:
        warn.append("Free cash flow negative last year (Rs %.0f crore), check capex" % m["FCFLast"])

     if m["QSalesYoY"] is not None and m["QSalesYoY"] >= 20:
        score += 3
        pos.append("Latest quarter sales up %.0f%% year on year" % m["QSalesYoY"])
    if m["QProfitYoY"] is not None and m["QProfitYoY"] >= 20:
        score += 3
        pos.append("Latest quarter profit up %.0f%% year on year" % m["QProfitYoY"])
    if m["QSalesYoY"] is not None and m["QSalesYoY"] > 100:
        warn.append("Latest quarter sales more than doubled; please verify (one-time item or data issue?)")
    if m["MarginChange"] is not None and m["MarginChange"] > 0.5:
        score += 3
        pos.append("Operating margin improved over 2 years")
    if promoter is not None:
        if promoter >= 50:
            score += 3
            pos.append("Promoter holds %.1f%%" % promoter)
        elif promoter < 40:
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
    if inst is not None and inst < 15:
        score += 3
        pos.append("Institutions hold only %.1f%% (not crowded yet)" % inst)
    ana = num(info.get("numberOfAnalystOpinions"))
    if ana is not None and ana <= 3:
        score += 3
        pos.append("Few analysts cover it")
    peg = num(info.get("trailingPegRatio")) or num(info.get("pegRatio"))
    if peg is not None and peg > 0:
        if peg <= 1.5:
            score += 4
            pos.append("PEG %.2f (price reasonable for the growth)" % peg)
        elif peg > 2.5:
            score -= 3
            warn.append("PEG %.2f looks expensive for the growth" % peg)
    if s1["Trend"].startswith("Above"):
        score += 3
    if s1["Ret1Y"] < 50:
        score += 3
        pos.append("Up only %.0f%% in 1 year (still early)" % s1["Ret1Y"])
    if m["Dilution"] is not None and m["Dilution"] > 5:
        score -= 8
        warn.append("Share count rose %.1f%% in 3 years (dilution)" % m["Dilution"])
    if m["RecCAGR"] is not None and m["RecCAGR"] > m["SalesCAGR"] + 10:
        score -= 5
        warn.append("Receivables growing faster than sales")
    if not lists_ok:
        warn.append("ASM/GSM list could not be checked")
    score = round(max(min(score, 100), 0), 1)
    if score < MIN_SCORE:
        rejected.append({"Symbol": sym, "Reason": "Score below %d" % MIN_SCORE})
        continue
    band = "High Conviction" if score >= 80 else ("Good Setup" if score >= 65 else "Early Watch")

    close = float(s1["Close"])
    struct = (close - s1["Low120"] * 0.98) / close
    stop_pct = min(max(struct, 0.20), 0.25)
    stop = close * (1 - stop_pct)
    risk = close - stop
    target = close + 2 * risk
    qty = int(max(min(CAPITAL * RISK_PCT / risk, CAPITAL / close), 0))
    rows.append({
        "Date": date_str, "Symbol": sym, "Score": score, "Band": band,
        "Close": round(close, 2), "Entry": round(close, 2), "Stop": round(stop, 2), "Target": round(target, 2),
        "StopDistPct": round(stop_pct * 100, 1), "TargetPct": round((target / close - 1) * 100, 1), "Qty": qty,
        "MarketCapCr": int(mcr), "Sector": info.get("sector") or "",
        "ROCE": round(m["ROCE"], 1), "SalesCAGR3": round(m["SalesCAGR"], 1), "ProfitCAGR3": round(m["ProfitCAGR"], 1),
        "DebtEquity": "" if de is None else de,
        "QSalesYoY": "" if m["QSalesYoY"] is None else round(m["QSalesYoY"], 1),
        "QProfitYoY": "" if m["QProfitYoY"] is None else round(m["QProfitYoY"], 1),
        "PromoterPct": "" if promoter is None else round(promoter, 1),
        "PledgeOfPromoterPct": "" if pledge_of_promoter is None else pledge_of_promoter,
        "InstPct": "" if inst is None else inst, "Analysts": "" if ana is None else int(ana),
        "PEG": "" if peg is None else round(peg, 2), "Ret1Y": round(s1["Ret1Y"], 1), "Trend": s1["Trend"],
        "Positives": "; ".join(pos), "Warning": "; ".join(warn),
    })

cols = ["Date", "Symbol", "Score", "Band", "Close", "Entry", "Stop", "Target", "StopDistPct", "TargetPct", "Qty",
        "MarketCapCr", "Sector", "ROCE", "SalesCAGR3", "ProfitCAGR3", "DebtEquity", "QSalesYoY", "QProfitYoY",
        "PromoterPct", "PledgeOfPromoterPct", "InstPct", "Analysts", "PEG", "Ret1Y", "Trend", "Positives", "Warning"]
out = pd.DataFrame(rows, columns=cols)
if len(out):
    out = out.sort_values("Score", ascending=False)
os.makedirs("data/history", exist_ok=True)
out.to_csv("data/multibagger.csv", index=False)
out.to_csv("data/history/multi_%s.csv" % date_str, index=False)
pd.DataFrame(rejected, columns=["Symbol", "Reason"]).to_csv("data/multibagger_rejected.csv", index=False)

print("---- సారాంశం ----")
print("తుది ఫలితాలు:", len(out))
rj = pd.DataFrame(rejected, columns=["Symbol", "Reason"])
if len(rj):
    print("తిరస్కరణ కారణాలు:")
    print(rj["Reason"].value_counts().to_string())
if len(out):
    print(out.head(10)[["Symbol", "Score", "ROCE", "SalesCAGR3", "ProfitCAGR3", "MarketCapCr"]].to_string(index=False))
print("సమయం: %.1f నిమిషాలు" % ((time.time() - START) / 60.0))
