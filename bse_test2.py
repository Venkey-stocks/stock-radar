import requests
import datetime

H = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Referer": "https://www.bseindia.com/",
    "Accept": "*/*",
}


def show(name, url):
    print("=" * 55)
    print("TEST:", name)
    print("URL:", url)
    try:
        r = requests.get(url, headers=H, timeout=40)
        print("STATUS:", r.status_code)
        print("LENGTH:", len(r.content))
        print("START:", r.text[:250].replace("\n", " | "))
        return r.status_code == 200 and len(r.content) > 2000
    except Exception as e:
        print("ERROR:", str(e)[:200])
        return False


# Test A: BSE scrip list API (headers తో)
show(
    "A: BSE scrip list API",
    "https://api.bseindia.com/BseIndiaAPI/api/ListofScripData/w?Group=&Scripcode=&industry=&segment=Equity&status=Active",
)

# Test B: BSE Bhavcopy (కొత్త పద్ధతి), గత 6 రోజుల్లో మొదటిది
found_new = False
found_old = False
d = datetime.date.today()
for i in range(7):
    day = d - datetime.timedelta(days=i)
    if day.weekday() >= 5:
        continue
    if not found_new:
        u = "https://www.bseindia.com/download/BhavCopy/Equity/BhavCopy_BSE_CM_0_0_0_%s_F_0000.CSV" % day.strftime("%Y%m%d")
        found_new = show("B: Bhavcopy new format " + str(day), u)
    if not found_old:
        u = "https://www.bseindia.com/download/BhavCopy/Equity/EQ_ISINCODE_%s.zip" % day.strftime("%d%m%y")
        found_old = show("C: Bhavcopy old format " + str(day), u)
    if found_new and found_old:
        break

print("=" * 55)
print("SUMMARY: A/B/C లో STATUS 200 వచ్చినవి చూడండి")
