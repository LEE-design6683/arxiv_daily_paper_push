import unittest

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


if __name__ == '__main__':
    unittest.main()
