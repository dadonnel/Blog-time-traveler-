import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

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


if __name__ == "__main__":
    unittest.main()
