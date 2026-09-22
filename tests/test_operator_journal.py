import tempfile
import unittest
from pathlib import Path
from operator_journal import claim, prepare, record, release, settle


class JournalTests(unittest.TestCase):
    def test_unresolved_order_blocks_next_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'execution.json'
            run = claim(path)
            ref = prepare(run, {'symbol': 'AAA', 'side': 'sell', 'quantity': '1', 'type': 'market'}, path)
            with self.assertRaisesRegex(ValueError, 'preceding'):
                prepare(run, {'symbol': 'BBB'}, path)
            release(run, path)
            with self.assertRaisesRegex(ValueError, 'Unresolved'):
                claim(path)
            recovery_run = claim(path, reconcile=True)
            record(recovery_run, ref, 'reconciled', 'confirmed-broker-id', path)
            release(recovery_run, path)
            self.assertTrue(claim(path))

    def test_submitted_order_requires_broker_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'execution.json'
            run = claim(path)
            ref = prepare(run, {'symbol': 'AAA'}, path)
            with self.assertRaisesRegex(ValueError, 'Broker order ID'):
                record(run, ref, 'submitted', path=path)
            record(run, ref, 'submitted', 'broker-id', path)
            settle(run, ref, 'filled', path)
            release(run, path)
            self.assertTrue(claim(path))
