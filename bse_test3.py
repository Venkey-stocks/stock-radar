import io
import datetime
import requests
import pandas as pd
import yfinance as yf

H = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Referer": "https://www.bseindia.com/",
    "Accept": "*/*",
}


def get_bhav():
    today = datetime.date.today()
    for i in range(8):
        day = today - datetime.timedelta(days=i)
        if day.weekday() >= 5:
            continue
        url = "https://www.bseindia.com/download/BhavCopy/Equity/BhavCopy_BSE_CM_0_0_0_%s_F_0000.CSV" % day.strftime("%Y%m%d")
        try:
            r = requests.get(url, headers=H, timeout=60)
        except Exception as e:
            print("ERR", day, str(e)[:100])
            continue
        if r.status_code == 200 and r.content[:6] == b"TradDt":
            return day, pd.read_csv(io.BytesIO(r.content))
    return None, None


day, df = get_bhav()
if df is None:
    print("RESULT: BHAVCOPY FAILED")
    raise SystemExit

print("DATE:", day, "ROWS:", len(df))
print("INSTR TYPES:", df["FinInstrmTp"].value_counts().head(8).to_dict())
print("SERIES:", df["SctySrs"].value_counts().head(10).to_dict())

df["ISIN"] = df["ISIN"].astype(str)
df["ClsPric"] = pd.to_numeric(df["ClsPric"], errors="coerce")
df["TtlTrfVal"] = pd.to_numeric(df["TtlTrfVal"], errors="coerce")

# కంపెనీ equity ISIN అంచనా: INE తో మొదలై 8-9 అక్షరాలు "01"
eq = df[df["ISIN"].str.startswith("INE") & (df["ISIN"].str[7:9] == "01")]
print("EQUITY-LIKE ROWS:", len(eq))

ok = eq[(eq["ClsPric"] >= 50) & (eq["TtlTrfVal"] >= 1e8)]
print("PASS FILTERS (price 50+, value 10cr+):", len(ok))

# NSE ISIN జాబితా
nse = set()
try:
    r = requests.get("https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv", headers=H, timeout=40)
    print("NSE LIST STATUS:", r.status_code, "LEN:", len(r.content))
    if r.status_code == 200:
        n = pd.read_csv(io.BytesIO(r.content))
        n.columns = [c.strip() for c in n.columns]
        print("NSE COLUMNS:", list(n.columns))
        nse = set(n["ISIN NUMBER"].astype(str).str.strip())
        print("NSE ISINS:", len(nse))
except Exception as e:
    print("NSE LIST ERROR:", str(e)[:150])

if nse:
    only = ok[~ok["ISIN"].isin(nse)]
    print("BSE-ONLY ALL (equity-like):", len(eq[~eq["ISIN"].isin(nse)]))
    print("BSE-ONLY PASSING FILTERS:", len(only))
    sample = only.head(6)
else:
    sample = ok.head(6)

print("SAMPLE:")
for _, row in sample.iterrows():
    print(row["TckrSymb"], row["FinInstrmId"], row["ISIN"], row["ClsPric"], row["TtlTrfVal"])

print("YAHOO HISTORY TEST:")
for _, row in sample.iterrows():
    for t in [str(row["TckrSymb"]), str(row["FinInstrmId"])]:
        try:
            h = yf.download(t + ".BO", period="1y", progress=False, auto_adjust=False)
            print(t + ".BO rows:", len(h))
        except Exception as e:
            print(t + ".BO error:", str(e)[:80])
