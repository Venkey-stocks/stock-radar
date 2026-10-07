import os
import yfinance as yf

SYMS = ["PANAMAPET", "PTC", "HERITGFOOD", "KIRIINDUS", "GRAPHITE"]
lines = []


def log(s):
    print(s)
    lines.append(s)


def pick(df, names):
    for n in names:
        if n in df.index:
            return n
    return None


def vals(df, k):
    return [None if x != x else round(x / 1e7, 1) for x in df.loc[k].values]


for s in SYMS:
    log("==== " + s)
    t = yf.Ticker(s + ".NS")
    try:
        inc = t.income_stmt
        log("annual income: %d years, columns=%s" % (len(inc.columns), [str(c)[:10] for c in inc.columns]))
        for label, names in (("Sales", ["Total Revenue", "Operating Revenue"]),
                             ("NetProfit", ["Net Income", "Net Income Common Stockholders"]),
                             ("EBIT", ["EBIT", "Operating Income"])):
            k = pick(inc, names)
            log("  %s [%s]: %s" % (label, k, None if k is None else vals(inc, k)))
    except Exception as e:
        log("annual income FAILED: %s" % e)
    try:
        bs = t.balance_sheet
        log("balance sheet: %d years" % len(bs.columns))
        for label, names in (("TotalAssets", ["Total Assets"]),
                             ("CurrentLiab", ["Current Liabilities", "Total Current Liabilities"]),
                             ("TotalDebt", ["Total Debt"]),
                             ("Receivables", ["Accounts Receivable", "Receivables"]),
                             ("ShareCount", ["Ordinary Shares Number", "Share Issued"])):
            k = pick(bs, names)
            log("  %s [%s]: %s" % (label, k, None if k is None else vals(bs, k)))
    except Exception as e:
        log("balance sheet FAILED: %s" % e)
    try:
        cf = t.cashflow
        k = pick(cf, ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"])
        log("cash flow: %d years | OCF [%s]: %s" % (len(cf.columns), k, None if k is None else vals(cf, k)))
    except Exception as e:
        log("cash flow FAILED: %s" % e)
    try:
        q = t.quarterly_income_stmt
        k = pick(q, ["Total Revenue", "Operating Revenue"])
        log("quarterly: %d quarters | Sales [%s]: %s" % (len(q.columns), k, None if k is None else vals(q, k)))
    except Exception as e:
        log("quarterly FAILED: %s" % e)

os.makedirs("data", exist_ok=True)
with open("data/financials_test.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print("పరీక్ష పూర్తి")
