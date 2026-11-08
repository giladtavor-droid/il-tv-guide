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
        self.assertEqual(a["reshet13"], ["yes 13", "YES 13"])
        self.assertEqual(a["kan11"], ["yes 11", "YES 11"])

    def test_duplicate_number_goes_to_both_channels(self):
        a = build.yes_number_aliases(YES_ITEMS)
        self.assertEqual(a[build.canon_of("Big Brother HD")], ["yes 26", "YES 26"])
        self.assertEqual(a[build.canon_of("yes 7 October")], ["yes 26", "YES 26"])

    def test_no_number_and_radio_are_skipped(self):
        a = build.yes_number_aliases(YES_ITEMS)
        self.assertNotIn(build.canon_of("Some Pack"), a)
        self.assertNotIn(build.canon_of("Radio X"), a)


if __name__ == "__main__":
    unittest.main()
