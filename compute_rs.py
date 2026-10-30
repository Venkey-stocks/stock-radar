import os
import pandas as pd
import numpy as np

# ట్రేడింగ్ రోజుల కాలపరిమితులు
D3 = 63     # 3 నెలలు
D6 = 126    # 6 నెలలు
D52W = 250  # 1 సంవత్సరం / 52 వారాల మాన్స్‌ఫీల్డ్ బేస్‌లైన్

# 1. స్టాక్స్ డేటా లోడ్ చేయడం
df_stocks = pd.read_csv("data/prices.csv.gz", parse_dates=["Date"])
df_stocks = df_stocks.dropna(subset=["Close"])
piv_stocks = df_stocks.pivot_table(index="Date", columns="Symbol", values="Close", aggfunc="last").sort_index()

# 2. నిఫ్టీ 500 బెంచ్‌మార్క్ డేటా లోడ్ చేయడం
nifty500_series = None
if os.path.exists("data/index.csv"):
    try:
        df_idx = pd.read_csv("data/index.csv", parse_dates=["Date"])
        df_n500 = df_idx[df_idx["Symbol"] == "NIFTY500"].sort_values("Date")
        if not df_n500.empty:
            nifty500_series = df_n500.set_index("Date")["Close"]
            print("నిఫ్టీ 500 బెంచ్‌మార్క్ డేటా విజయవంతంగా లోడ్ అయ్యింది.")
    except Exception as e:
        print("ఇండెక్స్ లోడింగ్‌లో లోపం:", e)

last_date = piv_stocks.index[-1]
print("చివరి తేదీ:", last_date.strftime("%Y-%m-%d"), "| స్టాక్స్ సంఖ్య:", piv_stocks.shape[1])

rows = []
for sym in piv_stocks.columns:
    s = piv_stocks[sym].dropna()
    
    # చివరి తేదీ డేటా లేని స్టాక్స్ మినహాయింపు
    if len(s) == 0 or s.index[-1] != last_date:
        continue

    # సాధారణ 3M, 6M పర్సంటేజ్ రిటర్న్స్
    r3 = (s.iloc[-1] / s.iloc[-(D3 + 1)] - 1) * 100 if len(s) > D3 else None
    r6 = (s.iloc[-1] / s.iloc[-(D6 + 1)] - 1) * 100 if len(s) > D6 else None

    # మాన్స్‌ఫీల్డ్ RS (Mansfield Relative Strength vs Nifty 500)
    mansfield_val = None
    if nifty500_series is not None and len(s) >= D3:
        try:
            # తేదీల ఆధారంగా స్టాక్ మరియు ఇండెక్స్ క్లోజింగ్ ప్రైస్‌లను కలపడం
            aligned = pd.concat([s.rename("Stock"), nifty500_series.rename("Index")], axis=1, join="inner").dropna()
            if len(aligned) >= 50:
                # Ratio = Stock Price / Benchmark Price
                ratio = aligned["Stock"] / aligned["Index"]
                
                # కనీస విండో పరిమాణం (లభ్యతను బట్టి 50 నుండి 250 రోజులు)
                window = min(len(ratio), D52W)
                ratio_ma = ratio.rolling(window=window, min_periods=30).mean()
                
                # మాన్స్‌ఫీల్డ్ RS సూత్రం
                if not pd.isna(ratio_ma.iloc[-1]) and ratio_ma.iloc[-1] > 0:
                    mansfield_val = ((ratio.iloc[-1] / ratio_ma.iloc[-1]) - 1) * 100
        except Exception:
            mansfield_val = None

    rows.append({
        "Symbol": sym, 
        "Ret3M": r3, 
        "Ret6M": r6, 
        "Mansfield_Raw": mansfield_val
    })

out = pd.DataFrame(rows)

# ర్యాంకింగ్ పర్సంటైల్స్ (1 నుండి 99)
out["RS3M"] = (out["Ret3M"].rank(pct=True) * 98 + 1).round()
out["RS6M"] = (out["Ret6M"].rank(pct=True) * 98 + 1).round()

# సాంప్రదాయ సగటు RS స్కోర్
out["RS"] = out[["RS3M", "RS6M"]].mean(axis=1).round()

# మాన్స్‌ఫీల్డ్ RS ర్యాంకింగ్ (0-99 స్కేల్‌పై పర్సంటైల్)
if out["Mansfield_Raw"].notna().sum() > 0:
    out["Mansfield_RS"] = (out["Mansfield_Raw"].rank(pct=True) * 98 + 1).round()
else:
    out["Mansfield_RS"] = out["RS"]

# ట్రూ లీడర్ ఫ్లాగ్: మాన్స్‌ఫీల్డ్ జీరో పైన ఉండి మరియు RS స్కోర్ >= 80 ఉంటే True
out["Is_Leader"] = (out["Mansfield_Raw"] > 0) & (out["RS"] >= 80)

# దశాంశ స్థానాల సర్దుబాటు
out["Ret3M"] = out["Ret3M"].round(1)
out["Ret6M"] = out["Ret6M"].round(1)
if "Mansfield_Raw" in out.columns:
    out["Mansfield_Raw"] = out["Mansfield_Raw"].round(2)

out["Date"] = last_date.strftime("%Y-%m-%d")

# కాలమ్స్ క్రమ అమరిక
cols = ["Date", "Symbol", "Ret3M", "Ret6M", "RS3M", "RS6M", "RS", "Mansfield_Raw", "Mansfield_RS", "Is_Leader"]
out = out[cols].sort_values("RS", ascending=False)

os.makedirs("data", exist_ok=True)
out.to_csv("data/rs_rank.csv", index=False)
print("rs_rank.csv లో మొత్తం స్టాక్స్:", len(out))
print("RS స్కోర్ లభించినవి:", int(out["RS"].notna().sum()))
print("నిజమైన మార్కెట్ లీడర్లు (RS >= 80 & Mansfield > 0):", int(out["Is_Leader"].sum()))
