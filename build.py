"""
לוח שידורים ישראלי לשבוע ומעלה, כקובץ XMLTV אחד דחוס (il-week.xml.gz).

חמישה מקורות. שלושת הראשונים הם ממשקי האתרים עצמם (לא רשמיים):
  FreeTV  - web.freetv.tv, כ-72 ערוצים, 9 עד 16 ימים קדימה. בקשה אחת לכל יום לכל הערוצים.
  סלקום   - Kaltura של סלקום TV (partner 3197), כ-170 ערוצים, 7 עד 14 ימים. בקשה לכל ערוץ.
  yes     - svc.yes.co.il, כ-180 ערוצים, עד 7 ימים. בקשה לכל ערוץ לכל יום, ולכן רק לערוצים שאין בשני האחרים.

ושני לוחות XMLTV מוכנים, שעד 11.11.2026 האפליקציה הוסיפה כמקורות נפרדים במכשיר:
  EPGShare - epgshare01.online, כ-118 ערוצים. מכסה ערוצים שאין לשלושת הראשונים (הוט סינמה, משפחת ספורט 5).
  Open-EPG - open-epg.com, כ-38 ערוצים.

השניים אחרונים בעדיפות: ערוץ מקבל אותם רק כשאין לו מקור ישיר, או כשהם מגיעים חצי יום ומעלה רחוק יותר קדימה.

אותו ערוץ בכמה מקורות (ערוץ 12 ב-FreeTV, "קשת" בסלקום, "Keshet HD" ב-yes) מאוחד למפתח אחד ([CANON]), ולכל ערוץ
נלקח המקור שמגיע הכי רחוק קדימה (בתיקו: FreeTV, סלקום, yes). לכל ערוץ כמה שמות תצוגה, עברית ואנגלית, כמו בטבלת
הכינויים של האפליקציה (ForkIlEpg), כך שהערוצים של כל ספק IPTV מוצאים אותו לפי השם.

מקור שנכשל לא מפיל את הריצה: הערוצים שלו מגיעים ממקור אחר, או לא מגיעים. ריצה שיצא בה מעט מדי (MIN_PROGRAMMES)
נכשלת בלי לכתוב קובץ, כך שהקובץ של אתמול נשאר.

הרצה:  python build.py [out_dir]     (ברירת מחדל: dist)
פלט:    il-week.xml.gz, report.json (כמה ערוצים ותוכניות מכל מקור, עד מתי, כמה זמן), report.md (כל ערוץ ושמותיו)
"""
import concurrent.futures as cf
import datetime as dt
import gzip
import io
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import uuid
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape, quoteattr

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
UTC = dt.timezone.utc
IL = dt.timezone(dt.timedelta(hours=2))  # היום הקלנדרי של FreeTV; שעון קיץ לא משנה את הגבול (חלון של יום שלם)
DAYS_AHEAD = 16
DESC_MAX = 500
MIN_PROGRAMMES = 5000
TIMEOUT = 30


def fetch(url, data=None, headers=None, tries=3):
    h = {"User-Agent": UA, "Accept": "application/json"}
    h.update(headers or {})
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers=h)
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # רשת, 5xx, JSON חלקי
            last = e
            time.sleep(1.5 * (i + 1))
    raise last


def fetch_bytes(url, tries=3):
    """הגוף כבייטים, מפורק מ-gzip אם צריך. לקובצי XMLTV, שבאים .xml.gz ולא JSON."""
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                raw = r.read()
            return gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw
        except Exception as e:
            last = e
            time.sleep(1.5 * (i + 1))
    raise last


# ------------------------------------------------------------------ איחוד ערוצים

# EPGShare ו-Open-EPG קוראים לאותו ערוץ "ערוץ 12 שידור חי", "MTV.il" או "ערוץ 12 | לוח השידורים המלא של קשת 12".
# בלי לנקות את שלושת אלה כל ערוץ שלהם היה נכנס שוב, ככפילות לצד הערוץ שכבר הגיע ממקור ישיר.
LIVE_TAIL = re.compile(r"\b(ב?שידור\s+חי)\b")
IL_SUFFIX = re.compile(r"\.il\s*$", re.I)


