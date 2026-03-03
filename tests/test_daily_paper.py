import unittest
from datetime import datetime, timezone

import daily_paper


class FakeResult:
    def __init__(self, entry_id, title, summary, published):
        self.entry_id = entry_id
        self.title = title
        self.summary = summary
        self.published = published


class DailyPaperTests(unittest.TestCase):
    def test_emri_query_contains_expected_terms(self):
        query = daily_paper.build_arxiv_query()
        self.assertIn('EMRI', query)
        self.assertIn('"extreme mass ratio inspiral"', query)

    def test_max_results_is_large_enough(self):
        self.assertGreaterEqual(daily_paper.MAX_RESULTS, 100)

    def test_filter_today_and_deduplicate(self):
        now = datetime.now(timezone.utc)
        yesterday = now.replace(day=max(1, now.day - 1))

        items = [
            FakeResult('http://arxiv.org/abs/2501.00001v1', 'A', 's', now),
            FakeResult('http://arxiv.org/abs/2501.00001v2', 'A2', 's', now),
            FakeResult('http://arxiv.org/abs/2501.00002v1', 'B', 's', now),
            FakeResult('http://arxiv.org/abs/2501.99999v1', 'Old', 's', yesterday),
        ]

        filtered = daily_paper.filter_today_and_deduplicate(items, now=now)
        ids = [daily_paper.extract_arxiv_id(i.entry_id) for i in filtered]
        self.assertEqual(ids, ['2501.00001', '2501.00002'])


if __name__ == '__main__':
    unittest.main()
