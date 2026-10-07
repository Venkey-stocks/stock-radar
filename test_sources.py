import os
import requests
import yfinance as yf

SYMS = ["RELIANCE", "LGEINDIA", "AKUMS"]
lines = []


def log(s):
    print(s)
    lines.append(s)


UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}

# ---------- NSE (cookie కోసం ముందు home page) ----------
sess = requests.Session()
sess.headers.update(UA)
try:
    r = sess.get("https://www.nseindia.com", timeout=30)
    log("NSE home page: status %s" % r.status_code)
except Exception as e:
    log("NSE home page: FAILED %s" % e)

NSE_TESTS = {
    "NSE ASM list": "https://www.nseindia.com/api/reportASM",
    "NSE GSM list": "https://www.nseindia.com/api/reportGSM",
    "NSE results calendar": "https://www.nseindia.com/api/event-calendar?index=equities",
    "NSE financial results": "https://www.nseindia.com/api/corporates-financial-results?index=equities&period=Quarterly",
    "NSE pledge data": "https://www.nseindia.com/api/corporate-pledgedata?index=equities&symbol=RELIANCE",
    "NSE shareholding": "https://www.nseindia.com/api/corporate-share-holdings-master?index=equities&symbol=RELIANCE",
    "NSE bulk deals": "https://www.nseindia.com/api/snapshot-capital-market-largedeal",
}
for name, url in NSE_TESTS.items():
    try:
        r = sess.get(url, timeout=30)
        body = r.text[:150].replace("\n", " ")
        log("%s: status %s, size %d | %s" % (name, r.status_code, len(r.text), body))
    except Exception as e:
        log("%s: FAILED %s" % (name, e))

# ---------- BSE ----------
try:
    r = requests.get("https://api.bseindia.com/BseIndiaAPI/api/ListofScripData/w?Group=&Scripcode=&industry=&segment=Equity&status=Active",
                     headers={"User-Agent": UA["User-Agent"], "Referer": "https://www.bseindia.com/"}, timeout=30)
    log("BSE script list: status %s, size %d | %s" % (r.status_code, len(r.text), r.text[:150].replace("\n", " ")))
except Exception as e:
    log("BSE script list: FAILED %s" % e)

# ---------- yfinance fundamentals ----------
for s in SYMS:
    try:
        t = yf.Ticker(s + ".NS")
        info = t.info or {}
        keys = ["marketCap", "debtToEquity", "returnOnEquity", "heldPercentInsiders",
                "heldPercentInstitutions", "earningsGrowth", "revenueGrowth", "trailingPE", "sector"]
        got = {k: info.get(k) for k in keys}
        log("yfinance info %s: %s" % (s, got))
    except Exception as e:
        log("yfinance info %s: FAILED %s" % (s, e))
    try:
        cal = yf.Ticker(s + ".NS").calendar
        log("yfinance calendar %s: %s" % (s, str(cal)[:200].replace("\n", " ")))
    except Exception as e:
        log("yfinance calendar %s: FAILED %s" % (s, e))
    try:
        q = yf.Ticker(s + ".NS").quarterly_income_stmt
        log("yfinance quarterly %s: columns=%s rows=%s" % (s, len(q.columns), len(q.index)))
    except Exception as e:
        log("yfinance quarterly %s: FAILED %s" % (s, e))

os.makedirs("data", exist_ok=True)
with open("data/source_test.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print("పరీక్ష పూర్తి")
