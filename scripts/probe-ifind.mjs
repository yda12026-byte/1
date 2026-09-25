import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

function loadEnv(path) {
  const values = {};
  for (const line of readFileSync(path, 'utf8').split(/\r?\n/)) {
    const match = line.match(/^([A-Z][A-Z0-9_]*)=(.*)$/);
    if (match) values[match[1]] = match[2];
  }
  return values;
}

const env = loadEnv(resolve(process.cwd(), '.env'));
const token = env.IFIND_MCP_AUTH_TOKEN;
const unifiedUrl = env.IFIND_MCP_URL;
if (!token || !unifiedUrl) {
  console.error('IFIND_MCP_AUTH_TOKEN or IFIND_MCP_URL is missing from the local .env');
  process.exit(2);
}

const services = {
  stock: 'hexin-ifind-ds-stock-mcp',
  index: 'hexin-ifind-ds-index-mcp',
  edb: 'hexin-ifind-ds-edb-mcp',
  news: 'hexin-ifind-ds-news-mcp',
  global_stock: 'hexin-ifind-ds-global-stock-mcp',
};
const selected = process.argv.slice(2);
const types = selected.length ? selected : Object.keys(services);
for (const type of types) {
  if (!services[type]) {
    console.error(`Unknown iFinD service type: ${type}`);
    process.exit(2);
  }
}

const base = new URL(unifiedUrl);
if (base.protocol !== 'https:' || base.hostname !== 'api-mcp.51ifind.com' || base.port !== '8643' || !base.pathname.startsWith('/ds-mcp-servers/')) {
  console.error('IFIND_MCP_URL must be the official iFinD MCP endpoint');
  process.exit(2);
}
const prefix = base.pathname.replace(/\/[^/]+\/?$/, '');

async function post(url, sessionId, payload) {
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      Authorization: token,
      'Content-Type': 'application/json',
      Accept: 'application/json, text/event-stream',
      ...(sessionId ? { 'Mcp-Session-Id': sessionId } : {}),
    },
    body: JSON.stringify(payload),
    signal: AbortSignal.timeout(15000),
  });
  const text = await response.text();
  let data = null;
  if (text.trim()) {
    try {
      data = JSON.parse(text);
    } catch {
      const eventData = text.split(/\r?\n/).filter((line) => line.startsWith('data:')).map((line) => line.slice(5).trim());
      if (eventData.length) data = JSON.parse(eventData.at(-1));
    }
  }
  return { response, data };
}

async function probe(type) {
  const url = `${base.origin}${prefix}/${services[type]}`;
  try {
    const init = await post(url, null, {
      jsonrpc: '2.0', id: 1, method: 'initialize',
      params: { protocolVersion: '2025-03-26', capabilities: {}, clientInfo: { name: 'stock-diagnosis-probe', version: '0.1.0' } },
    });
    const sessionId = init.response.headers.get('mcp-session-id');
    if (!init.response.ok || !sessionId) return { server: type, status: 'initialize_failed', http_status: init.response.status };
    await post(url, sessionId, { jsonrpc: '2.0', method: 'notifications/initialized' });
    const listed = await post(url, sessionId, { jsonrpc: '2.0', id: 2, method: 'tools/list', params: {} });
    const tools = listed.data?.result?.tools;
    return {
      server: type,
      status: listed.response.ok && Array.isArray(tools) ? 'ok' : 'tools_list_failed',
      http_status: listed.response.status,
      tool_count: Array.isArray(tools) ? tools.length : null,
      tool_names: Array.isArray(tools) ? tools.map((tool) => tool.name) : [],
    };
  } catch (error) {
    return { server: type, status: 'request_failed', error_type: error?.name || 'Error' };
  }
}

const results = [];
for (const type of types) results.push(await probe(type));
console.log(JSON.stringify({ checked_at: new Date().toISOString(), results }, null, 2));
if (results.some((result) => result.status !== 'ok')) process.exitCode = 1;
