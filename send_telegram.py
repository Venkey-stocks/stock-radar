import os
import json
import pandas as pd
import requests

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
STATUS = os.environ.get("JOB_STATUS", "success")


def col(df, names):
    low = {c.lower().replace(" ", "").replace("_", ""): c for c in df.columns}
    for n in names:
        if n in low:
            return low[n]
    return None


def fmt(v):
    if v is None:
        return "n/a"
    try:
        if pd.isna(v):
            return "n/a"
    except Exception:
        pass
    if isinstance(v, float):
        return f"{v:.1f}"
    return str(v)


def event_line(r, c_evt, c_adj):
    """Events ఉంటే ఒక లైన్ (boost అయితే Events, penalty అయితే warning)."""
    if not c_evt:
        return ""
    try:
        txt = r[c_evt]
        if pd.isna(txt) or str(txt).strip() == "":
            return ""
        txt = str(txt).strip()
    except Exception:
        return ""
    adj = 0
    if c_adj:
        try:
            adj = int(float(r[c_adj]))
        except Exception:
            adj = 0
    if adj < 0:
        return f"   WARNING events: {txt} (score {adj:+d})"
    return f"   Events: {txt} (score {adj:+d})"


def top_lines(path, title):
    try:
        df = pd.read_csv(path)
    except Exception:
        return [f"{title}: data file not readable"]
    dt = col(df, ["date", "scandate", "asof"])
    if dt and len(df) > 0:
        df = df[df[dt] == df[dt].max()]
    st = col(df, ["status"])
    if st:
        df = df[~df[st].astype(str).str.lower().str.contains("near")]
    if len(df) == 0:
        return [f"{title}: no signals today"]
    sc = col(df, ["score"])
    if sc:
        df = df.sort_values(sc, ascending=False)
    c_sym = col(df, ["symbol", "stock", "ticker", "name"])
    c_ent = col(df, ["entry", "entryprice", "buy", "buyprice"])
    c_stp = col(df, ["stop", "stoploss", "sl"])
    c_tgt = col(df, ["target", "targetprice"])
    c_set = col(df, ["setup"])
    c_evt = col(df, ["events"])
    c_adj = col(df, ["eventadj"])
    lines = [f"{title}: {len(df)} signals (top 3)"]
    for i, (_, r) in enumerate(df.head(3).iterrows(), 1):
        sym = fmt(r[c_sym]) if c_sym else "n/a"
        ent = fmt(r[c_ent]) if c_ent else "n/a"
        stp = fmt(r[c_stp]) if c_stp else "n/a"
        tgt = fmt(r[c_tgt]) if c_tgt else "n/a"
        scr = fmt(r[sc]) if sc else "n/a"
        extra = ""
        if c_set:
            extra = " | " + fmt(r[c_set])
        lines.append(
            f"{i}. {sym} | Entry {ent} | Stop {stp} | Target {tgt} | Score {scr}{extra}"
        )
        ev = event_line(r, c_evt, c_adj)
        if ev:
            lines.append(ev)
    return lines


def health():
    try:
        with open("data/market_health.json") as f:
            d = json.load(f)
    except Exception:
        return "Market Health: n/a"
    score = None
    label = None
    if isinstance(d, dict):
        for k, v in d.items():
            kl = k.lower()
            if score is None and "score" in kl and isinstance(v, (int, float)):
                score = v
            if label is None and kl in (
                "label", "status", "state", "regime", "verdict", "condition"
            ):
                label = v
    parts = []
    if label is not None:
        parts.append(str(label))
    if score is not None:
        parts.append(f"{score}/100")
    return "Market Health: " + (" ".join(parts) if parts else "n/a")


def main():
    if not TOKEN or not CHAT_ID:
        print("Telegram secrets missing, skipping")
        return
    if STATUS != "success":
        msg = (
            "WARNING: today's data run had a problem "
            f"(status: {STATUS}). Please check GitHub Actions."
        )
    else:
        lines = ["Stock Radar - daily summary", health(), ""]
        lines += top_lines("data/ultra_short.csv", "Ultra Short")
        lines.append("")
        lines += top_lines("data/short_term.csv", "Short Term")
        lines.append("")
        lines.append("End-of-day data, may be wrong or delayed. Verify on screener.in before buying. Research tool, not advice.")
        msg = "\n".join(lines)
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    r = requests.post(url, data={"chat_id": CHAT_ID, "text": msg}, timeout=30)
    print("Telegram status:", r.status_code)


main()
