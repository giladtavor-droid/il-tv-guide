"""בדיקות לפונקציות הטהורות של build.py (בלי רשת). הרצה: python -m unittest test_build -v"""
import unittest

import build

YES_ITEMS = [
    {"title": "Reshet HD", "number": "13", "channelId": "CH36"},
    {"title": "Kan HD", "number": "11", "channelId": "CH30"},
    {"title": "Big Brother HD", "number": "26", "channelId": "CH40"},
    {"title": "yes 7 October", "number": "26", "channelId": "CH41"},
    {"title": "Some Pack", "number": "", "channelId": "CH50"},
    {"title": "Radio X", "number": "7", "channelId": "I01"},
]


class YesNumberAliases(unittest.TestCase):
    def test_numbers_become_aliases_by_canon_key(self):
        a = build.yes_number_aliases(YES_ITEMS)
        self.assertEqual(a["reshet13"], ["yes 13"])
        self.assertEqual(a["kan11"], ["yes 11"])

    def test_duplicate_number_goes_to_both_channels(self):
        a = build.yes_number_aliases(YES_ITEMS)
        self.assertEqual(a[build.canon_of("Big Brother HD")], ["yes 26"])
        self.assertEqual(a[build.canon_of("yes 7 October")], ["yes 26"])

    def test_no_number_and_radio_are_skipped(self):
        a = build.yes_number_aliases(YES_ITEMS)
        self.assertNotIn(build.canon_of("Some Pack"), a)
        self.assertNotIn(build.canon_of("Radio X"), a)

    def test_every_number_of_the_same_channel_is_kept(self):
        a = build.yes_number_aliases([{"title": "History SD", "number": "44", "channelId": "CH1"},
                                      {"title": "History HD", "number": "45", "channelId": "CH2"},
                                      {"title": "Kan HD", "number": "11", "channelId": "CH30"},
                                      {"title": "Kan HD", "number": "311", "channelId": "CH31"}])
        self.assertEqual(a[build.canon_of("History SD")], ["yes 44", "yes 45"])
        self.assertEqual(a["kan11"], ["yes 11", "yes 311"])

    def test_zero_and_leading_zeros(self):
        a = build.yes_number_aliases([{"title": "yes+ Love", "number": "0", "channelId": "CH1"},
                                      {"title": "Kan HD", "number": "011", "channelId": "CH30"}])
        self.assertNotIn(build.canon_of("yes+ Love"), a)
        self.assertEqual(a["kan11"], ["yes 11"])

    def test_previous_numbers_used_when_yes_is_down(self):
        prev = {"built": "x", "yes_numbers": {"kan11": ["yes 11"]}}
        self.assertEqual(build.aliases_or_previous({}, prev), {"kan11": ["yes 11"]})
        self.assertEqual(build.aliases_or_previous({"kan11": ["yes 11", "yes 311"]}, prev), {"kan11": ["yes 11", "yes 311"]})
        self.assertEqual(build.aliases_or_previous({}, {"built": "x"}), {})


class DisplayNames(unittest.TestCase):
    def test_hebrew_first_then_english_then_aliases(self):
        names = build.display_names("kan11", "ערוץ 11", {"kan11": ["yes 11"]})
        self.assertEqual(names[0], "כאן 11")
        self.assertEqual(names[-1], "yes 11")
        self.assertIn("Kan 11", names)
        self.assertIn("ערוץ 11", names)
        self.assertEqual(len(names), len({n.lower() for n in names}))

    def test_unknown_key_keeps_source_title_first(self):
        self.assertEqual(build.display_names("x.yesmoviesaction", "yes Movies Action", {"x.yesmoviesaction": ["yes 2"]}),
                         ["yes Movies Action", "yes 2"])

    def test_case_duplicate_dropped(self):
        names = build.display_names("hop", "HOP", {})
        self.assertEqual([n.lower() for n in names].count("hop"), 1)


class CanonAdditions(unittest.TestCase):
    def test_yes_and_kids_channels_have_hebrew_first(self):
        for title, key, hebrew in [("yes Movies Action", "yesmoviesaction", "yes סרטים אקשן"),
                                   ("yes Docu HD", "yesdocu", "yes דוקו"),
                                   ("HOP! Childhood", "hopchildhood", "הופ ילדות"),
                                   ("History SD", "history", "היסטוריה"),
                                   ("Disney Junior", "disneyjunior", "דיסני ג'וניור")]:
            self.assertEqual(build.canon_of(title), key, title)
            self.assertEqual(build.CANON[key][0][0], hebrew, key)

    def test_freetv_channels_have_english_names(self):
        for title, key, english in [("FreeTV סרטים פעולה", "freetvmoviesaction", "FreeTV Movies Action"),
                                    ("FreeTV סדרות קומדיה", "freetvseriescomedy", "FreeTV Comedy"),
                                    ("FreeTV דוקו", "freetvdocu", "FreeTV Docu")]:
            self.assertEqual(build.canon_of(title), key, title)
            self.assertIn(english, build.CANON[key][0])
            self.assertEqual(build.CANON[key][0][0], title)

    def test_existing_keys_unchanged(self):
        self.assertEqual(build.canon_of("Keshet HD"), "keshet12")
        self.assertEqual(build.canon_of("ערוץ 11"), "kan11")
        self.assertEqual(build.canon_of("Sport 5 4K"), "sport54k")


