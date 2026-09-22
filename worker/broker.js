import { Client, StreamableHTTPClientTransport } from '@modelcontextprotocol/client';

const ENDPOINT = new URL('https://agent.robinhood.com/mcp/trading');

export async function callRobinhood(accessToken, name, args = {}) {
  const client = new Client({ name: 'Alongside', version: '1.0.0' });
  const transport = new StreamableHTTPClientTransport(ENDPOINT, {
    authProvider: { token: async () => accessToken },
  });
  try {
    await client.connect(transport);
    const result = await client.callTool({ name, arguments: args });
    if (result.isError) throw new Error(`Robinhood rejected ${name}`);
    if (result.structuredContent?.data) return result.structuredContent.data;
    const text = result.content?.find(item => item.type === 'text')?.text;
    const parsed = text && JSON.parse(text);
    if (parsed?.data) return parsed.data;
    throw new Error(`Robinhood returned no ${name} data`);
  } finally {
    await client.close().catch(() => {});
  }
}

export async function agenticAccount(accessToken) {
  const data = await callRobinhood(accessToken, 'get_accounts');
  const accounts = data.accounts?.filter(row => row?.agentic_allowed === true && row.state === 'active' && !row.deactivated && !row.permanently_deactivated) || [];
  if (accounts.length !== 1) throw new Error('No single active Agentic account');
  return { number: accounts[0].account_number, last4: accounts[0].account_number.slice(-4), type: accounts[0].type };
}