def norm(title):
    """שם להשוואה: אותיות קטנות, בלי HD/SD/4K, סוגריים, סימנים ורווחים, בלי "שידור חי" ו-".il", ובלי זנב אחרי "|"."""
    s = LIVE_TAIL.sub(" ", IL_SUFFIX.sub("", title.split("|")[0].lower()))
    s = re.sub(r"\(.*?\)|\[.*?\]", " ", s)
    s = re.sub(r"\b(hd|sd|fhd|uhd|ip only|ip|ssr|sub|ll|nopics|\+ip)\b", " ", s)
    return re.sub(r"[^0-9a-z֐-׿+]", "", s)


# מפתח -> (שמות תצוגה, שמות במקורות). השמות הראשונים הם הכינויים שהאפליקציה מכירה (ForkIlEpg).
CANON = {
    "kan11": (["Kan 11", "כאן 11", "ערוץ 11"], ["ערוץ 11", "כאן 11", "ערוץ 11 כאן", "kan"]),
    "keshet12": (["Keshet 12", "קשת 12", "ערוץ 12"], ["ערוץ 12", "קשת 12", "קשת", "keshet"]),
    "reshet13": (["Reshet 13", "רשת 13", "ערוץ 13"], ["ערוץ 13", "רשת 13", "רשת", "reshet"]),
    "now14": (["Now 14", "עכשיו 14", "ערוץ 14"], ["ערוץ 14", "channel 14"]),
    "ch9": (["Israel Plus", "ישראל פלוס", "ערוץ 9"], ["ערוץ 9", "israel plus"]),
    "i24he": (["i24NEWS Hebrew", "i24 עברית", "i24NEWS"], ["i24 עברית", "עברית i24", "i24 hebrew"]),
    "i24en": (["i24NEWS English", "i24 English"], ["i24 english"]),
    "i24fr": (["i24NEWS French", "i24 French"], ["i24 french"]),
    "i24ar": (["i24NEWS Arabic", "i24 Arabic"], ["i24 arabic"]),
    "ch16": (["Channel 16", "ערוץ 16"], ["ערוץ 16", "channel 16"]),
    "kanedu": (["Kan Educational", "כאן חינוכית", "חינוכית"], ["חינוכית", "כאן חינוכית", "kan educational"]),
    "makan": (["Makan 33", "מכאן", "Makan"], ["מכאן", "makan"]),
    "knesset": (["Knesset", "ערוץ הכנסת"], ["ערוץ הכנסת", "knesset"]),
    "music24": (["Music 24", "מוזיקה 24", "Channel 24 Music"], ["music 24", "מוסיקה 24"]),
    "ch23": (["ערוץ 23 רק ישראלי", "23 Only Israeli"], ["ערוץ 23 רק ישראלי", "23 - only israeli"]),
    "sport1": (["ספורט 1", "Sport 1 Israel"], ["ספורט 1", "sport 1"]),
    "sport2": (["ספורט 2", "Sport 2 Israel"], ["ספורט 2", "sport 2"]),
    "sport3": (["ספורט 3", "Sport 3 Israel"], ["ספורט 3", "sport 3"]),
    "sport4": (["ספורט 4", "Sport 4 Israel"], ["ספורט 4", "sport 4"]),
    "sport6": (["ספורט 6", "Sport 6 Israel"], ["ספורט 6", "sport 6"]),
    # EPGShare קורא למשפחת ספורט 5 "5GOLD", "5LIVE", "5PLUS", "5SPORT", "5STARS".
    "sport5": (["Sport 5", "ספורט 5"], ["sport5", "sport 5", "5sport"]),
    "sport5plus": (["Sport 5 Plus", "ספורט 5 פלוס"], ["sport 5 plus", "sport 5+", "5plus", "ספורט 5 פלוס לייב"]),
    "sport5gold": (["Sport 5 Gold", "ספורט 5 גולד"], ["sport 5 gold", "5gold", "ספורט 5 גולד"]),
    "sport5live": (["Sport 5 Live", "ספורט 5 לייב"], ["sport 5 live", "5live", "ספורט 5 לייב"]),
    "sport5stars": (["Sport 5 Stars", "ספורט 5 סטארס"], ["sport 5 stars", "5stars", "ספורט 5 סטארס"]),
    "sport5max": (["Sport 5 MAX", "ספורט 5 מקס"], ["sport 5 max"]),
    "sport54k": (["Sport 5 4K", "ספורט 5 4K"], ["sport 5 4k"]),
    "eurosport1": (["יורוספורט 1", "Eurosport 1 Israel"], ["eurosport 1", "eurosport"]),
    "eurosport2": (["יורוספורט 2", "Eurosport 2 Israel"], ["eurosport 2"]),
    "one": (["One", "ערוץ One", "ONE 1"], ["one 1", "one"]),
    "one2": (["One 2", "ערוץ One 2"], ["one 2", "one2"]),
    "onedoco": (["One Doco"], ["one doco"]),
    "oneedge": (["One Edge"], ["one edge"]),
    "daystar": (["DAYSTAR"], ["daystar"]),
    "foody": (["FOODY"], ["foody"]),
    "junior": (["Junior", "ג'וניור"], ["junior", "ג'וניור"]),
    "yoyo": (["יויו", "Yoyo"], ["יויו", "yoyo"]),
    "baby": (["Baby", "בייבי"], ["baby", "בייבי"]),
    "luli": (["לולי", "Luli"], ["luli"]),
    # ערוצי yes, ילדים ותיעוד: שם עברי ראשון (מוצג באפליקציה), אחריו האנגלית. שמות המקור כפי ש-norm מחזירה אותם.
    "yesmoviesaction": (["yes סרטים אקשן", "yes Movies Action"], ["yes movies action"]),
    "yesmoviescomedy": (["yes סרטים קומדיה", "yes Movies Comedy"], ["yes movies comedy"]),
    "yesmoviesdrama": (["yes סרטים דרמה", "yes Movies Drama"], ["yes movies drama"]),
    "yesmovieskids": (["yes סרטים ילדים", "yes Movies Kids"], ["yes movies kids"]),
    "yesisraelicinema": (["yes קולנוע ישראלי", "yes Israeli Cinema"], ["yes israeli cinema"]),
    "yesdocu": (["yes דוקו", "yes Docu"], ["yes docu"]),
    "yestvaction": (["yes TV אקשן", "yes TV Action"], ["yes tv action"]),
    "yestvcomedy": (["yes TV קומדיה", "yes TV Comedy"], ["yes tv comedy"]),
    "yestvdrama": (["yes TV דרמה", "yes TV Drama"], ["yes tv drama"]),
    "disney": (["דיסני", "Disney Channel", "Disney"], ["disney"]),
    "disneyjunior": (["דיסני ג'וניור", "Disney Junior"], ["disney junior"]),
    "nickelodeon": (["ניקלודיאון", "Nickelodeon"], ["nickelodeon"]),
    "nickjunior": (["ניק ג'וניור", "Nick Junior"], ["nick junior"]),
    "teennick": (["טין ניק", "TeenNick"], ["teennick"]),
    "hop": (["הופ", "HOP"], ["hop"]),
    "hopchildhood": (["הופ ילדות", "HOP Childhood"], ["hop! childhood", "hop childhood"]),
    "discovery": (["דיסקברי", "Discovery Channel", "Discovery"], ["discovery"]),
    "history": (["היסטוריה", "History Channel", "History"], ["history"]),
    "foodchannel": (["ערוץ האוכל", "Food Channel"], ["food channel"]),
    "ego": (["אגו", "EGO"], ["ego"]),
    # ערוצי FreeTV: שמות הספק (FreeTV סרטים פעולה) וכפי שספקי IPTV כותבים אותם ("FREE TV MOVIES ACTION", "FREE MOVIES ACTION").
    "freetvmoviesaction": (["FreeTV סרטים פעולה", "FreeTV Movies Action", "Free Movies Action"], ["freetv סרטים פעולה"]),
    "freetvmoviescomedy": (["FreeTV סרטים קומדיה", "FreeTV Movies Comedy", "FreeTV Movies Comdey", "Free Movies Comedy"], ["freetv סרטים קומדיה"]),
    "freetvmoviesdrama": (["FreeTV סרטים דרמה", "FreeTV Movies Drama", "Free Movies Drama"], ["freetv סרטים דרמה"]),
    "freetvmovieshorror": (["FreeTV סרטים אימה", "FreeTV Movies Horror", "Free Movies Horror"], ["freetv סרטים אימה"]),
    "freetvmoviesisraeli": (["FreeTV סרטים ישראלי", "FreeTV Movies Israeli", "Free Israeli Movies"], ["freetv סרטים ישראלי"]),
    "freetvmoviesfamily": (["FreeTV סרטים משפחה", "FreeTV Movies Family", "Free Movies Family"], ["freetv סרטים משפחה"]),
    "freetvmoviesthriller": (["FreeTV סרטים מתח", "FreeTV Movies Thriller", "Free Movies Thriller"], ["freetv סרטים מתח"]),
    "freetvmoviesromance": (["FreeTV סרטים רומנטי", "FreeTV Movies Romantic", "Free Movies Romance"], ["freetv סרטים רומנטי"]),
    "freetvseriesdrama": (["FreeTV סדרות דרמה", "FreeTV Drama", "FreeTV TV Series"], ["freetv סדרות דרמה"]),
    "freetvseriescomedy": (["FreeTV סדרות קומדיה", "FreeTV Comedy"], ["freetv סדרות קומדיה"]),
    "freetvdocu": (["FreeTV דוקו", "FreeTV Docu"], ["freetv דוקו"]),
    "freetvcooking": (["FreeTV אוכל", "FreeTV Cooking"], ["freetv אוכל"]),
    "freetvlifestyle": (["FreeTV לייף סטייל", "FreeTV Lifestyle"], ["freetv לייף סטייל"]),
    "freetvglobal": (["FreeTV גלובל", "FreeTV Global", "Free Global"], ["freetv גלובל"]),
    # הערוצים שרק EPGShare ו-Open-EPG מכסים (נמדד 11.11.2026). בלי מפתח כאן הם נכנסים כ-"x.<שם>",
    # בלי שם עברי ובלי שהאפליקציה מזהה אותם מול שמות הערוצים של ספק ה-IPTV.
    "hotcinema1": (["הוט סינמה 1", "HOT Cinema 1"], ["הוט סינמה 1", "hot cinema 1"]),
    "hotcinema2": (["הוט סינמה 2", "HOT Cinema 2"], ["הוט סינמה 2", "hot cinema 2"]),
    "hotcinema3": (["הוט סינמה 3", "HOT Cinema 3"], ["הוט סינמה 3", "hot cinema 3"]),
    "hotisraeli": (["הוט בידור ישראלי", "HOT Israeli Entertainment"], ["הוט בידור ישראלי"]),
    "aljazeera": (["אל ג'זירה", "Al Jazeera"], ["אל ג'זירה", "al jazeera"]),
    "mtv": (["MTV", "אם טי וי"], ["mtv"]),
    "dwrussian": (["DW רוסית", "DW Russian"], ["dw רוסית", "dw russian"]),
    "israel33": (["ישראל 33", "Israel 33"], ["ישראל 33", "israel 33"]),
}
BY_SOURCE_NAME = {}
for key, (_, names) in CANON.items():
    for n in names:
        BY_SOURCE_NAME[norm(n)] = key