SAMPLE_XMLTV = """<?xml version="1.0" encoding="UTF-8"?>
<tv>
  <channel id="ch12.il">
    <display-name>ערוץ 12 שידור חי</display-name>
    <icon src="http://x/12.png" />
  </channel>
  <channel id="cinema1.il">
    <display-name>הוט סינמה 1</display-name>
  </channel>
  <programme start="20261111180000 +0000" stop="20261111190000 +0000" channel="ch12.il">
    <title>חדשות</title>
    <desc>מהדורת הערב</desc>
  </programme>
  <programme start="20261111190000 +0000" stop="20261111200000 +0000" channel="cinema1.il">
    <title>סרט</title>
  </programme>
  <programme start="20261111200000 +0000" stop="20261111210000 +0000" channel="missing.il">
    <title>אין ערוץ</title>
  </programme>
</tv>
""".encode("utf-8")


class LiveAndSuffixNames(unittest.TestCase):
    """EPGShare ו-Open-EPG קוראים לאותם ערוצים "שידור חי" ו-".il". בלי זה כל ערוץ היה נכנס פעמיים."""

    def test_live_suffix_is_the_same_channel(self):
        self.assertEqual(build.canon_of("ערוץ 12 שידור חי"), "keshet12")
        self.assertEqual(build.canon_of("ערוץ 11 כאן שידור חי"), "kan11")
        self.assertEqual(build.canon_of("ערוץ 13 בשידור חי"), "reshet13")

    def test_il_suffix_is_the_same_channel(self):
        self.assertEqual(build.canon_of("ערוץ 24.il"), build.canon_of("ערוץ 24"))
        self.assertEqual(build.canon_of("MTV.il"), build.canon_of("MTV"))

    def test_a_pipe_tail_is_dropped(self):
        self.assertEqual(build.canon_of("ערוץ 12 | לוח השידורים המלא של קשת 12.il"), "keshet12")
        self.assertEqual(build.canon_of("ערוץ 11 | תאגיד השידור הישראלי"), "kan11")

    def test_a_name_that_really_holds_live_is_not_merged_away(self):
        self.assertNotEqual(build.canon_of("ספורט 5 לייב"), build.canon_of("ספורט 5"))


class DisplayNamesAreMatchedToo(unittest.TestCase):
    """שם התצוגה של ערוץ הוא גם שם שמקור עשוי להשתמש בו. בלי זה "ספורט 5" נכנס כערוץ שני לצד sport5."""

    def test_a_display_name_finds_its_key(self):
        self.assertEqual(build.canon_of("ספורט 5"), "sport5")
        self.assertEqual(build.canon_of("יורוספורט 1"), "eurosport1")
        self.assertEqual(build.canon_of("ניקלודיאון"), "nickelodeon")
        self.assertEqual(build.canon_of("i24NEWS English"), "i24en")
        self.assertEqual(build.canon_of("דיסני ג'וניור"), "disneyjunior")

    def test_an_explicit_source_name_always_wins(self):
        for key, (_, names) in build.CANON.items():
            for n in names:
                self.assertEqual(build.canon_of(n), key, n)


class ChannelWordPrefix(unittest.TestCase):
    """EPGShare מקדים "ערוץ" לשמות ("ערוץ דיסקברי", "ערוץ אגו"). הקידומת נופלת רק כשהשם המלא לא נמצא."""

    def test_the_prefix_is_dropped_when_the_full_name_is_unknown(self):
        self.assertEqual(build.canon_of("ערוץ דיסקברי"), "discovery")
        self.assertEqual(build.canon_of("ערוץ אגו שידור חי"), "ego")
        self.assertEqual(build.canon_of("ערוץ TeenNick"), "teennick")

    def test_a_name_that_starts_with_the_word_is_not_broken(self):
        self.assertEqual(build.canon_of("ערוץ 11"), "kan11")
        self.assertEqual(build.canon_of("ערוץ 12"), "keshet12")
        self.assertEqual(build.canon_of("ערוץ 9"), "ch9")

    def test_channels_the_outside_guides_add_have_keys(self):
        for title, key in [("ערוץ ויוה", "viva"),
                           ("ויוה פרימיום", "vivapremium"),
                           ("ערוץ נשיונל גיאוגרפיק", "natgeo"),
                           ("נ. ג’יאוגרפיק WILD", "natgeowild"),
                           ("ערוץ האופנה FTV", "ftv"),
                           ("ערוץ הטיולים", "travel"),
                           ("ערוץ הבידור E", "echannel"),
                           ("ערוץ 24", "music24"),
                           ("i24news בעברית", "i24he")]:
            self.assertEqual(build.canon_of(title), key, title)


