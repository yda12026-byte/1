const messages = document.querySelector('#messages');
const form = document.querySelector('#chat-form');
const input = document.querySelector('#question');
const send = document.querySelector('#send');
let context = null;

const labels = {
  fact: '事实', inference: '推断', unknown: '未知',
  positive: '正面', negative: '负面', mixed: '矛盾',
  driver: '核心驱动', support: '支持证据', context: '背景', low: '低优先级',
  valid: '有效', missing: '缺失', stale: '过期', conflict: '冲突',
  error: '获取失败', not_applicable: '不适用'
};

function el(tag, className, value) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (value !== undefined && value !== null) node.textContent = String(value);
  return node;
}
function addText(parent, tag, className, value) { const node = el(tag, className, value); parent.append(node); return node; }
function scrollDown() { messages.scrollTop = messages.scrollHeight; }
function addMessage(content, kind = 'assistant') {
  const article = el('article', `message ${kind === 'user' ? 'user-message' : 'assistant-message'}`);
  if (kind === 'assistant') addText(article, 'div', 'message-label', '研究助手');
  if (typeof content === 'string') addText(article, 'div', '', content); else article.append(content);
  messages.append(article); scrollDown(); return article;
}
function detailPair(grid, name, value) {
  if (value === undefined || value === null || value === '') return;
  addText(grid, 'dt', '', name); addText(grid, 'dd', '', value);
}
function renderEvidence(item, byId) {
  const details = el('details', 'evidence'); details.id = `evidence-${item.id.replace(/[^\w-]/g, '-')}`;
  const summary = el('summary');
  addText(summary, 'span', '', item.metric_id === 'cash_to_profit_ratio' ? '经营现金流 / 净利润（计算）' : item.metric_id === 'net_profit' ? '净利润（来源）' : '经营活动现金流净额（来源）');
  addText(summary, 'span', `evidence-state ${item.quality.status === 'valid' ? '' : 'bad'}`, labels[item.quality.status] || item.quality.status);
  details.append(summary);
  const body = el('div', 'evidence-body'), grid = el('dl', 'evidence-grid');
  detailPair(grid, '原始值 / 结果', item.value === null ? '未取得可用数值' : `${item.value} ${item.unit || ''}`);
  detailPair(grid, '报告期末', item.time?.period_end || '未核准');
  detailPair(grid, '快照下载', item.time?.fetched_at || '未知');
  detailPair(grid, '统计口径', [item.scope?.period_basis, item.scope?.consolidation].filter(Boolean).join(' / '));
  detailPair(grid, '证据状态', labels[item.quality.status] || item.quality.status);
  detailPair(grid, '状态原因', item.quality.reason);
  detailPair(grid, '优先级', `${labels[item.priority.tier] || item.priority.tier} · ${item.priority.field_id} · ${item.priority.reason}`);
  detailPair(grid, '配置版本', item.priority.profile_version);
  if (item.source) {
    detailPair(grid, '来源', item.source.provider);
    detailPair(grid, '接口 / 字段', `${item.source.endpoint} · ${item.source.field}`);
    detailPair(grid, '查询定位', item.source.query_ref);
  }
  if (item.calculation) {
    detailPair(grid, '计算公式', item.calculation.formula_id === 'operating_cash_flow_div_net_profit' ? '经营活动现金流净额 ÷ 净利润；净利润须大于零，结果保留两位小数' : item.calculation.formula_id);
    detailPair(grid, '公式版本', item.calculation.formula_version);
    addText(grid, 'dt', '', '输入证据');
    const dd = el('dd');
    for (const id of item.calculation.input_evidence_ids || []) {
      const button = addText(dd, 'button', 'input-link', byId[id]?.metric_id || id);
      button.type = 'button';
      button.addEventListener('click', () => { const target = document.getElementById(`evidence-${id.replace(/[^\w-]/g, '-')}`); if (target) { target.open = true; target.scrollIntoView({ behavior: 'smooth', block: 'center' }); } });
    }
    grid.append(dd);
  }
  body.append(grid); details.append(body); return details;
}
function renderRun(payload) {
  const run = payload.run, conclusion = run.conclusions[0], byId = Object.fromEntries(run.evidence.map(item => [item.id, item]));
  const card = el('div', 'answer'), header = el('div', 'answer-header');
  addText(header, 'span', `tag ${conclusion.assessment}`, labels[conclusion.assessment] || conclusion.assessment);
  addText(header, 'span', 'tag type', labels[conclusion.type] || conclusion.type);
  addText(header, 'span', 'tag priority', labels[conclusion.priority.tier] || conclusion.priority.tier);
  card.append(header);
  addText(card, 'p', 'answer-text', conclusion.text);
  addText(card, 'div', 'answer-meta', `固定快照 · ${payload.snapshot.created_at} · 报告期见下方证据 · ${conclusion.validation === 'passed' ? '受限模型文案已校验' : '程序回退文案'}`);
  if (payload.resolved_question) addText(card, 'div', 'answer-note', `按受限追问解析为：${payload.resolved_question}`);
  if (conclusion.validation_failures?.length) addText(card, 'div', 'answer-note', `模型文案回退原因：${conclusion.validation_failures.join('、')}`);
  const list = el('div', 'evidence-list');
  for (const link of conclusion.evidence_links) { const item = byId[link.evidence_id]; if (item) list.append(renderEvidence(item, byId)); }
  card.append(list);
  if (conclusion.limitations?.length) addText(card, 'div', 'answer-note', `限制：${conclusion.limitations.join('；')}`);
  addMessage(card);
}
function renderPlanned(payload) {
  const card = el('div', 'answer');
  const header = el('div', 'answer-header'); addText(header, 'span', 'tag unknown', '待接入'); card.append(header);
  addText(card, 'p', 'answer-text', payload.message);
  addText(card, 'div', 'answer-meta', `涉及 ${payload.route.dimensions.length} 个维度、${payload.route.field_ids.length} 个候选字段。下方仅显示优先核准项，不构成有效诊断。`);
  const fields = el('div', 'planned-fields');
  for (const field of payload.missing_evidence) {
    const row = el('div', 'planned-field'); addText(row, 'strong', '', `${field.label} · ${labels[field.priority_tier] || field.priority_tier}`);
    addText(row, 'span', '', `候选状态：${field.candidate_status}；产品状态：数据或计算待接入；预期来源：${field.source_ref}`);
    fields.append(row);
  }
  card.append(fields); addMessage(card);
}
async function submitQuestion(question) {
  if (!question.trim() || send.disabled) return;
  addMessage(question, 'user'); input.value = ''; send.disabled = true;
  const pending = addMessage('正在核对路由与固定快照…');
  try {
    const response = await fetch('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question, context }) });
    const payload = await response.json(); pending.remove();
    context = payload.context || null;
    if (payload.status === 'ok') renderRun(payload);
    else if (payload.status === 'not_implemented') renderPlanned(payload);
    else addMessage(payload.message || '当前无法完成诊断。');
  } catch (_) { pending.remove(); context = null; addMessage('服务连接失败，请稍后重试。'); }
  finally { send.disabled = false; input.focus(); scrollDown(); }
}
form.addEventListener('submit', event => { event.preventDefault(); submitQuestion(input.value.trim()); });
input.addEventListener('keydown', event => { if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) { event.preventDefault(); form.requestSubmit(); } });

fetch('/api/bootstrap').then(response => response.json()).then(data => {
  const banner = document.querySelector('#snapshot-banner');
  if (data.snapshot.status === 'fixed') banner.textContent = `固定快照已连接 · 下载时间 ${data.snapshot.created_at} · ID ${data.snapshot.id} · 观察区间 ${data.window.start} 至 ${data.window.end}`;
  else { banner.classList.add('unavailable'); banner.textContent = data.snapshot.message; }
  const dimensions = document.querySelector('#dimensions');
  for (const dim of data.dimensions) { const row = el('div', 'dimension'); addText(row, 'span', '', dim.label); addText(row, 'span', `dim-status ${dim.status}`, dim.status === 'limited' ? '四类问题' : '待接入'); dimensions.append(row); }
  const examples = document.querySelector('#examples');
  for (const question of data.examples) { const button = addText(examples, 'button', 'example', question); button.type = 'button'; button.addEventListener('click', () => submitQuestion(question)); }
}).catch(() => { const banner = document.querySelector('#snapshot-banner'); banner.classList.add('unavailable'); banner.textContent = '服务状态暂时无法读取。'; });
