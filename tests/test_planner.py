import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from planner import build_proposal


class PlannerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.site = Path(self.tmp.name)
        (self.site / 'pilots.json').write_text(json.dumps({
            'as_of': '2026-09-22',
            'pilots': [
                {'id': 'a', 'name': 'A', 'weights': {'AAA': 1/3, 'AAC': 1/3, 'AAD': 1/3}},
                {'id': 'b', 'name': 'B', 'weights': {'BBB': .5, 'BBC': .5}},
            ],
        }))
        self.broker = {
            'updated': datetime.now(timezone.utc).isoformat(),
            'buying_power': 20,
            'positions': [{'symbol': 'OLD', 'value': 80}],
        }

    def tearDown(self):
        self.tmp.cleanup()

    def test_sell_and_split_buy_legs(self):
        plan = build_proposal(self.site, self.broker, [{'id': 'a', 'percent': 50}, {'id': 'b', 'percent': 50}])
        self.assertEqual([(o['symbol'], o['dollar_amount']) for o in plan['sell_orders']], [('OLD', '80.00')])
        self.assertEqual(sum(float(o['dollar_amount']) for o in plan['buy_orders_now']), 20)
        self.assertEqual(sum(float(o['dollar_amount']) for o in plan['buy_orders_after_settlement']), 80)
        self.assertEqual(plan['status'], 'draft_only')

    def test_rejects_stale_snapshot_and_bad_shares(self):
        self.broker['updated'] = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        with self.assertRaisesRegex(ValueError, 'stale'):
            build_proposal(self.site, self.broker, [{'id': 'a', 'percent': 100}])
        self.broker['updated'] = datetime.now(timezone.utc).isoformat()
        with self.assertRaisesRegex(ValueError, 'total 100'):
            build_proposal(self.site, self.broker, [{'id': 'a', 'percent': 30}])


if __name__ == '__main__':
    unittest.main()
