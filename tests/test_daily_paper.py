import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import daily_paper


class DailyPaperTests(unittest.TestCase):
    def test_keywords_include_emri_and_imri(self):
        kws = [k.lower() for k in daily_paper.EMRI_KEYWORDS]
        self.assertIn('emri', kws)
        self.assertIn('imri', kws)

    def test_is_emri_related(self):
        text = 'This work studies extreme mass ratio inspiral waveforms for LISA.'
        self.assertTrue(daily_paper.is_emri_related(text))

    def test_filter_emri_papers_and_deduplicate(self):
        items = [
            {'id': '2501.00001', 'title': 'EMRI with Kerr geodesic', 'subjects': '', 'comments': ''},
            {'id': '2501.00001', 'title': 'EMRI duplicate', 'subjects': '', 'comments': ''},
            {'id': '2501.00002', 'title': 'Unrelated cosmology paper', 'subjects': '', 'comments': ''},
            {'id': '2501.00003', 'title': 'Inspiral in LISA band', 'subjects': '', 'comments': ''},
        ]
        out = daily_paper.filter_emri_papers(items)
        ids = [i['id'] for i in out]
        self.assertEqual(ids, ['2501.00001', '2501.00003'])

    def test_announcement_window(self):
        now_utc = datetime(2026, 3, 3, 3, 0, 0, tzinfo=timezone.utc)
        start_utc, end_utc = daily_paper.announcement_window_utc(now_utc)
        self.assertLess(start_utc, end_utc)

    def test_filter_by_announcement_window(self):
        now_utc = datetime(2026, 3, 3, 3, 0, 0, tzinfo=timezone.utc)
        start_utc, end_utc = daily_paper.announcement_window_utc(now_utc)
        inside = start_utc + (end_utc - start_utc) / 2
        outside = start_utc - (end_utc - start_utc)
        items = [
            {"id": "1", "updated_at": inside},
            {"id": "2", "updated_at": outside},
            {"id": "3", "updated_at": None},
        ]
        out = daily_paper.filter_by_announcement_window(items, now_utc=now_utc)
        self.assertEqual([i["id"] for i in out], ["1", "3"])

    def test_strict_emri_filter(self):
        self.assertTrue(daily_paper.is_strict_emri_related("EMRI waveform in Kerr background"))
        self.assertTrue(daily_paper.is_strict_emri_related("LISA inspiral with self-force around black hole"))
        self.assertFalse(daily_paper.is_strict_emri_related("pulsar machine learning with Taiji pipeline"))

    def test_getenv_nonempty_fallback(self):
        with patch.dict("os.environ", {"ARXIV_NEW_CATEGORIES": "   "}, clear=False):
            self.assertEqual(
                daily_paper.getenv_nonempty("ARXIV_NEW_CATEGORIES", "astro-ph,gr-qc"),
                "astro-ph,gr-qc",
            )


if __name__ == '__main__':
    unittest.main()