class XmltvSource(unittest.TestCase):
    def test_channels_and_programmes_are_read(self):
        by_key = {c.key: c for c in build.xmltv_channels(SAMPLE_XMLTV, "epgshare")}
        self.assertIn("keshet12", by_key)
        self.assertEqual(by_key["keshet12"].source, "epgshare")
        self.assertEqual(len(by_key["keshet12"].programmes), 1)
        self.assertEqual(by_key["keshet12"].programmes[0][2], "חדשות")
        self.assertEqual(by_key["keshet12"].programmes[0][3], "מהדורת הערב")

    def test_an_icon_is_kept(self):
        by_key = {c.key: c for c in build.xmltv_channels(SAMPLE_XMLTV, "epgshare")}
        self.assertEqual(by_key["keshet12"].icon, "http://x/12.png")

    def test_a_programme_without_a_channel_is_dropped(self):
        keys = {c.key for c in build.xmltv_channels(SAMPLE_XMLTV, "epgshare")}
        self.assertNotIn("x.איןערוץ", keys)

    def test_times_are_utc(self):
        import datetime as dt
        by_key = {c.key: c for c in build.xmltv_channels(SAMPLE_XMLTV, "epgshare")}
        self.assertEqual(by_key["keshet12"].programmes[0][0], dt.datetime(2026, 11, 11, 18, 0, tzinfo=dt.timezone.utc))


class SourcePriority(unittest.TestCase):
    def test_the_outside_guides_rank_after_the_direct_ones(self):
        for name in ("epgshare", "openepg"):
            self.assertIn(name, build.PRIORITY)
            self.assertGreater(build.PRIORITY[name], max(build.PRIORITY[n] for n in ("freetv", "cellcom", "yes")))

    def test_a_direct_source_wins_at_the_same_reach(self):
        import datetime as dt
        now = dt.datetime(2026, 11, 11, tzinfo=dt.timezone.utc)
        end = now + dt.timedelta(days=7)
        direct, outside = build.Channel("yes", "1", "ערוץ 12"), build.Channel("epgshare", "2", "ערוץ 12 שידור חי")
        direct.programmes.append((now, end, "a", None, None, None))
        outside.programmes.append((now, end, "b", None, None, None))
        self.assertEqual(build.pick([outside, direct], now)[0].source, "yes")

    def test_the_outside_guide_wins_when_it_reaches_much_further(self):
        import datetime as dt
        now = dt.datetime(2026, 11, 11, tzinfo=dt.timezone.utc)
        direct, outside = build.Channel("yes", "1", "ערוץ 12"), build.Channel("epgshare", "2", "ערוץ 12 שידור חי")
        direct.programmes.append((now, now + dt.timedelta(days=1), "a", None, None, None))
        outside.programmes.append((now, now + dt.timedelta(days=7), "b", None, None, None))
        self.assertEqual(build.pick([outside, direct], now)[0].source, "epgshare")


class MissingChannelsAreNamed(unittest.TestCase):
    """הערוצים שרק EPGShare ו-Open-EPG מכסים מקבלים מפתח קנוני ושם, ולא "x.<שם>"."""

    def test_hot_and_sport5_family_have_keys(self):
        for title, key in [("הוט סינמה 1", "hotcinema1"),
                           ("הוט סינמה 2", "hotcinema2"),
                           ("הוט סינמה 3", "hotcinema3"),
                           ("הוט בידור ישראלי", "hotisraeli"),
                           ("5GOLD", "sport5gold"),
                           ("5LIVE", "sport5live"),
                           ("5PLUS", "sport5plus"),
                           ("5STARS", "sport5stars")]:
            self.assertEqual(build.canon_of(title), key, title)
            self.assertTrue(build.CANON[key][0], key)

    def test_foreign_channels_have_keys(self):
        for title, key in [("אל ג'זירה", "aljazeera"),
                           ("MTV", "mtv"),
                           ("DW רוסית", "dwrussian"),
                           ("ישראל 33", "israel33")]:
            self.assertEqual(build.canon_of(title), key, title)
            self.assertTrue(build.CANON[key][0], key)


class ReportMarkdown(unittest.TestCase):
    def test_table_rows_and_escaping(self):
        import datetime as dt
        now = dt.datetime(2026, 11, 8, 20, 0, tzinfo=dt.timezone.utc)
        report = {"built": "2026-11-08T20:00:00+00:00",
                  "sources": {"yes": {"channels": 1, "programmes": 10, "seconds": 1.0, "until": "2026-11-15T00:00+00:00"}},
                  "per_channel": {"kan11": {"source": "freetv", "title": "ערוץ 11", "until": "2026-11-20T22:00+00:00"}}}
        md = build.report_markdown(report, {"kan11": ["כאן 11", "Kan 11", "a|b"]}, now)
        self.assertIn("| kan11 | כאן 11 · Kan 11 · a\\|b | freetv | 2026-11-20 22:00 | 12 |", md)
        self.assertIn("| yes | 1 | 10 |", md)


if __name__ == "__main__":
    unittest.main()
