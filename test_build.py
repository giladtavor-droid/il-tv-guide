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

    def test_existing_keys_unchanged(self):
        self.assertEqual(build.canon_of("Keshet HD"), "keshet12")
        self.assertEqual(build.canon_of("ערוץ 11"), "kan11")
        self.assertEqual(build.canon_of("Sport 5 4K"), "sport54k")


if __name__ == "__main__":
    unittest.main()
