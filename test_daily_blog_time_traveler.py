import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import daily_blog_time_traveler as btt


class DiscoveryHelpersTest(unittest.TestCase):
    def test_canonical_source_url_normalizes_host(self):
        self.assertEqual(btt.canonical_source_url("https://Example.com/path?q=1"), "https://example.com/")

    def test_looks_like_blog_url_rejects_social_domains(self):
        self.assertFalse(btt.looks_like_blog_url("https://twitter.com/someuser"))
        self.assertFalse(btt.looks_like_blog_url("https://x.com/someuser"))

    def test_looks_like_blog_url_requires_blog_markers(self):
        self.assertTrue(btt.looks_like_blog_url("https://example.com/blog/"))
        self.assertFalse(btt.looks_like_blog_url("https://example.com/about/"))

    def test_extract_candidate_urls(self):
        doc = """
        <html><body>
        <a href="https://someblog.com/blog/post">Post</a>
        <a href="/news/">News</a>
        <a href="https://twitter.com/user">Social</a>
        </body></html>
        """
        got = btt.extract_candidate_urls(doc, "https://seed.com/")
        self.assertIn("https://someblog.com/", got)
        self.assertIn("https://seed.com/", got)
        self.assertEqual(len(got), 2)

    def test_registry_round_trip(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "registry.json"
            source = btt.BlogSource("Example Blog", "https://example.com/", "Technology", "low", origin="discovered")
            entry = btt.ArchiveEntry(
                year=2025,
                month_day="April 03",
                subject="Technology",
                popularity="low",
                blog_name="Example Blog",
                page_title="Example Post",
                original_url="https://example.com/blog/post",
                archive_url="https://web.archive.org/web/20250403120000/https://example.com/blog/post",
                timestamp="20250403120000",
            )
            updated = btt.update_source_registry({}, [source], [entry], seen_date=btt.dt.date(2026, 4, 3))
            btt.save_source_registry(path, updated)
            loaded = btt.load_source_registry(path)
            self.assertIn("example.com", loaded)
            self.assertEqual(loaded["example.com"]["success_count"], 1)


class CdxQueryFallbackTest(unittest.TestCase):
    def test_cdx_query_retries_json_with_smaller_limits(self):
        calls: list[str] = []

        def fake_fetch_json(url: str, timeout: int = 0, retries: int = 0, sleep_base: float = 0.0):
            calls.append(url)
            if "limit=40" in url:
                raise RuntimeError("timed out")
            return [["timestamp", "original"], ["20250404120000", "https://example.com/post"]]

        with patch.object(btt, "fetch_json", side_effect=fake_fetch_json):
            rows = btt.cdx_query("https://example.com/", btt.dt.date(2025, 4, 4), max_results=40)

        self.assertEqual(len(rows), 1)
        self.assertTrue(any("output=json" in call and "limit=20" in call for call in calls))

    def test_cdx_query_falls_back_to_text_after_json_failures(self):
        def fake_fetch_json(url: str, timeout: int = 0, retries: int = 0, sleep_base: float = 0.0):
            raise RuntimeError("json failed")

        def fake_fetch_text(
            url: str,
            timeout: int = 0,
            retries: int = 0,
            max_bytes: int = 0,
            use_stream_read: bool = False,
        ):
            if "limit=20" in url:
                return "20250404120000 https://example.com/post\n"
            raise RuntimeError("text failed")

        with patch.object(btt, "fetch_json", side_effect=fake_fetch_json), patch.object(
            btt, "fetch_text", side_effect=fake_fetch_text
        ):
            rows = btt.cdx_query("https://example.com/", btt.dt.date(2025, 4, 4), max_results=40)

        self.assertEqual(rows, [("20250404120000", "https://example.com/post")])


if __name__ == "__main__":
    unittest.main()