def canon_of(title):
    return BY_SOURCE_NAME.get(norm(title)) or "x." + norm(title)


# ------------------------------------------------------------------ מספרי הערוצים של yes

# מפתח -> ["yes N"]: מספר הערוץ ב-yes כשם תצוגה (הרישיות לא משנה: האפליקציות משוות באותיות קטנות). ספקי IPTV קוראים לערוצים "IL: YES 13" לפי המספור הזה,
# והנרמול של האפליקציה הופך גם "IL: YES 13" וגם "yes 13" לאותו מפתח. נאסף מכל ערוצי yes, גם כאלה שהלוח שלהם נלקח ממקור אחר.
YES_ALIASES = {}


HEBREW = re.compile("[֐-׿]")


def display_names(key, title, aliases):
    """שמות התצוגה של ערוץ בקובץ: השם העברי ראשון, אחריו שמות CANON ושם המקור, ובסוף כינויי המספר של yes. בלי כפילויות."""
    out = []
    seen = set()

    def add(n):
        n = n.strip()
        if n and n.lower() not in seen:
            seen.add(n.lower())
            out.append(n)

    for n in (CANON[key][0] if key in CANON else []):
        add(n)
    add(title)
    for i, n in enumerate(out):
        if HEBREW.search(n):
            out.insert(0, out.pop(i))
            break
    for n in aliases.get(key, []):
        add(n)
    return out


