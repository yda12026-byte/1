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
const key = env.FUYAO_API_KEY;
const base = env.FUYAO_BASE_URL || 'https://fuyao.aicubes.cn';
const baseUrl = new URL(base);
if (baseUrl.protocol !== 'https:' || baseUrl.hostname !== 'fuyao.aicubes.cn') {
  console.error('FUYAO_BASE_URL must be the official Fuyao HTTPS endpoint');
  process.exit(2);
}
const stock = process.argv[2] || '600519.SH';
if (!key) {
  console.error('FUYAO_API_KEY is missing from the local .env');
  process.exit(2);
}
if (!/^\d{6}\.(SH|SZ|BJ)$/.test(stock)) {
  console.error('Stock must be a full A-share thscode, such as 600519.SH');
  process.exit(2);
}

const end = Date.now();
const start = end - 60 * 24 * 60 * 60 * 1000;
const probes = [
  ['snapshot', '/api/a-share/prices/snapshot', { thscodes: stock }],
  ['historical', '/api/a-share/prices/historical', { thscode: stock, interval: '1d', adjust: 'forward', start, end }],
  ['income', '/api/a-share/financials/income-statements', { thscode: stock, period: 'quarterly', limit: 4 }],
  ['balance', '/api/a-share/financials/balance-sheets', { thscode: stock, period: 'quarterly', limit: 4 }],
  ['cash_flow', '/api/a-share/financials/cash-flow-statements', { thscode: stock, period: 'quarterly', limit: 4 }],
  ['indicators', '/api/a-share/financials/indicators', { thscode: stock, report: '2026-2' }],
  ['valuation', '/api/a-share/valuations/snapshot', { thscodes: stock }],
];

async function probe([name, path, params]) {
  const url = new URL(path, base);
  for (const [param, value] of Object.entries(params)) url.searchParams.set(param, String(value));
  const started = Date.now();
  try {
    const response = await fetch(url, {
      headers: { 'X-api-key': key },
      signal: AbortSignal.timeout(20000),
    });
    const body = await response.json();
    const items = body?.data?.item;
    const abilities = body?.data?.abilities;
    const count = Array.isArray(items)
      ? items.length
      : Array.isArray(abilities)
        ? abilities.reduce((total, ability) => total + (Array.isArray(ability.indicators) ? ability.indicators.length : 0), 0)
        : null;
    const first = Array.isArray(items) ? items[0] : null;
    return {
      name,
      http_status: response.status,
      business_code: body?.code ?? null,
      status: !response.ok ? 'http_error' : body?.code !== 0 ? 'api_error' : !count ? 'empty' : 'ok',
      message: String(body?.message ?? '').replaceAll(key, '[redacted]').slice(0, 160),
      item_count: count,
      data_shape: Array.isArray(items) ? 'item' : Array.isArray(abilities) ? 'abilities' : 'other',
      data_timestamp_ms: body?.data?.timestamp ?? null,
      report_period: body?.data?.report ?? null,
      first_period_end_ms: first?.period_end_ms ?? null,
      first_item_fields: first && typeof first === 'object' ? Object.keys(first).slice(0, 40) : [],
      elapsed_ms: Date.now() - started,
    };
  } catch (error) {
    return { name, status: 'request_failed', error_type: error?.name || 'Error', elapsed_ms: Date.now() - started };
  }
}

const results = await Promise.all(probes.map(probe));
console.log(JSON.stringify({ checked_at: new Date().toISOString(), sample_stock: stock, results }, null, 2));
if (results.every((result) => result.status !== 'ok')) process.exitCode = 1;
