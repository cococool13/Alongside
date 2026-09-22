"""Persist an explicit Alongside transition request; never place orders."""

import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from allocation import cap_weights
from book import blend_weights
from planner import portfolio_index

ALLOWED_CADENCES = {'on_filing'}
ALLOWED_ORDER_TYPES = {'market_regular'}


def resolve_target(site: Path, picks: list):
    if not isinstance(picks, list) or not 1 <= len(picks) <= 2:
        raise ValueError('Choose one or two portfolios')
    pilots, as_of = portfolio_index(site)
    ids = [item.get('id') for item in picks]
    if len(ids) != len(set(ids)) or any(identifier not in pilots for identifier in ids):
        raise ValueError('Invalid portfolio selection')
    if (date.today() - date.fromisoformat(as_of)).days > 3:
        raise ValueError('Portfolio data needs a refresh')
    for identifier in ids:
        row = pilots[identifier]
        if row.get('as_of'):
            max_age = 150 if row.get('kind') == '13f' else 60
            if (date.today() - date.fromisoformat(row['as_of'])).days > max_age:
                raise ValueError(f'{row["name"]} disclosure is too old to trade')
    percents = [float(item.get('percent', 0)) for item in picks]
    if any(not 0 < percent <= 100 for percent in percents) or abs(sum(percents) - 100) > .01:
        raise ValueError('Portfolio shares must total 100%')
    weights = cap_weights(blend_weights((percent / 100, pilots[identifier]['weights']) for identifier, percent in zip(ids, percents)))
    return weights, as_of, [{'id': identifier, 'name': pilots[identifier]['name'], 'percent': percent} for identifier, percent in zip(ids, percents)]


def request_mandate(site: Path, state: Path, body: dict):
    if body.get('confirm') != 'REPLACE QCC-1':
        raise ValueError('Explicit strategy replacement confirmation required')
    if body.get('cadence') not in ALLOWED_CADENCES or body.get('order_type') not in ALLOWED_ORDER_TYPES:
        raise ValueError('Unsupported trading cadence or order type')
    _weights, as_of, selected = resolve_target(site, body.get('picks'))
    path = state / 'mandate.json'
    if path.exists() and json.loads(path.read_text()).get('status') in {'requested', 'active'}:
        raise ValueError('An Alongside mandate already exists; resolve it before replacing')
    payload = {
        'status': 'requested', 'requested_at': datetime.now(timezone.utc).isoformat(),
        'picks': selected,
        'cadence': body['cadence'], 'order_type': body['order_type'], 'filings_as_of': as_of,
        'account_last4': '5634', 'max_name_weight': .20,
        'note': 'Transition request. No broker order has been placed by this action.',
    }
    state.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(payload, indent=2))
    os.replace(temporary, path)
    return payload


def promote_mandate(state: Path):
    """Called by the operator only after live broker and filing checks pass."""
    path = state / 'mandate.json'
    payload = json.loads(path.read_text())
    if payload.get('status') != 'requested':
        raise ValueError('No pending Alongside transition')
    payload['status'] = 'active'
    payload['activated_at'] = datetime.now(timezone.utc).isoformat()
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(payload, indent=2))
    os.replace(temporary, path)
    return payload


if __name__ == '__main__':
    if sys.argv[1:] != ['promote']:
        raise SystemExit('use: python3 mandate.py promote')
    promote_mandate(Path(__file__).resolve().parent / 'state')
