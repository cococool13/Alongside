import { test } from 'node:test';
import { strict as assert } from 'node:assert';
import { agenticAccount, toolData } from '../broker.js';

test('parses Robinhood structured MCP account response', () => {
  const data = toolData({ structuredContent: { data: { accounts: [{ account_number: '1234' }] } } }, 'get_accounts');
  assert.equal(data.accounts[0].account_number, '1234');
});

test('requires exactly one active Agentic account', async () => {
  const account = await agenticAccount('unused', async () => ({ accounts: [
    { account_number: '11112222', agentic_allowed: false, state: 'active' },
    { account_number: '565755634', agentic_allowed: true, state: 'active', type: 'cash' },
  ] }));
  assert.deepEqual(account, { number: '565755634', last4: '5634', type: 'cash' });
  await assert.rejects(agenticAccount('unused', async () => ({ accounts: [] })), /No single active/);
});
