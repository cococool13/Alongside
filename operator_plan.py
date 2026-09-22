"""Turn an active mandate and fresh MCP snapshot into one executable leg."""

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from execution import order_intents
from mandate import resolve_target
from operator_journal import complete_cycle, start_cycle
from planner import portfolio_index

ROOT = Path(__file__).resolve().parent


def fingerprint(site, picks):
    pilots, _as_of = portfolio_index(site)
    rows = [{'id': item['id'], 'percent': item['percent'], 'as_of': pilots[item['id']]['as_of'],
             'weights': pilots[item['id']]['weights']} for item in picks]
    return hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()


def plan(run_id, root=ROOT):
    state = root / 'state'
    mandate = json.loads((state / 'mandate.json').read_text())
    if mandate.get('status') != 'active' or mandate.get('order_type') != 'market_regular':
        raise ValueError('No active supported mandate')
    journal_path = state / 'execution.json'
    journal = json.loads(journal_path.read_text())
    lease = journal.get('lease', {})
    if lease.get('run_id') != run_id or datetime.fromisoformat(lease['expires_at']) <= datetime.now(timezone.utc):
        raise ValueError('Operator lease is not held')
    if any(item['status'] in {'prepared', 'submitted', 'reconciled'} for item in journal.get('orders', [])):
        raise ValueError('Reconcile or settle an unresolved order first')
    weights, as_of, _selected = resolve_target(root / 'site', mandate['picks'])
    current_fingerprint = fingerprint(root / 'site', mandate['picks'])
    cycle = journal.get('cycle')
    if cycle and cycle.get('status') == 'in_progress':
        weights = cycle['weights']
        as_of = cycle['filings_as_of']
        current_fingerprint = cycle['fingerprint']
    elif cycle and cycle.get('status') == 'completed':
        if cycle['fingerprint'] == current_fingerprint:
            return {'phase': 'idle', 'orders': []}
    snapshot = json.loads((state / 'live_snapshot.json').read_text())
    result = order_intents(weights, snapshot)
    if not cycle or cycle.get('status') != 'in_progress':
        start_cycle(run_id, current_fingerprint, weights, as_of, journal_path)
    if result['phase'] == 'complete':
        complete_cycle(run_id, journal_path)
    result['filings_as_of'] = as_of
    result['target_weights'] = weights
    return result


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('use: python3 operator_plan.py RUN_ID')
    print(json.dumps(plan(sys.argv[1]), indent=2))