def yes_number_aliases(items):
    """ערוצי ה-API של yes -> מפתח CANON -> כינויי מספר. בלי ערוצי רדיו (I0…) ובלי ערוץ שאין לו מספר."""
    out = {}
    for c in items:
        if str(c.get("channelId", "")).startswith("I0"):
            continue
        n = str(c.get("number") or "").strip()
        if not n.isdigit() or int(n) == 0:
            continue
        alias = "yes %d" % int(n)
        lst = out.setdefault(canon_of(c.get("title") or ""), [])
        if alias not in lst:
            lst.append(alias)          # אותו ערוץ בכמה מספרים (כאן 11 גם ב-311 וב-511, History ב-44 וב-45)
    return out


def aliases_or_previous(current, previous_report):
    """הכינויים של הריצה הזו; כש-yes נפל (ריק) - מה שנשמר ב-report.json של הריצה הקודמת, כדי שהם לא ייעלמו מהקובץ."""
    return current or dict(previous_report.get("yes_numbers") or {})


# ------------------------------------------------------------------ מקורות

class Channel:
    def __init__(self, source, sid, title, icon=None):
        self.source, self.sid, self.title, self.icon = source, sid, title.strip(), icon
        self.key = canon_of(self.title)
        self.programmes = []  # (start, stop, title, desc, icon, category) ב-UTC

    def last_stop(self):
        return max((p[1] for p in self.programmes), default=None)


