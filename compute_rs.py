import os
import pandas as pd

# RS rank: అన్ని stocks లో 3 నెలలు / 6 నెలల పనితీరు percentile (1-99, 99 = బలమైనది)
D3 = 63    # 3 నెలలు (అంచనా trading days)
D6 = 126   # 6 నెలలు (అంచనా trading days)

df = pd.read_csv("data/prices.csv.gz", parse_dates=["Date"])
df = df.dropna(subset=["Close"])
piv = df.pivot_table(index="Date", columns="Symbol", values="Close", aggfunc="last").sort_index()
last_date = piv.index[-1]
print("చివరి తేదీ:", last_date.strftime("%Y-%m-%d"), "| stocks:", piv.shape[1])

rows = []
for sym in piv.columns:
    s = piv[sym].dropna()
    # చివరి తేదీ డేటా లేని (పాత/ఆగిపోయిన) stocks వద్దు
    if len(s) == 0 or s.index[-1] != last_date:
        continue
    r3 = (s.iloc[-1] / s.iloc[-(D3 + 1)] - 1) * 100 if len(s) > D3 else None
    r6 = (s.iloc[-1] / s.iloc[-(D6 + 1)] - 1) * 100 if len(s) > D6 else None
    rows.append({"Symbol": sym, "Ret3M": r3, "Ret6M": r6})

out = pd.DataFrame(rows)
out["RS3M"] = (out["Ret3M"].rank(pct=True) * 98 + 1).round()
out["RS6M"] = (out["Ret6M"].rank(pct=True) * 98 + 1).round()
# RS = రెండు ర్యాంకుల సగటు (ఒకటే ఉంటే అదే; రెండూ లేకపోతే ఖాళీ = n/a)
out["RS"] = out[["RS3M", "RS6M"]].mean(axis=1).round()
out["Ret3M"] = out["Ret3M"].round(1)
out["Ret6M"] = out["Ret6M"].round(1)
out["Date"] = last_date.strftime("%Y-%m-%d")
out = out[["Date", "Symbol", "Ret3M", "Ret6M", "RS3M", "RS6M", "RS"]]
out = out.sort_values("RS", ascending=False)

os.makedirs("data", exist_ok=True)
out.to_csv("data/rs_rank.csv", index=False)
print("rs_rank.csv లో stocks:", len(out))
print("RS ఉన్నవి:", int(out["RS"].notna().sum()))
