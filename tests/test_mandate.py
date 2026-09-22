import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from mandate import promote_mandate, request_mandate


class MandateTests(unittest.TestCase):
    def test_request_and_promote_are_separate(self):
        with tempfile.TemporaryDirectory() as tmp:
            site, state = Path(tmp) / 'site', Path(tmp) / 'state'
            site.mkdir()
            weights = {symbol: .2 for symbol in 'ABCDE'}
            (site / 'pilots.json').write_text(json.dumps({'as_of': date.today().isoformat(), 'pilots': [{'id': 'test', 'name': 'Test', 'kind': '13f', 'as_of': date.today().isoformat(), 'weights': weights}]}))
            body = {'picks': [{'id': 'test', 'percent': 100}], 'cadence': 'on_filing', 'order_type': 'market_regular', 'confirm': 'REPLACE QCC-1'}
            requested = request_mandate(site, state, body)
            self.assertEqual(requested['status'], 'requested')
            with self.assertRaisesRegex(ValueError, 'already exists'):
                request_mandate(site, state, body)
            self.assertEqual(promote_mandate(state)['status'], 'active')

    def test_confirmation_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, 'confirmation'):
                request_mandate(Path(tmp), Path(tmp), {})

    def test_calendar_rebalance_is_not_supported(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, 'Unsupported trading cadence'):
                request_mandate(Path(tmp), Path(tmp), {
                    'confirm': 'REPLACE QCC-1', 'cadence': 'monthly',
                    'order_type': 'market_regular', 'picks': [],
                })

    def test_old_disclosure_cannot_be_activated(self):
        with tempfile.TemporaryDirectory() as tmp:
            site, state = Path(tmp) / 'site', Path(tmp) / 'state'
            site.mkdir()
            (site / 'pilots.json').write_text(json.dumps({'as_of': date.today().isoformat(), 'pilots': [{'id': 'old', 'name': 'Old', 'kind': '13f', 'as_of': (date.today() - timedelta(days=151)).isoformat(), 'weights': {symbol: .2 for symbol in 'ABCDE'}}]}))
            with self.assertRaisesRegex(ValueError, 'too old'):
                request_mandate(site, state, {'picks': [{'id': 'old', 'percent': 100}], 'cadence': 'on_filing', 'order_type': 'market_regular', 'confirm': 'REPLACE QCC-1'})
