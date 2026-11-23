"""Tests for the CSV importers: platform detection, alias matching,
number/date parsing, de-duplication and bad-row handling."""

import unittest
from datetime import datetime

from smad.importers import (
    ImportError_,
    import_posts_from_text,
    sample_csv,
)
from smad.parseutils import parse_date, parse_number

INSTAGRAM_CSV = """Date,Caption,Media type,Likes,Comments,Shares,Saves,Reach,Impressions
2026-11-02 19:00,5 free tools #freelance #tools,Reel,842,96,41,128,12400,15800
2026-11-04 12:30,Morning routine,Image,231,18,4,22,3900,4600
"""

TIKTOK_CSV = """Video ID,Date,Caption,Video views,Likes,Comments,Shares,Saves
7482910031,2026-11-03 18:00,3 Canva tricks,48200,3900,214,980,1500
"""

LINKEDIN_CSV = """Post URL,Date,Impressions,Reactions,Comments,Reposts,Clicks
https://www.linkedin.com/posts/example-1,2026-11-02 09:00,8400,312,48,21,96
"""


class TestParseNumber(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(parse_number("1234"), 1234)
        self.assertEqual(parse_number(42), 42)
        self.assertEqual(parse_number("1,234"), 1234)

    def test_suffixes(self):
        self.assertEqual(parse_number("1.2k"), 1200)
        self.assertEqual(parse_number("2.5m"), 2_500_000)
        self.assertEqual(parse_number("3K"), 3000)

    def test_missing(self):
        self.assertEqual(parse_number(""), 0)
        self.assertEqual(parse_number(None), 0)
        self.assertEqual(parse_number("n/a"), 0)
        self.assertEqual(parse_number("-"), 0)

    def test_garbage(self):
        self.assertEqual(parse_number("abc"), 0)


class TestParseDate(unittest.TestCase):
    def test_iso(self):
        self.assertEqual(parse_date("2026-11-02"), datetime(2026, 11, 2))
        self.assertEqual(parse_date("2026-11-02 19:00"), datetime(2026, 11, 2, 19, 0))

    def test_day_first(self):
        self.assertEqual(parse_date("02/11/2026"), datetime(2026, 11, 2))

    def test_written(self):
        self.assertEqual(parse_date("12 Nov 2026"), datetime(2026, 11, 12))
        self.assertEqual(parse_date("Nov 12, 2026"), datetime(2026, 11, 12))

    def test_bad(self):
        self.assertIsNone(parse_date("not a date"))
        self.assertIsNone(parse_date(""))


class TestImporters(unittest.TestCase):
    def test_instagram_import(self):
        result = import_posts_from_text(INSTAGRAM_CSV)
        self.assertEqual(result.platform, "instagram")
        self.assertEqual(len(result.imported), 2)
        post = result.imported[0]
        self.assertEqual(post.likes, 842)
        self.assertEqual(post.engagement, 842 + 96 + 41 + 128)
        self.assertEqual(post.content_type, "reel")
        self.assertAlmostEqual(post.engagement_rate_by_reach(), 8.93, places=1)

    def test_tiktok_import(self):
        result = import_posts_from_text(TIKTOK_CSV)
        self.assertEqual(result.platform, "tiktok")
        post = result.imported[0]
        self.assertEqual(post.post_id, "7482910031")
        self.assertEqual(post.impressions, 48200)  # "Video views" -> impressions
        self.assertEqual(post.content_type, "post")

    def test_linkedin_import(self):
        result = import_posts_from_text(LINKEDIN_CSV)
        self.assertEqual(result.platform, "linkedin")
        post = result.imported[0]
        self.assertEqual(post.likes, 312)  # Reactions -> likes
        self.assertEqual(post.shares, 21)  # Reposts -> shares
        self.assertEqual(post.post_id, "https://www.linkedin.com/posts/example-1")

    def test_explicit_platform_wins(self):
        result = import_posts_from_text(INSTAGRAM_CSV, platform="facebook")
        self.assertEqual(result.platform, "facebook")
        self.assertEqual(result.imported[0].platform, "facebook")

    def test_dedup_on_reimport(self):
        first = import_posts_from_text(INSTAGRAM_CSV)
        keys = {p.key() for p in first.imported}
        second = import_posts_from_text(INSTAGRAM_CSV, existing_keys=keys)
        self.assertEqual(len(second.imported), 0)
        self.assertEqual(second.skipped_duplicates, 2)

    def test_bad_date_row_skipped(self):
        bad = INSTAGRAM_CSV + "yesterday,Bad row,Image,1,1,1,1,1,1\n"
        result = import_posts_from_text(bad)
        self.assertEqual(len(result.imported), 2)
        self.assertEqual(result.skipped_bad_rows, 1)

    def test_no_date_column_fails(self):
        with self.assertRaises(ImportError_):
            import_posts_from_text("Caption,Likes\nhello,5\n")

    def test_no_metric_column_fails(self):
        with self.assertRaises(ImportError_):
            import_posts_from_text("Date,Caption\n2026-11-02,hello\n")

    def test_empty_file_fails(self):
        with self.assertRaises(ImportError_):
            import_posts_from_text("")

    def test_generic_platform_column(self):
        csv_text = ("Date,Platform,Caption,Type,Likes,Comments,Shares,Reach,Impressions\n"
                    "2026-11-02 19:00,instagram,Launch,Reel,100,10,5,2000,2500\n"
                    "2026-11-03 18:00,tiktok,Clip,Video,500,20,30,8000,8000\n")
        result = import_posts_from_text(csv_text)
        self.assertEqual(len(result.imported), 2)
        self.assertEqual({p.platform for p in result.imported}, {"instagram", "tiktok"})

    def test_sample_csvs_import_cleanly(self):
        for platform in ("instagram", "tiktok", "linkedin", "facebook", "x", "generic"):
            result = import_posts_from_text(sample_csv(platform))
            self.assertGreater(len(result.imported), 0, platform)
            self.assertEqual(result.skipped_bad_rows, 0, platform)

    def test_k_suffix_numbers(self):
        csv_text = "Date,Caption,Likes,Reach\n2026-11-02,hello,1.2k,12k\n"
        result = import_posts_from_text(csv_text)
        self.assertEqual(result.imported[0].likes, 1200)
        self.assertEqual(result.imported[0].reach, 12000)

    def test_negative_metrics_become_zero(self):
        csv_text = "Date,Caption,Likes,Reach\n2026-11-02,hello,-1,100\n"
        result = import_posts_from_text(csv_text)
        self.assertEqual(result.imported[0].likes, 0)


if __name__ == "__main__":
    unittest.main()
