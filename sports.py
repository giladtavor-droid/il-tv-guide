"""
ספורט ישראלי כקובץ JSON אחד (il-sports.json), באותה תבנית של המדריך.

למה בכלל: עד היום האפליקציה משכה את כל הספורט הישראלי ישירות מ-TheSportsDB, עם **מפתח הבדיקה
החינמי "123"** ובלי גיבוי. המפתח הקודם כבר מחזיר 403, 429 גורר השהיה של 61 שניות, והטבלה החינמית
נקטעת ב-5 שורות — ולכן הטבלאות הוצגו חלקיות והגביעים נגרדו מ-HTML של אתר ההתאחדות.

כאן המקור הוא 365Scores, שכבר בשימוש באפליקציה: 26 תחרויות ישראליות, בעברית, **עם הטבלה המלאה**
(14–16 שורות), עם הגביעים, עם דקת משחק ועם צבעי הקבוצות. הצינור הזה מוריד את תקרות הקצב מכל
המכשירים ומסתיר מקור לא מתועד מאחורי קובץ אחד שאנחנו שולטים בו.

הלייב (תוצאה ודקה תוך כדי משחק) **לא** עובר כאן: הוא נקרא ישירות מהמכשיר, כי רענון של חמש שניות
לא עובר דרך קובץ שמתפרסם כמה פעמים ביום.

הרצה:  python sports.py [out_dir]     (ברירת מחדל: dist)
פלט:    il-sports.json
"""
import datetime as dt
import json
import os
import sys
import time
import urllib.request

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
BASE = "https://webws.365scores.com/web"
TIMEOUT = 30
UTC = dt.timezone.utc

# פחות מזה — הריצה דלה מדי ולא כותבים קובץ, כדי שהקובץ של אתמול יישאר.
MIN_GAMES = 20


class Comp:
    """תחרות: המזהה ב-365Scores, השם בעברית, והענף (1 כדורגל, 2 כדורסל)."""

    def __init__(self, id, he, sport):
        self.id, self.he, self.sport = id, he, sport


# נמדד 11.11.2026 מול האתר: כל אחת מחזירה טבלה ומשחקים בעברית.
COMPETITIONS = [
    Comp(42, "ליגת העל", 1),
    Comp(43, "ליגה לאומית", 1),
    Comp(49, "גביע המדינה", 1),
    Comp(546, "גביע הטוטו", 1),
    Comp(53, "גביע הטוטו לאומית", 1),
    Comp(47, "ליגת ווינר", 2),
    Comp(609, "גביע ווינר", 2),
    Comp(51, "גביע המדינה בכדורסל", 2),
]