def iso(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(UTC)


def freetv(now):
    base = "https://web.freetv.tv/api/products/lives"
    lives = fetch(base + "?platform=BROWSER&lang=HEB&maxResults=200")["items"]
    chans = {}
    for c in lives:
        img = ((c.get("images") or {}).get("16x9") or [{}])[0].get("url")
        chans[c["id"]] = Channel("freetv", c["id"], c["title"], ("https:" + img) if img and img.startswith("//") else img)
    ids = list(chans)
    day0 = now.astimezone(IL).date()

    def one_day(k, part):
        d = day0 + dt.timedelta(days=k)
        since = dt.datetime.combine(d, dt.time(), IL).strftime("%Y-%m-%dT%H:%M%z")
        till = dt.datetime.combine(d + dt.timedelta(days=1), dt.time(), IL).strftime("%Y-%m-%dT%H:%M%z")
        qs = "&".join("liveId[]=%d" % i for i in part) + "&since=" + urllib.parse.quote(since) + "&till=" + urllib.parse.quote(till)
        return fetch(base + "/programmes?" + qs + "&lang=HEB&platform=BROWSER")

    parts = [ids[i:i + 24] for i in range(0, len(ids), 24)]
    seen = set()
    with cf.ThreadPoolExecutor(6) as ex:
        futs = [ex.submit(one_day, k, p) for k in range(DAYS_AHEAD) for p in parts]
        for f in cf.as_completed(futs):
            try:
                items = f.result()
            except Exception as e:
                print("freetv: a day failed:", e, file=sys.stderr)
                continue
            for x in items or []:
                ch = chans.get((x.get("live") or {}).get("id"))
                if ch is None or x.get("id") in seen:
                    continue
                seen.add(x.get("id"))
                img = ((x.get("images") or {}).get("16x9") or [{}])[0].get("url")
                genres = [g.get("name") for g in x.get("genres") or [] if isinstance(g, dict) and g.get("name")]
                ch.programmes.append((iso(x["since"]), iso(x["till"]), x.get("title") or "", x.get("description") or x.get("lead") or "",
                                      ("https:" + img) if img and img.startswith("//") else img, genres[0] if genres else None))
    return list(chans.values())


KALTURA = "https://api.frp1.ott.kaltura.com/api_v3/service/"


def kpost(svc, body):
    return fetch(KALTURA + svc, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})


