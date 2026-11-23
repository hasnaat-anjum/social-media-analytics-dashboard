"""Tests for the analytics engine: rates, best times, outliers,
hashtags, trends, growth and recommendations."""

import unittest
from datetime import datetime

from smad.analytics import (
    best_posting_times,
    content_type_performance,
    follower_growth,
    hashtag_performance,
    median,
    outlier_posts,
    per_platform_summary,
    platform_summary,
    posting_gaps,
    recommendations,
    top_posts,
    weekly_trend,
)
from smad.models import Post, Snapshot


def make_post(platform="instagram", date="2026-11-02 19:00", caption="",
              content_type="reel", likes=100, comments=10, shares=5, saves=5,
              reach=2000, impressions=2500, clicks=0, followers=5000,
              post_id=""):
    return Post(
        platform=platform, date=datetime.strptime(date, "%Y-%m-%d %H:%M"),
        caption=caption, content_type=content_type, likes=likes,
        comments=comments, shares=shares, saves=saves, reach=reach,
        impressions=impressions, clicks=clicks, followers_at_post=followers,
        post_id=post_id,
    )


class TestRates(unittest.TestCase):
    def test_engagement_and_er(self):
        post = make_post(likes=100, comments=10, shares=5, saves=5, reach=2000)
        self.assertEqual(post.engagement, 120)
        self.assertEqual(post.engagement_rate_by_reach(), 6.0)
        self.assertEqual(post.engagement_rate_by_followers(), 2.4)

    def test_no_reach_returns_none(self):
        post = make_post(reach=0, followers=0)
        self.assertIsNone(post.engagement_rate_by_reach())
        self.assertIsNone(post.engagement_rate_by_followers())

    def test_median(self):
        self.assertEqual(median([]), 0.0)
        self.assertEqual(median([3]), 3.0)
        self.assertEqual(median([1, 2, 3, 4]), 2.5)


class TestSummaries(unittest.TestCase):
    def setUp(self):
        self.posts = [
            make_post("instagram", "2026-11-02 19:00", likes=100, reach=2000),
            make_post("instagram", "2026-11-03 19:00", likes=200, reach=4000),
            make_post("tiktok", "2026-11-02 18:00", likes=500, reach=10000),
        ]

    def test_platform_summary(self):
        summary = platform_summary(self.posts)
        self.assertEqual(summary["posts"], 3)
        self.assertEqual(summary["reach"], 16000)
        # engagement: 120 + 220 + 520
        self.assertEqual(summary["engagement"], 860)
        self.assertAlmostEqual(summary["avg_er_reach"], 5.38, places=2)

    def test_empty_summary(self):
        summary = platform_summary([])
        self.assertEqual(summary["posts"], 0)
        self.assertIsNone(summary["avg_er_reach"])

    def test_per_platform_sorted_best_first(self):
        result = per_platform_summary(self.posts)
        # instagram: 340/6000 = 5.67%; tiktok: 520/10000 = 5.2%
        self.assertEqual(list(result.keys()), ["instagram", "tiktok"])


class TestBestTimes(unittest.TestCase):
    def test_top_slot_needs_two_posts(self):
        posts = [make_post(date="2026-11-02 19:00", likes=900, reach=1000)]  # Mon 19:00, huge ER
        times = best_posting_times(posts)
        self.assertEqual(times["top_slots"], [])  # one post is not a pattern

    def test_ranked_slots(self):
        posts = [
            make_post(date="2026-11-02 19:00", likes=180, reach=2000),  # Mon 19:00, ER 10%
            make_post(date="2026-11-09 19:00", likes=180, reach=2000),  # Mon 19:00 again
            make_post(date="2026-11-03 09:00", likes=20, reach=2000),   # Tue 09:00, ER 2%
            make_post(date="2026-11-10 09:00", likes=20, reach=2000),   # Tue 09:00 again
        ]
        times = best_posting_times(posts)
        self.assertEqual(times["top_slots"][0]["key"], (0, 19))  # Monday 19:00
        self.assertAlmostEqual(times["top_slots"][0]["avg_er"], 10.0, places=1)