def fetch(path, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(BASE + path, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            last = e
            time.sleep(1.5 * (i + 1))
    raise last


def _num(v):
    """מספר, או None כש-365Scores מסמן "אין" במינוס אחד."""
    if v is None:
        return None
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    if n < 0:
        return None
    return int(n) if n == int(n) else n


def _side(c):
    """צד במשחק: שם בעברית, קיצור, תוצאה וצבע. None כשאין צד."""
    if not c or not c.get("name"):
        return None
    return {"id": c.get("id"), "name": c.get("name"), "short": c.get("symbolicName"),
            "score": _num(c.get("score")), "color": c.get("color")}


# statusGroup של 365Scores, נמדד 11.11.2026: 2 טרם החל, 4 הסתיים (גם אחרי הארכה ופנדלים), 3 חי.
# האפליקציה מכירה "pre" / "in" / "post" (אותם שמות שה-EuroLeague ושאר המקורות מחזירים).
_STATE = {2: "pre", 3: "in", 4: "post"}


def _state(g, home, away):
    s = _STATE.get(g.get("statusGroup"))
    if s:
        return s
    # קוד שלא מוכר: תוצאה קיימת אומרת שהמשחק לפחות התחיל.
    return "in" if home.get("score") is not None or away.get("score") is not None else "pre"


def _iso_z(s):
    """365Scores מחזיר "+00:00"; האפליקציה קוראת "...Z"."""
    s = (s or "").strip()
    return (s[:19] + "Z") if len(s) >= 19 else None


def parse_games(raw):
    """תשובת games -> משחקים בפורמט שדף הספורט קורא. משחק בלי שני צדדים נזרק."""
    out = []
    for g in (raw or {}).get("games") or []:
        home, away = _side(g.get("homeCompetitor")), _side(g.get("awayCompetitor"))
        if not home or not away:
            continue
        start = _iso_z(g.get("startTime"))
        if not start:
            continue
        state = _state(g, home, away)
        e = {
            "id": g.get("id"),
            "comp": g.get("competitionId"),
            "sport": g.get("sportId"),
            "start": start,
            "hasTime": True,
            "state": state,
            "status": g.get("statusText"),
            "minute": _num(g.get("gameTime")),
            "round": g.get("roundNum"),
            "home": home,
            "away": away,
        }
        # תוצאה נכתבת רק כשיש מה לכתוב, כמו בשאר המקורות.
        if state != "pre" and (home.get("score") is not None or away.get("score") is not None):
            e["hs"] = home.get("score") or 0
            e["as"] = away.get("score") or 0
        out.append(e)
    return out


def parse_table(raw):
    """תשובת standings -> שורות הטבלה, כולן. הטבלה החינמית של TheSportsDB נקטעה ב-5."""
    groups = (raw or {}).get("standings") or []
    rows = (groups[0] if groups else {}).get("rows") or []
    out = []
    for r in rows:
        c = r.get("competitor") or {}
        out.append({
            "pos": _num(r.get("position")),
            "id": c.get("id"),
            "team": c.get("name"),
            "short": c.get("symbolicName"),
            "color": c.get("color"),
            "played": _num(r.get("gamePlayed")),
            "w": _num(r.get("gamesWon")),
            "d": _num(r.get("gamesEven")),
            "l": _num(r.get("gamesLost")),
            "gf": _num(r.get("for")),
            "ga": _num(r.get("against")),
            "points": _num(r.get("points")),
            # חמשת המשחקים האחרונים ("WWDWW"), לגרף הטופס בדף הקבוצה.
            "form": r.get("recentForm") or None,
        })
    return out


def build(get, comps=None):
    """המסמך כולו. [get] מוזרק כדי שאפשר יהיה לבדוק בלי רשת.

    תחרות שנפלה לא מפילה את השאר: היא נרשמת ב-failed, ומה שכבר נאסף נשאר.
    """
    comps = COMPETITIONS if comps is None else comps
    games, tables, failed = [], {}, []
    for c in comps:
        try:
            games += parse_games(get("/games/current/?appTypeId=5&langId=2&competitions=%d" % c.id))
            rows = parse_table(get("/standings/?appTypeId=5&langId=2&competitions=%d" % c.id))
            if rows:
                tables[str(c.id)] = rows
        except Exception as e:
            print("%s (%d): %s" % (c.he, c.id, e), file=sys.stderr)
            failed.append(c.id)
    return {
        "built": dt.datetime.now(UTC).isoformat(timespec="seconds"),
        "competitions": [{"id": c.id, "name": c.he, "sport": c.sport} for c in comps],
        "games": games,
        "tables": tables,
        "failed": failed,
    }


def too_little(doc):
    """ריצה דלה מדי: לא כותבים, כדי שהקובץ של אתמול יישאר."""
    return len(doc.get("games") or []) < MIN_GAMES and not (doc.get("tables") or {})


def main():
    out_dir = sys.argv[1] if len(sys.argv) > 1 else "dist"
    os.makedirs(out_dir, exist_ok=True)
    doc = build(fetch)
    print("%d משחקים, %d טבלאות, %d נפלו" % (len(doc["games"]), len(doc["tables"]), len(doc["failed"])))
    if too_little(doc):
        print("מעט מדי: לא נכתב קובץ", file=sys.stderr)
        return 1
    tmp = os.path.join(out_dir, "il-sports.json.part")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, os.path.join(out_dir, "il-sports.json"))
    print("גודל: %.2f MB" % (os.path.getsize(os.path.join(out_dir, "il-sports.json")) / 1e6))
    return 0


if __name__ == "__main__":
    sys.exit(main())