def cellcom(now):
    ks = kpost("OTTUser/action/anonymousLogin", {"apiVersion": "5.4.0.28193", "partnerId": "3197", "udid": str(uuid.uuid4())})["result"]["ks"]
    t = int(now.timestamp())

    def search(ksql, page=1, size=500):
        return kpost("asset/action/list", {"apiVersion": "5.4.0.28193", "ks": ks,
                                           "filter": {"objectType": "KalturaSearchAssetFilter", "kSql": ksql, "orderBy": "START_DATE_ASC"},
                                           "pager": {"objectType": "KalturaFilterPager", "pageIndex": page, "pageSize": size}})["result"]

    # הערוצים: מה שמשודר עכשיו בכל ערוץ נותן את מזהה הלוח שלו ואת הערוץ עצמו (שמו).
    epg_of = {}
    for o in search("(and asset_type='epg' start_date<'%d' end_date>'%d')" % (t, t)).get("objects", []):
        if o.get("linearAssetId"):
            epg_of[o["linearAssetId"]] = o["epgChannelId"]
    names = {}
    ids = list(epg_of)
    for i in range(0, len(ids), 100):
        r = search("(or " + " ".join("media_id='%d'" % m for m in ids[i:i + 100]) + ")")
        for o in r.get("objects", []):
            names[o["id"]] = o.get("name") or ""
    chans = [Channel("cellcom", epg_of[m], names[m]) for m in ids if names.get(m) and "בדיקה" not in names[m]
             and "מונגש" not in names[m] and not names[m].startswith("רדיו") and "התחנה" not in names[m]]
    end = t + DAYS_AHEAD * 86400

    def one(ch):
        page, out = 1, []
        while True:
            r = search("(and epg_channel_id='%s' end_date>'%d' start_date<'%d' asset_type='epg')" % (ch.sid, t - 6 * 3600, end), page)
            objs = r.get("objects", [])
            out += objs
            if len(out) >= r.get("totalCount", 0) or not objs or page >= 6:
                return out
            page += 1

    with cf.ThreadPoolExecutor(8) as ex:
        for ch, f in [(c, ex.submit(one, c)) for c in chans]:
            try:
                objs = f.result()
            except Exception as e:
                print("cellcom: %s failed: %s" % (ch.title, e), file=sys.stderr)
                continue
            for o in objs:
                imgs = o.get("images") or []
                ch.programmes.append((dt.datetime.fromtimestamp(o["startDate"], UTC), dt.datetime.fromtimestamp(o["endDate"], UTC),
                                      (o.get("name") or "").strip(), (o.get("description") or "").strip(),
                                      imgs[0].get("url") if imgs else None, None))
    return chans


def yes(now, skip_keys):
    base = "https://svc.yes.co.il/api/content/broadcast-schedule/channels"
    items = fetch(base, headers={"Accept-Language": "he-IL"})["items"]
    YES_ALIASES.clear()
    YES_ALIASES.update(yes_number_aliases(items))
    chans, seen = [], set()
    for c in items:
        if c["channelId"] in seen or c["channelId"].startswith("I0"):
            continue
        seen.add(c["channelId"])
        ch = Channel("yes", c["channelId"], c["title"])
        if ch.key not in skip_keys:
            chans.append(ch)
    day0 = now.astimezone(IL).date()

    def one(ch, k):
        d = day0 + dt.timedelta(days=k)
        return fetch("%s/%s?date=%s&ignorePastItems=false" % (base, ch.sid, d.isoformat()), headers={"Accept-Language": "he-IL"}).get("items", [])

    with cf.ThreadPoolExecutor(10) as ex:
        jobs = [(ch, ex.submit(one, ch, k)) for ch in chans for k in range(8)]
        for ch, f in jobs:
            try:
                for x in f.result():
                    ch.programmes.append((iso(x["starts"]), iso(x["ends"]), x.get("title") or "", x.get("description") or "", x.get("imageUrl"), None))
            except Exception as e:
                print("yes: %s failed: %s" % (ch.title, e), file=sys.stderr)
    return chans


# ------------------------------------------------------------------ איחוד וכתיבה

# ------------------------------------------------------------------ מקורות XMLTV חיצוניים

# שני הלוחות שהאפליקציה הוסיפה עד היום בנפרד. כאן הם נכנסים כמקור ככל מקור אחר, כדי שבמכשיר יישאר מדריך אחד.
EPGSHARE_URL = "https://epgshare01.online/epgshare01/epg_ripper_IL1.xml.gz"
OPENEPG_URL = "https://www.open-epg.com/files/israel1.xml.gz"

XMLTV_TIME = re.compile(r"^(\d{14})(?:\s*([+-]\d{4}))?")


def xmltv_parse_time(s):
    """20261111180000 +0200 -> datetime ב-UTC. בלי אזור זמן נחשב UTC."""
    m = XMLTV_TIME.match((s or "").strip())
    if not m:
        return None
    t = dt.datetime.strptime(m.group(1), "%Y%m%d%H%M%S")
    off = m.group(2)
    if off:
        delta = dt.timedelta(hours=int(off[1:3]), minutes=int(off[3:5]))
        t = t.replace(tzinfo=dt.timezone(delta if off[0] == "+" else -delta))
    else:
        t = t.replace(tzinfo=UTC)
    return t.astimezone(UTC)


