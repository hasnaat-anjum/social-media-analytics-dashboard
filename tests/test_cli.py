"""End-to-end CLI tests: import -> dashboard -> report, plus the
small commands (add, snapshot, remove, set-followers, example)."""

import json
import os
import tempfile
import unittest
from io import StringIO
from unittest import mock

from smad.cli import main
from smad.importers import sample_csv
from smad.store import load_store

INSTAGRAM_CSV = sample_csv("instagram")


class CliTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = os.path.join(self.tmp.name, "data.json")
        self.csv_path = os.path.join(self.tmp.name, "ig.csv")
        with open(self.csv_path, "w", encoding="utf-8") as handle:
            handle.write(INSTAGRAM_CSV)

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, argv):
        with mock.patch("sys.stdout", new_callable=StringIO) as out:
            code = main(argv + ["--data", self.data])
        return code, out.getvalue()

    def test_import_then_dashboard(self):
        code, out = self.run_cli(["import", self.csv_path])
        self.assertEqual(code, 0)
        self.assertIn("Imported 5 posts", out)
        store = load_store(self.data)
        self.assertEqual(len(store.posts), 5)

        code, out = self.run_cli(["dashboard"])
        self.assertEqual(code, 0)
        self.assertIn("Posts analysed:  5", out)
        self.assertIn("instagram", out)

    def test_reimport_is_deduped(self):
        self.run_cli(["import", self.csv_path])
        code, out = self.run_cli(["import", self.csv_path])
        self.assertEqual(code, 0)
        self.assertIn("Imported 0 posts", out)
        self.assertIn("Skipped 5 duplicate", out)
        self.assertEqual(len(load_store(self.data).posts), 5)

    def test_import_missing_file_fails(self):
        with mock.patch("sys.stderr", new_callable=StringIO):
            code, _ = self.run_cli(["import", os.path.join(self.tmp.name, "nope.csv")])
        self.assertEqual(code, 1)

    def test_add_and_remove(self):
        code, out = self.run_cli([
            "add", "--platform", "linkedin", "--date", "2026-11-20 09:00",
            "--caption", "Hello world", "--likes", "50", "--reach", "1000",
        ])
        self.assertEqual(code, 0)
        self.assertEqual(len(load_store(self.data).posts), 1)

        code, out = self.run_cli(["list"])
        self.assertIn("Hello world", out)

        # add again with same identity -> rejected
        with mock.patch("sys.stderr", new_callable=StringIO):
            code, _ = self.run_cli([
                "add", "--platform", "linkedin", "--date", "2026-11-20 09:00",
                "--caption", "Hello world", "--likes", "50", "--reach", "1000",
            ])
        self.assertEqual(code, 1)

        # remove needs an id; this post has none, so use --id "" is not
        # possible — instead verify list shows it and move on.
        code, out = self.run_cli(["top"])
        self.assertIn("Hello world", out)

    def test_remove_by_id(self):
        self.run_cli(["import", self.csv_path])
        store = load_store(self.data)
        # sample instagram rows have no IDs; give one an ID via add
        self.run_cli(["add", "--platform", "x", "--date", "2026-11-20 12:00",
                      "--id", "abc123", "--caption", "to delete",
                      "--likes", "5", "--reach", "100"])
        self.assertEqual(len(load_store(self.data).posts), 6)
        code, out = self.run_cli(["remove", "--id", "abc123"])
        self.assertEqual(code, 0)
        self.assertEqual(len(load_store(self.data).posts), 5)

    def test_snapshot_and_growth(self):
        self.run_cli(["snapshot", "--platform", "instagram", "--followers", "1000",
                      "--date", "2026-11-01"])
        self.run_cli(["snapshot", "--platform", "instagram", "--followers", "1200",
                      "--date", "2026-11-11"])
        code, out = self.run_cli(["snapshots"])
        self.assertEqual(code, 0)
        self.assertIn("instagram", out)
        self.assertIn("+20.00%", out)

    def test_report_formats(self):
        self.run_cli(["import", self.csv_path])
        for fmt, name in (("md", "report.md"), ("html", "report.html"),
                          ("json", "report.json"), ("csv", "report.csv")):
            out_path = os.path.join(self.tmp.name, name)
            code, out = self.run_cli(["report", "--format", fmt, "--out", out_path])
            self.assertEqual(code, 0, fmt)
            self.assertTrue(os.path.exists(out_path), fmt)
            self.assertGreater(os.path.getsize(out_path), 100, fmt)
        with open(os.path.join(self.tmp.name, "report.json"), encoding="utf-8") as handle:
            payload = json.load(handle)
        self.assertEqual(payload["posts_analysed"], 5)

    def test_best_times_and_hashtags(self):
        self.run_cli(["import", self.csv_path])
        code, out = self.run_cli(["best-times"])
        self.assertEqual(code, 0)
        # The sample CSV uses each hashtag once; add two posts sharing one tag.
        self.run_cli(["add", "--platform", "instagram", "--date", "2026-11-10 19:00",
                      "--caption", "More tips #freelance", "--likes", "300", "--reach", "5000"])
        self.run_cli(["add", "--platform", "instagram", "--date", "2026-11-11 19:00",
                      "--caption", "Even more #freelance", "--likes", "250", "--reach", "4500"])
        code, out = self.run_cli(["hashtags"])
        self.assertEqual(code, 0)
        self.assertIn("#freelance", out)

    def test_example_command(self):
        with mock.patch("sys.stdout", new_callable=StringIO) as out:
            code = main(["example", "tiktok"])
        self.assertEqual(code, 0)
        self.assertIn("Video ID", out.getvalue())

    def test_set_followers(self):
        code, out = self.run_cli(["set-followers", "--platform", "instagram", "--followers", "2500"])
        self.assertEqual(code, 0)
        self.assertEqual(load_store(self.data).followers["instagram"], 2500)


if __name__ == "__main__":
    unittest.main()
