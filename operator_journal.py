"""Local idempotency journal for the Alongside MCP operator."""

import argparse
import fcntl
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

STATE = Path(__file__).resolve().parent / 'state' / 'execution.json'
LEASE_MINUTES = 20


def now():
    return datetime.now(timezone.utc)


def change(path, operation):
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_suffix('.lock')
    with lock.open('a+') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        data = json.loads(path.read_text()) if path.exists() else {'orders': []}
        result = operation(data)
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(data, indent=2))
        os.replace(temporary, path)
        return result


def claim(path=STATE, reconcile=False):
    def update(data):
        if not reconcile and any(order['status'] == 'prepared' for order in data['orders']):
            raise ValueError('Unresolved order must be reconciled first')
        lease = data.get('lease')
        if lease and datetime.fromisoformat(lease['expires_at']) > now():
            raise ValueError('Another operator run holds the lease')
        run_id = str(uuid.uuid4())
        data['lease'] = {'run_id': run_id, 'expires_at': (now() + timedelta(minutes=LEASE_MINUTES)).isoformat()}
        return run_id
    return change(path, update)


def prepare(run_id, order, path=STATE):
    def update(data):
        lease = data.get('lease', {})
        if lease.get('run_id') != run_id or datetime.fromisoformat(lease['expires_at']) <= now():
            raise ValueError('Operator lease is not held')
        if any(item['status'] == 'prepared' for item in data['orders']):
            raise ValueError('Reconcile the preceding order first')
        ref_id = str(uuid.uuid4())
        data['orders'].append({'ref_id': ref_id, 'run_id': run_id, 'order': order, 'status': 'prepared', 'created_at': now().isoformat()})
        return ref_id
    return change(path, update)


def record(run_id, ref_id, status, broker_order_id=None, path=STATE):
    if status not in {'submitted', 'rejected', 'reconciled'}:
        raise ValueError('Invalid journal status')
    def update(data):
        lease = data.get('lease', {})
        if lease.get('run_id') != run_id or datetime.fromisoformat(lease['expires_at']) <= now():
            raise ValueError('Operator lease is not held')
        item = next((item for item in data['orders'] if item['ref_id'] == ref_id and (item['run_id'] == run_id or status == 'reconciled')), None)
        if not item or item['status'] != 'prepared':
            raise ValueError('Order is not awaiting an outcome')
        if status in {'submitted', 'reconciled'} and not broker_order_id:
            raise ValueError('Broker order ID is required')
        item.update(status=status, broker_order_id=broker_order_id, updated_at=now().isoformat())
    change(path, update)


def settle(run_id, ref_id, broker_state, path=STATE):
    if broker_state not in {'filled', 'cancelled', 'rejected', 'failed', 'voided'}:
        raise ValueError('Broker order is not final')
    def update(data):
        if data.get('lease', {}).get('run_id') != run_id:
            raise ValueError('Operator lease is not held')
        item = next((item for item in data['orders'] if item['ref_id'] == ref_id), None)
        if not item or item['status'] not in {'submitted', 'reconciled'}:
            raise ValueError('Order has no broker submission to settle')
        item.update(status=broker_state, updated_at=now().isoformat())
    change(path, update)


def release(run_id, path=STATE):
    def update(data):
        if data.get('lease', {}).get('run_id') != run_id:
            raise ValueError('Operator lease is not held')
        data.pop('lease')
    change(path, update)


def start_cycle(run_id, fingerprint, weights, filings_as_of, path=STATE):
    def update(data):
        if data.get('lease', {}).get('run_id') != run_id:
            raise ValueError('Operator lease is not held')
        cycle = data.get('cycle')
        if cycle and cycle.get('status') == 'in_progress':
            return cycle
        data['cycle'] = {'status': 'in_progress', 'fingerprint': fingerprint, 'weights': weights,
                         'filings_as_of': filings_as_of, 'started_at': now().isoformat()}
        return data['cycle']
    return change(path, update)


def complete_cycle(run_id, path=STATE):
    def update(data):
        if data.get('lease', {}).get('run_id') != run_id or data.get('cycle', {}).get('status') != 'in_progress':
            raise ValueError('No active cycle for this operator')
        if any(item['status'] in {'prepared', 'submitted', 'reconciled'} for item in data['orders']):
            raise ValueError('Unresolved order must be reconciled first')
        data['cycle']['status'] = 'completed'
        data['cycle']['completed_at'] = now().isoformat()
    change(path, update)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)
    claiming = sub.add_parser('claim'); claiming.add_argument('--reconcile', action='store_true')
    prepared = sub.add_parser('prepare')
    prepared.add_argument('run_id'); prepared.add_argument('symbol'); prepared.add_argument('side'); prepared.add_argument('amount')
    recorded = sub.add_parser('record')
    recorded.add_argument('run_id'); recorded.add_argument('ref_id'); recorded.add_argument('status'); recorded.add_argument('--broker-order-id')
    settled = sub.add_parser('settle')
    settled.add_argument('run_id'); settled.add_argument('ref_id'); settled.add_argument('broker_state')
    released = sub.add_parser('release'); released.add_argument('run_id')
    completed = sub.add_parser('complete'); completed.add_argument('run_id')
    args = parser.parse_args()
    try:
        if args.command == 'claim': print(claim(reconcile=args.reconcile))
        elif args.command == 'prepare':
            key = 'quantity' if args.side == 'sell' else 'dollar_amount'
            print(prepare(args.run_id, {'symbol': args.symbol, 'side': args.side, key: args.amount, 'type': 'market'}))
        elif args.command == 'record': record(args.run_id, args.ref_id, args.status, args.broker_order_id)
        elif args.command == 'settle': settle(args.run_id, args.ref_id, args.broker_state)
        elif args.command == 'complete': complete_cycle(args.run_id)
        else: release(args.run_id)
    except ValueError as error:
        parser.exit(1, str(error) + '\n')
