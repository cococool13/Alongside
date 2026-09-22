import unittest
from datetime import datetime, timedelta, timezone

from execution import order_intents


def snapshot(**overrides):
    value = {
        'account_number': '565755634', 'account_type': 'cash',
        'updated': datetime.now(timezone.utc).isoformat(),
        'account_value': '1000', 'buying_power': '0', 'open_orders': [],
        'positions': [{'symbol': 'OLD', 'quantity': '10', 'shares_available_for_sells': '10', 'price': '100'}],
    }
    value.update(overrides)
    return value


class ExecutionTests(unittest.TestCase):
    def test_sell_then_wait_then_buy(self):
        target = {'NEW': 1}
        sell = order_intents(target, snapshot())
        self.assertEqual(sell, {'phase': 'sell', 'orders': [{'symbol': 'OLD', 'side': 'sell', 'quantity': '10', 'type': 'market'}]})
        waiting = order_intents(target, snapshot(positions=[], buying_power='0'))
        self.assertEqual(waiting['phase'], 'await_settlement')
        ready = order_intents(target, snapshot(positions=[], buying_power='1000'))
        self.assertEqual(ready['orders'][0]['dollar_amount'], '1000.00')
        near_ready = order_intents(target, snapshot(positions=[], buying_power='990'))
        self.assertEqual(near_ready['orders'][0]['dollar_amount'], '990.00')

    def test_blocks_stale_and_open_orders(self):
        with self.assertRaisesRegex(ValueError, 'five minutes'):
            order_intents({'NEW': 1}, snapshot(updated=(datetime.now(timezone.utc) - timedelta(minutes=6)).isoformat()))
        with self.assertRaisesRegex(ValueError, 'open orders'):
            order_intents({'NEW': 1}, snapshot(open_orders=[{'state': 'queued'}]))

    def test_partial_sell_and_account_scope(self):
        plan = order_intents({'OLD': .5, 'NEW': .5}, snapshot())
        self.assertEqual(plan['orders'][0]['quantity'], '5.000000')
        with self.assertRaisesRegex(ValueError, 'designated'):
            order_intents({'NEW': 1}, snapshot(account_number='other'))


if __name__ == '__main__':
    unittest.main()