def xmltv_channels(raw, source):
    """קובץ XMLTV -> ערוצים עם תוכניות. תוכנית שהערוץ שלה לא מוגדר בקובץ, וערוץ בלי תוכניות, נזרקים."""
    chans = {}
    for _, el in ET.iterparse(io.BytesIO(raw), events=("end",)):
        if el.tag == "channel":
            cid = el.get("id") or ""
            name = next((d.text.strip() for d in el.findall("display-name") if (d.text or "").strip()), "")
            icon = el.find("icon")
            if cid and name and cid not in chans:
                chans[cid] = Channel(source, cid, name, icon.get("src") if icon is not None else None)
            el.clear()
        elif el.tag == "programme":
            ch = chans.get(el.get("channel") or "")
            start, stop = xmltv_parse_time(el.get("start")), xmltv_parse_time(el.get("stop"))
            title = (el.findtext("title") or "").strip()
            if ch is not None and title and start and stop and stop > start:
                desc = (el.findtext("desc") or "").strip()
                icon = el.find("icon")
                ch.programmes.append((start, stop, title, desc[:DESC_MAX] or None,
                                      icon.get("src") if icon is not None else None,
                                      (el.findtext("category") or "").strip() or None))
            el.clear()
    return [c for c in chans.values() if c.programmes]


def epgshare(now):
    return xmltv_channels(fetch_bytes(EPGSHARE_URL), "epgshare")


def openepg(now):
    return xmltv_channels(fetch_bytes(OPENEPG_URL), "openepg")


# המקורות הישירים קודמים: הם מגיעים מהמפעיל עצמו. השניים החיצוניים נכנסים לערוץ שאין לו מקור ישיר,
# או כשהם מגיעים חצי יום ומעלה רחוק יותר קדימה.
PRIORITY = {"freetv": 0, "cellcom": 1, "yes": 2, "epgshare": 3, "openepg": 4}


