"""
לוח שידורים ישראלי לשבוע ומעלה, כקובץ XMLTV אחד דחוס (il-week.xml.gz).

שלושה מקורות, כולם ממשקי האתרים עצמם (לא רשמיים):
  FreeTV  - web.freetv.tv, כ-72 ערוצים, 9 עד 16 ימים קדימה. בקשה אחת לכל יום לכל הערוצים.
  סלקום   - Kaltura של סלקום TV (partner 3197), כ-170 ערוצים, 7 עד 14 ימים. בקשה לכל ערוץ.
  yes     - svc.yes.co.il, כ-180 ערוצים, עד 7 ימים. בקשה לכל ערוץ לכל יום, ולכן רק לערוצים שאין בשני האחרים.

אותו ערוץ בכמה מקורות (ערוץ 12 ב-FreeTV, "קשת" בסלקום, "Keshet HD" ב-yes) מאוחד למפתח אחד ([CANON]), ולכל ערוץ
נלקח המקור שמגיע הכי רחוק קדימה (בתיקו: FreeTV, סלקום, yes). לכל ערוץ כמה שמות תצוגה, עברית ואנגלית, כמו בטבלת
הכינויים של האפליקציה (ForkIlEpg), כך שהערוצים של כל ספק IPTV מוצאים אותו לפי השם.

מקור שנכשל לא מפיל את הריצה: הערוצים שלו מגיעים ממקור אחר, או לא מגיעים. ריצה שיצא בה מעט מדי (MIN_PROGRAMMES)
נכשלת בלי לכתוב קובץ, כך שהקובץ של אתמול נשאר.

הרצה:  python build.py [out_dir]     (ברירת מחדל: dist)
פלט:    il-week.xml.gz, report.json (כמה ערוצים ותוכניות מכל מקור, עד מתי, כמה זמן)
"""
import concurrent.futures as cf
import datetime as dt
import gzip
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import uuid
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


# ------------------------------------------------------------------ איחוד ערוצים

def norm(title):
    """שם להשוואה: אותיות קטנות, בלי HD/SD/4K, סוגריים, סימנים ורווחים."""
    s = title.lower()
    s = re.sub(r"\(.*?\)|\[.*?\]", " ", s)
    s = re.sub(r"\b(hd|sd|fhd|uhd|ip only|ip|ssr|sub|ll|nopics|\+ip)\b", " ", s)
    return re.sub(r"[^0-9a-z֐-׿+]", "", s)


# מפתח -> (שמות תצוגה, שמות במקורות). השמות הראשונים הם הכינויים שהאפליקציה מכירה (ForkIlEpg).
CANON = {
    "kan11": (["Kan 11", "כאן 11", "ערוץ 11"], ["ערוץ 11", "כאן 11", "kan"]),
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
    "sport5": (["Sport 5", "ספורט 5"], ["sport5", "sport 5"]),
    "sport5plus": (["Sport 5 Plus", "ספורט 5 פלוס"], ["sport 5 plus", "sport 5+"]),
    "sport5gold": (["Sport 5 Gold", "ספורט 5 גולד"], ["sport 5 gold"]),
    "sport5live": (["Sport 5 Live", "ספורט 5 לייב"], ["sport 5 live"]),
    "sport5stars": (["Sport 5 Stars", "ספורט 5 סטארס"], ["sport 5 stars"]),
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
        if not n.isdigit():
            continue
        out.setdefault(canon_of(c.get("title") or ""), ["yes %s" % n])
    return out


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

PRIORITY = {"freetv": 0, "cellcom": 1, "yes": 2}


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
    write(chosen, tmp, now, YES_ALIASES)
    os.replace(tmp, os.path.join(out_dir, "il-week.xml.gz"))
    with open(os.path.join(out_dir, "report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print("size: %.1f MB" % (os.path.getsize(os.path.join(out_dir, "il-week.xml.gz")) / 1e6))


if __name__ == "__main__":
    main()
