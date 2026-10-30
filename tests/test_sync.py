"""Unit tests — no network needed."""
import logging
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backup_download import (  # noqa: E402
    cleanup_old,
    load_config,
    parse_date_folder,
)


class TestDateParse(unittest.TestCase):
    def test_common_formats(self):
        self.assertEqual(parse_date_folder("29Oct2026"), date(2026, 10, 29))
        self.assertEqual(parse_date_folder("29-Oct-2026"), date(2026, 10, 29))
        self.assertEqual(parse_date_folder("2026-10-29"), date(2026, 10, 29))
        self.assertEqual(parse_date_folder("29.10.2026"), date(2026, 10, 29))
        self.assertEqual(parse_date_folder("20261029"), date(2026, 10, 29))

    def test_unknown_returns_none(self):
        self.assertIsNone(parse_date_folder("random_folder"))
        self.assertIsNone(parse_date_folder("backup_final"))


class TestCleanup(unittest.TestCase):
    def test_deletes_only_old_date_dirs(self):
        tmp = Path(tempfile.mkdtemp())
        today = date.today()
        old = (today - timedelta(days=40)).strftime("%d%b%Y")
        new = (today - timedelta(days=5)).strftime("%d%b%Y")
        (tmp / old).mkdir()
        (tmp / new).mkdir()
        (tmp / "random_folder").mkdir()
        log = logging.getLogger("test")
        deleted = cleanup_old(tmp, 30, dry_run=False, log=log, server_name="t")
        self.assertEqual(deleted, [old])
        self.assertFalse((tmp / old).exists())
        self.assertTrue((tmp / new).exists())
        self.assertTrue((tmp / "random_folder").exists())

    def test_dry_run_keeps_everything(self):
        tmp = Path(tempfile.mkdtemp())
        old = (date.today() - timedelta(days=40)).strftime("%d%b%Y")
        (tmp / old).mkdir()
        log = logging.getLogger("test")
        deleted = cleanup_old(tmp, 30, dry_run=True, log=log, server_name="t")
        self.assertEqual(deleted, [old])
        self.assertTrue((tmp / old).exists())


class TestConfig(unittest.TestCase):
    def test_example_loads(self):
        example = Path(__file__).resolve().parent.parent / "config.example.json"
        cfg = load_config(example)
        self.assertGreaterEqual(len(cfg["servers"]), 2)
        self.assertIn("schedule", cfg)


if __name__ == "__main__":
    unittest.main()