def pick(channels, now):
    """לכל מפתח: המקור שמגיע הכי רחוק (חצי יום ומעלה נחשב), בתיקו לפי PRIORITY. ערוץ בלי תוכניות עתידיות לא נכנס."""
    best = {}
    for ch in channels:
        last = ch.last_stop()
        if last is None or last <= now:
            continue
        half_days = int((last - now).total_seconds() // 43200)
        rank = (half_days, -PRIORITY[ch.source])
        cur = best.get(ch.key)
        if cur is None or rank > cur[0]:
            best[ch.key] = (rank, ch)
    return [c for _, c in sorted(best.values(), key=lambda v: v[1].key)]


def xmltv_time(t):
    return t.strftime("%Y%m%d%H%M%S +0000")


def write(chosen, path, now, aliases):
    keep_from = now - dt.timedelta(hours=6)
    with gzip.open(path, "wt", encoding="utf-8", compresslevel=9) as out:
        out.write('<?xml version="1.0" encoding="UTF-8"?>\n<tv generator-info-name="il-tv-guide">\n')
        for ch in chosen:
            cid = "il-week." + ch.key.replace("x.", "x-")
            names = display_names(ch.key, ch.title, aliases)
            out.write("<channel id=%s>" % quoteattr(cid))
            for n in names:
                out.write("<display-name lang=\"he\">%s</display-name>" % escape(n))
            if ch.icon:
                out.write("<icon src=%s/>" % quoteattr(ch.icon))
            out.write("</channel>\n")
        for ch in chosen:
            cid = "il-week." + ch.key.replace("x.", "x-")
            last_start = None
            for start, stop, title, desc, icon, cat in sorted(ch.programmes):
                if stop <= keep_from or stop <= start or start == last_start:
                    continue
                last_start = start
                out.write("<programme start=\"%s\" stop=\"%s\" channel=%s><title lang=\"he\">%s</title>"
                          % (xmltv_time(start), xmltv_time(stop), quoteattr(cid), escape(title.strip() or ch.title)))
                d = re.sub(r"\s+", " ", desc or "").strip()
                if d:
                    out.write("<desc lang=\"he\">%s</desc>" % escape(d[:DESC_MAX]))
                if cat:
                    out.write("<category lang=\"he\">%s</category>" % escape(cat))
                if icon:
                    out.write("<icon src=%s/>" % quoteattr(icon))
                out.write("</programme>\n")
        out.write("</tv>\n")


def report_markdown(report, names, now):
    """דוח קריא (Markdown): המקורות, ואז כל ערוץ עם שמות התצוגה שנכתבו לקובץ, המקור, עד מתי וכמה ימים קדימה."""
    def cell(v):
        return str(v).replace("|", "\\|")

    def until_txt(iso):
        return iso.replace("T", " ")[:16] if iso else "-"

    lines = ["# לוח שידורים ישראלי — דוח ריצה", "", "נבנה: %s" % report.get("built", ""), "",
             "| מקור | ערוצים | תוכניות | עד |", "|---|---|---|---|"]
    for name, src in report.get("sources", {}).items():
        lines.append("| %s | %s | %s | %s |" % (name, src.get("channels", 0), src.get("programmes", 0), until_txt(src.get("until"))))
    lines += ["", "| מפתח | שמות תצוגה | מקור | עד | ימים קדימה |", "|---|---|---|---|---|"]
    for key in sorted(report.get("per_channel", {})):
        ch = report["per_channel"][key]
        until = ch.get("until")
        days = max(0, (dt.datetime.fromisoformat(until) - now).days) if until else 0
        lines.append("| %s | %s | %s | %s | %d |" % (cell(key), " · ".join(cell(n) for n in names.get(key, [ch.get("title", "")])),
                                                   cell(ch.get("source", "")), until_txt(until), days))
    return "\n".join(lines) + "\n"


def main():
    out_dir = sys.argv[1] if len(sys.argv) > 1 else "dist"
    os.makedirs(out_dir, exist_ok=True)
    now = dt.datetime.now(UTC)
    report = {"built": now.isoformat(timespec="seconds"), "sources": {}}
    channels = []

    def run(name, fn, *a):
        t0 = time.time()
        try:
            got = fn(now, *a)
        except Exception as e:
            print("%s: failed: %s" % (name, e), file=sys.stderr)
            got = []
        n = sum(len(c.programmes) for c in got)
        last = max((c.last_stop() for c in got if c.last_stop()), default=None)
        report["sources"][name] = {"channels": len(got), "programmes": n, "seconds": round(time.time() - t0, 1),
                                   "until": last.isoformat(timespec="minutes") if last else None}
        print("%-8s %4d channels %6d programmes until %s in %.1fs" % (name, len(got), n, last, time.time() - t0))
        return got

    channels += run("freetv", freetv)
    channels += run("cellcom", cellcom)
    covered = {c.key for c in channels if c.last_stop() and c.last_stop() > now + dt.timedelta(days=6)}
    channels += run("yes", yes, covered)
    # שני הלוחות החיצוניים אחרונים: הם מכסים ערוצים שאין לשלושת הראשונים (הוט סינמה, משפחת ספורט 5
    # ועוד), ו-pick נותן להם ערוץ רק כשאין לו מקור ישיר או כשהם מגיעים רחוק יותר.
    channels += run("epgshare", epgshare)
    channels += run("openepg", openepg)

    # yes נפל? מספרי הערוצים מהריצה הקודמת (report.json בשורש המאגר, מגיע עם ה-checkout) במקום לפרסם קובץ בלעדיהם
    previous = {}
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "report.json"), encoding="utf-8") as f:
            previous = json.load(f)
    except (OSError, ValueError):
        pass
    aliases = aliases_or_previous(YES_ALIASES, previous)
    if not YES_ALIASES and aliases:
        print("yes numbers taken from the previous run (%d channels)" % len(aliases), file=sys.stderr)
    report["yes_numbers"] = aliases
    report["yes_numbers_from_previous_run"] = not YES_ALIASES and bool(aliases)

    chosen = pick(channels, now)
    total = sum(len(c.programmes) for c in chosen)
    report["channels"] = len(chosen)
    report["programmes"] = total
    report["per_channel"] = {c.key: {"source": c.source, "title": c.title, "until": c.last_stop().isoformat(timespec="minutes")} for c in chosen}
    print("chosen: %d channels, %d programmes" % (len(chosen), total))
    if total < MIN_PROGRAMMES:
        print("too few programmes (%d < %d): nothing written" % (total, MIN_PROGRAMMES), file=sys.stderr)
        sys.exit(1)
    tmp = os.path.join(out_dir, "il-week.xml.gz.part")
    write(chosen, tmp, now, aliases)
    os.replace(tmp, os.path.join(out_dir, "il-week.xml.gz"))
    with open(os.path.join(out_dir, "report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    names = {c.key: display_names(c.key, c.title, aliases) for c in chosen}
    with open(os.path.join(out_dir, "report.md"), "w", encoding="utf-8") as f:
        f.write(report_markdown(report, names, now))
    print("size: %.1f MB" % (os.path.getsize(os.path.join(out_dir, "il-week.xml.gz")) / 1e6))


if __name__ == "__main__":
    main()
