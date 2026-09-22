import json
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from operator_journal import claim, release
from operator_plan import plan


class OperatorPlanTests(unittest.TestCase):
    def test_cycle_starts_then_idles_when_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'site').mkdir(); (root / 'state').mkdir()
            weights = {symbol: .2 for symbol in 'ABCDE'}
            (root / 'site' / 'pilots.json').write_text(json.dumps({'as_of': date.today().isoformat(), 'pilots': [{'id': 'chosen', 'name': 'Chosen', 'kind': '13f', 'as_of': date.today().isoformat(), 'weights': weights}]}))
            (root / 'state' / 'mandate.json').write_text(json.dumps({'status': 'active', 'order_type': 'market_regular', 'cadence': 'on_filing', 'picks': [{'id': 'chosen', 'percent': 100}]}))
            (root / 'state' / 'live_snapshot.json').write_text(json.dumps({'account_number': '565755634', 'account_type': 'cash', 'updated': datetime.now(timezone.utc).isoformat(), 'account_value': '1000', 'buying_power': '0', 'open_orders': [], 'positions': [{'symbol': symbol, 'quantity': '2', 'shares_available_for_sells': '2', 'price': '100'} for symbol in 'ABCDE']}))
            journal = root / 'state' / 'execution.json'
            run = claim(journal)
            self.assertEqual(plan(run, root)['phase'], 'complete')
            release(run, journal)
            later = claim(journal)
            self.assertEqual(plan(later, root)['phase'], 'idle')
