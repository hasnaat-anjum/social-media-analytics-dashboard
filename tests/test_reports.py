"""Tests for the store (atomic saves, .bak, round-trips) and the
report generators (all four formats produce real content)."""

import json
import os
import tempfile
import unittest
from datetime import datetime

from smad.analytics import platform_summary
from smad.models import Post, Snapshot, Store
from smad.reports import (
    csv_export,
    html_report,
    json_report,
    markdown_report,
    terminal_dashboard,
)
from smad.store import load_store, save_store


def sample_posts():
    return [
        Post(platform="instagram", date=datetime(2026, 11, 2, 19, 0),
             caption="Launch #freelance", content_type="reel",
             likes=200, comments=20, shares=10, saves=30, reach=4000,
             impressions=5000, post_id="p1"),
        Post(platform="instagram", date=datetime(2026, 11, 9, 19, 0),
             caption="Tips #freelance #tools", content_type="reel",
             likes=180, comments=15, shares=8, saves=25, reach=3800,
             impressions=4600, post_id="p2"),
        Post(platform="tiktok", date=datetime(2026, 11, 3, 18, 0),
             caption="Quick tips", content_type="video",
             likes=900, comments=60, shares=120, saves=80, reach=20000,
             impressions=20000, post_id="t1"),
    ]


class TestStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "data.json")

    def tearDown(self):
        self.tmp.cleanup()

    def test_round_trip(self):
        store = Store(posts=sample_posts(),
                      snapshots=[Snapshot("instagram", datetime(2026, 11, 1), 1000)],
                      followers={"instagram": 1200})
        save_store(store, self.path)
        loaded = load_store(self.path)
        self.assertEqual(len(loaded.posts), 3)
        self.assertEqual(loaded.posts[0].post_id, "p1")
        self.assertEqual(loaded.posts[0].engagement, 260)
        self.assertEqual(loaded.snapshots[0].followers, 1000)
        self.assertEqual(loaded.followers["instagram"], 1200)

    def test_missing_file_is_empty_store(self):
        loaded = load_store(self.path)
        self.assertEqual(loaded.posts, [])
        self.assertEqual(loaded.snapshots, [])

    def test_bak_kept_after_second_save(self):
        store = Store(posts=sample_posts()[:1])
        save_store(store, self.path)
        store.posts = sample_posts()
        save_store(store, self.path)
        self.assertTrue(os.path.exists(self.path + ".bak"))
        with open(self.path + ".bak", encoding="utf-8") as handle:
            bak = json.load(handle)
        self.assertEqual(len(bak["posts"]), 1)

    def test_save_is_atomic(self):
        # After a save, the file is always complete valid JSON.
        store = Store(posts=sample_posts())
        save_store(store, self.path)
        with open(self.path, encoding="utf-8") as handle:
            data = json.load(handle)
        self.assertEqual(len(data["posts"]), 3)


class TestReports(unittest.TestCase):
    def setUp(self):
        self.posts = sample_posts()
        self.snapshots = [
            Snapshot("instagram", datetime(2026, 11, 1), 1000),
            Snapshot("instagram", datetime(2026, 11, 11), 1150),
        ]

    def test_terminal_dashboard(self):
        text = terminal_dashboard(self.posts, self.snapshots)
        self.assertIn("Posts analysed:  3", text)
        self.assertIn("instagram", text)
        self.assertIn("tiktok", text)
        self.assertIn("Best times", text)
        self.assertIn("Recommendations", text)

    def test_terminal_dashboard_empty(self):
        text = terminal_dashboard([], [])
        self.assertIn("No posts yet", text)

    def test_markdown_report(self):
        text = markdown_report(self.posts, self.snapshots)
        self.assertIn("# Social Media Analytics Report", text)
        self.assertIn("## By platform", text)
        self.assertIn("## Recommendations", text)
        self.assertIn("instagram", text)

    def test_json_report(self):
        payload = json.loads(json_report(self.posts, self.snapshots))
        self.assertEqual(payload["posts_analysed"], 3)
        self.assertEqual(payload["overall"]["posts"], 3)
        self.assertIn("instagram", payload["by_platform"])
        self.assertEqual(len(payload["posts"]), 3)
        self.assertTrue(payload["recommendations"])

    def test_csv_export(self):
        text = csv_export(self.posts)
        lines = text.strip().splitlines()
        self.assertEqual(len(lines), 4)  # header + 3 posts
        self.assertIn("engagement_rate", lines[0])
        self.assertIn("p1", text)

    def test_html_report(self):
        text = html_report(self.posts, self.snapshots)
        self.assertIn("<!DOCTYPE html>", text)
        self.assertIn("instagram", text)
        self.assertIn("<svg", text)  # weekly reach chart
        self.assertIn("Recommendations", text)
        # No external requests: no script tags, no http links.
        self.assertNotIn("<script", text)
        self.assertNotIn("http://", text)
        self.assertNotIn("https://", text)

    def test_html_escapes_captions(self):
        posts = [Post(platform="x", date=datetime(2026, 11, 2, 12, 0),
                      caption="<script>alert(1)</script>", likes=5, reach=100)]
        text = html_report(posts, [])
        self.assertNotIn("<script>alert(1)</script>", text)
        self.assertIn("&lt;script&gt;", text)


if __name__ == "__main__":
    unittest.main()
