import datetime as dt
import unittest

from watch import check_ledger, check_pins, check_schedule, first_tuesday

U = dt.timezone.utc


class Watch(unittest.TestCase):
    def test_first_tuesday(self):
        self.assertEqual(first_tuesday(2026, 12), dt.date(2026, 12, 1))
        self.assertEqual(first_tuesday(2027, 1), dt.date(2027, 1, 5))

    def test_nothing_before_start(self):
        self.assertEqual(check_schedule(dt.datetime(2026, 11, 18, 9, tzinfo=U), {'2026-11-17_210119': 1}, [], set()), [])

    def test_missing_archive_and_draw(self):
        now = dt.datetime(2026, 11, 24, 10, tzinfo=U)                     # mardi après le premier lundi programmé
        codes = [a['code'] for a in check_schedule(now, {'2026-11-17_210119': 1}, [], set())]
        self.assertIn('S-1', codes)
        codes = [a['code'] for a in check_schedule(now, {'2026-11-23_053100': 1}, [], set())]
        self.assertEqual(codes, ['S-2'])
        self.assertEqual(check_schedule(now, {'2026-11-23_053100': 1}, [], {'2026-11-23_053100'}), [])

    def test_missing_monthly_audit(self):
        now = dt.datetime(2026, 12, 1, 13, tzinfo=U)
        snaps, draws = {'2026-11-30_053100': 1}, {'2026-11-30_053100'}
        self.assertEqual([a['code'] for a in check_schedule(now, snaps, ['2026-11-17_20261117T210635Z'], draws)], ['S-3'])
        self.assertEqual(check_schedule(now, snaps, ['2026-11-30_20261201T073500Z'], draws), [])

    def test_deleted_or_rewritten_report(self):
        led = {'reports': {'a': '1', 'b': '2'}, 'snapshots': {'s': {'contenu': '9', 'tirage': None}}}
        cur = {'reports': {'a': '1', 'b': '3', 'c': '4'}, 'snapshots': {}}
        titles = [a['titre'] for a in check_ledger(led, cur)]
        self.assertEqual(len(titles), 2)
        self.assertTrue(any('modifié' in t and 'reports/b' in t for t in titles))
        self.assertTrue(any('supprimé' in t and 'snapshots/s' in t for t in titles))

    def test_draw_may_be_added_once_only(self):
        led = {'snapshots': {'s': {'contenu': '9', 'tirage': None}}}
        ok = {'reports': {}, 'snapshots': {'s': {'contenu': '9', 'tirage': 'd1'}}}
        self.assertEqual(check_ledger(led, ok), [])
        led = {'snapshots': {'s': {'contenu': '9', 'tirage': 'd1'}}}
        for bad in ({'contenu': '9', 'tirage': 'd2'}, {'contenu': '9', 'tirage': None}, {'contenu': '8', 'tirage': 'd1'}):
            self.assertEqual(len(check_ledger(led, {'reports': {}, 'snapshots': {'s': bad}})), 1)

    def test_mandate_change(self):
        self.assertEqual(len(check_pins({'m': 'x'}, {'m': 'y'})), 1)
        self.assertEqual(check_pins({'m': 'x'}, {'m': 'x'}), [])


if __name__ == '__main__':
    unittest.main()