class TestTopAndOutliers(unittest.TestCase):
    def test_top_by_engagement(self):
        posts = [make_post(post_id=str(i), likes=i * 10, reach=1000) for i in range(1, 6)]
        top = top_posts(posts, 2)
        self.assertEqual([p.post_id for p in top], ["5", "4"])

    def test_outliers(self):
        posts = [make_post(post_id=str(i), likes=100, reach=2000) for i in range(5)]
        posts.append(make_post(post_id="star", likes=900, reach=2000))
        outliers = outlier_posts(posts)
        self.assertEqual(len(outliers), 1)
        self.assertEqual(outliers[0]["post"].post_id, "star")
        self.assertGreater(outliers[0]["multiple"], 5.0)


class TestContentTypesAndHashtags(unittest.TestCase):
    def test_content_type_ranking(self):
        posts = [make_post(content_type="reel", likes=200, reach=2000) for _ in range(3)]
        posts += [make_post(content_type="image", likes=20, reach=2000) for _ in range(3)]
        rows = content_type_performance(posts)
        self.assertEqual(rows[0]["content_type"], "reel")
        self.assertGreater(rows[0]["avg_er"], rows[1]["avg_er"])

    def test_type_with_too_few_posts_skipped(self):
        posts = [make_post(content_type="reel", likes=200, reach=2000)]
        self.assertEqual(content_type_performance(posts), [])

    def test_hashtag_ranking(self):
        posts = [
            make_post(caption="hello #freelance #tools", likes=200, reach=2000),
            make_post(caption="again #freelance #tools", likes=200, reach=2000),
            make_post(caption="solo #once", likes=900, reach=2000),
        ]
        rows = hashtag_performance(posts)
        tags = [r["hashtag"] for r in rows]
        self.assertIn("#freelance", tags)
        self.assertIn("#tools", tags)
        self.assertNotIn("#once", tags)  # used once only


class TestTrendsAndGrowth(unittest.TestCase):
    def test_weekly_trend(self):
        posts = [
            make_post(date="2026-11-02 19:00", reach=1000),
            make_post(date="2026-11-03 19:00", reach=1000),
            make_post(date="2026-11-09 19:00", reach=3000),
        ]
        trend = weekly_trend(posts)
        self.assertEqual(len(trend), 2)
        self.assertEqual(trend[0]["posts"], 2)
        self.assertEqual(trend[1]["reach"], 3000)

    def test_follower_growth(self):
        snaps = [
            Snapshot("instagram", datetime(2026, 11, 1), 1000),
            Snapshot("instagram", datetime(2026, 11, 11), 1100),
        ]
        growth = follower_growth(snaps)
        self.assertEqual(growth["instagram"]["growth"], 100)
        self.assertEqual(growth["instagram"]["growth_pct"], 10.0)
        self.assertEqual(growth["instagram"]["per_day"], 10.0)

    def test_posting_gaps(self):
        posts = [
            make_post(date="2026-11-02 19:00"),
            make_post(date="2026-11-12 19:00"),
        ]
        gaps = posting_gaps(posts)
        self.assertEqual(len(gaps), 1)
        self.assertEqual(gaps[0]["days"], 10)


class TestRecommendations(unittest.TestCase):
    def test_empty_posts(self):
        findings = recommendations([], [])
        self.assertEqual(len(findings), 1)
        self.assertIn("No posts", findings[0]["title"])

    def test_best_slot_finding(self):
        posts = [
            make_post(date="2026-11-02 19:00", likes=180, reach=2000),
            make_post(date="2026-11-09 19:00", likes=180, reach=2000),
            make_post(date="2026-11-03 09:00", likes=20, reach=2000),
            make_post(date="2026-11-10 09:00", likes=20, reach=2000),
        ]
        titles = [f["title"] for f in recommendations(posts, [])]
        self.assertTrue(any("Monday" in t and "19:00" in t for t in titles))

    def test_weak_platform_warning(self):
        posts = [make_post("instagram", likes=400, reach=2000) for _ in range(3)]
        posts += [make_post("tiktok", likes=10, reach=2000) for _ in range(3)]
        titles = [f["title"] for f in recommendations(posts, [])]
        self.assertTrue(any("lags badly" in t for t in titles))


if __name__ == "__main__":
    unittest.main()
