"""בדיקות לפונקציות הטהורות של sports.py (בלי רשת). הרצה: python -m unittest test_sports -v"""
import unittest

import sports

GAMES_RAW = {
    "games": [
        {
            "id": 4739294, "sportId": 1, "competitionId": 42, "competitionDisplayName": "ליגת העל",
            "startTime": "2026-11-06T12:00:00+00:00", "statusText": "הסתיים", "shortStatusText": "הסתיים",
            "statusGroup": 4, "gameTime": 90.0, "roundNum": 10,
            "homeCompetitor": {"id": 566, "name": "מכבי תל אביב", "symbolicName": "MTA", "score": 2.0, "color": "#FFEE05"},
            "awayCompetitor": {"id": 564, "name": "מכבי פתח תקוה", "symbolicName": "MPT", "score": 2.0, "color": "#00843D"},
        },
        {
            "id": 4739300, "sportId": 1, "competitionId": 42, "competitionDisplayName": "ליגת העל",
            "startTime": "2026-11-14T18:30:00+00:00", "statusText": "טרם החל", "statusGroup": 1,
            "gameTime": -1.0, "roundNum": 11,
            "homeCompetitor": {"id": 567, "name": "הפועל תל אביב", "symbolicName": "HTA", "score": -1.0},
            "awayCompetitor": {"id": 568, "name": "מכבי חיפה", "symbolicName": "MHA", "score": -1.0},
        },
        {"id": 1, "competitionId": 42, "startTime": "", "homeCompetitor": {}, "awayCompetitor": {}},
    ]
}

TABLE_RAW = {
    "standings": [{
        "competitionId": 42,
        "rows": [
            # recentForm מגיע כרשימת מספרים (נמדד 11.11.2026), לא כמחרוזת "WWDWW".
            {"position": 1, "points": 25.0, "gamePlayed": 10, "gamesWon": 8, "gamesEven": 1, "gamesLost": 1,
             "for": 21, "against": 6, "recentForm": [1, 1, 2, 1, 1],
             "competitor": {"id": 567, "name": "הפועל תל אביב", "symbolicName": "HTA", "color": "#CC0000"}},
            {"position": 2, "points": 24.0, "gamePlayed": 10, "gamesWon": 7, "gamesEven": 3, "gamesLost": 0,
             "for": 18, "against": 7,
             "competitor": {"id": 566, "name": "מכבי תל אביב", "symbolicName": "MTA"}},
        ],
    }]
}


class Games(unittest.TestCase):
    def test_a_finished_game_keeps_its_score_and_hebrew_names(self):
        g = sports.parse_games(GAMES_RAW)[0]
        self.assertEqual(g["id"], 4739294)
        self.assertEqual(g["comp"], 42)
        self.assertEqual(g["status"], "הסתיים")
        self.assertEqual(g["home"]["name"], "מכבי תל אביב")
        self.assertEqual(g["home"]["score"], 2)
        self.assertEqual(g["away"]["score"], 2)
        self.assertEqual(g["round"], 10)

    def test_a_game_that_has_not_started_has_no_score(self):
        g = sports.parse_games(GAMES_RAW)[1]
        self.assertIsNone(g["home"]["score"])
        self.assertIsNone(g["away"]["score"])
        self.assertIsNone(g["minute"])

    def test_the_minute_is_kept_only_while_it_means_something(self):
        self.assertEqual(sports.parse_games(GAMES_RAW)[0]["minute"], 90)

    def test_a_game_without_sides_is_dropped(self):
        self.assertEqual(2, len(sports.parse_games(GAMES_RAW)))

    def test_nothing_at_all_gives_nothing(self):
        self.assertEqual([], sports.parse_games({}))
        self.assertEqual([], sports.parse_games({"games": []}))


class Table(unittest.TestCase):
    def test_a_row_carries_what_a_table_shows(self):
        r = sports.parse_table(TABLE_RAW)[0]
        self.assertEqual(r["pos"], 1)
        self.assertEqual(r["team"], "הפועל תל אביב")
        self.assertEqual(r["played"], 10)
        self.assertEqual(r["points"], 25)
        self.assertEqual((r["w"], r["d"], r["l"]), (8, 1, 1))
        self.assertEqual((r["gf"], r["ga"]), (21, 6))

    def test_the_recent_form_comes_through_when_there_is_one(self):
        rows = sports.parse_table(TABLE_RAW)
        self.assertEqual(rows[0]["form"], [1, 1, 2, 1, 1])
        self.assertIsNone(rows[1]["form"])

    def test_the_whole_table_arrives_not_the_first_five_rows(self):
        self.assertEqual(2, len(sports.parse_table(TABLE_RAW)))

    def test_a_cup_without_a_table_gives_nothing(self):
        self.assertEqual([], sports.parse_table({"standings": []}))
        self.assertEqual([], sports.parse_table({}))


class Build(unittest.TestCase):
    def fake(self, path):
        if "/standings/" in path:
            return TABLE_RAW
        if "/games/" in path:
            return GAMES_RAW
        raise AssertionError("unexpected " + path)

    def test_it_collects_every_competition(self):
        doc = sports.build(self.fake, [sports.Comp(42, "ליגת העל", 1)])
        self.assertEqual([42], [c["id"] for c in doc["competitions"]])
        self.assertEqual(2, len(doc["games"]))
        self.assertEqual(2, len(doc["tables"]["42"]))
        self.assertTrue(doc["built"])

    def test_a_competition_that_fails_does_not_take_the_others_with_it(self):
        def flaky(path):
            if "competitions=43" in path:
                raise OSError("down")
            return self.fake(path)

        doc = sports.build(flaky, [sports.Comp(42, "ליגת העל", 1), sports.Comp(43, "ליגה לאומית", 1)])
        self.assertEqual(2, len(doc["games"]))
        self.assertIn("42", doc["tables"])
        self.assertNotIn("43", doc["tables"])
        self.assertEqual([43], doc["failed"])

    def test_every_israeli_competition_we_promise_is_in_the_list(self):
        ids = [c.id for c in sports.COMPETITIONS]
        for wanted in (42, 43, 47, 49, 546, 609):
            self.assertIn(wanted, ids)

    def test_a_run_that_brought_almost_nothing_is_refused(self):
        self.assertTrue(sports.too_little({"games": [], "tables": {}}))
        self.assertFalse(sports.too_little({"games": [1] * 20, "tables": {"42": [1]}}))


if __name__ == "__main__":
    unittest.main()
