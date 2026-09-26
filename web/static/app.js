const messages = document.querySelector('#messages');
const form = document.querySelector('#chat-form');
const input = document.querySelector('#question');
const send = document.querySelector('#send');
let context = null;

const labels = {
  fact: '事实', inference: '推断', unknown: '未知',
  positive: '正面', negative: '负面', mixed: '矛盾', neutral: '中性',
  driver: '核心驱动', support: '支持证据', context: '背景', low: '低优先级',
  valid: '有效', missing: '缺失', stale: '过期', conflict: '冲突',
  error: '获取失败', not_applicable: '不适用'
};
const metricNames = { net_profit: '净利润', operating_cash_flow: '经营活动现金流净额', cash_to_profit_ratio: '经营现金流 / 净利润' };
const scopeNames = {
  subject: '证券', period_basis: '期间口径', consolidation: '合并口径', unit_conversion: '单位换算', adjust: '复权',
  numerator: '分子', denominator: '分母', filter: '日期过滤', weighting: '加权方式', basis: '口径'
};
const basisNames = { cumulative: '累计', annual: '年报', consolidated: '合并报表', forward: '前复权', program_calculation: '程序计算' };

function beijing(iso) {
  const date = new Date(iso);
  if (!iso || Number.isNaN(date.getTime())) return iso || '未知';
  const text = new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }).format(date);
  return `${text.replaceAll('/', '-')}（北京时间）`;
}
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
function evidenceName(item) { return item.label || metricNames[item.metric_id] || item.metric_id; }
function evidenceValue(item) { return item.value === null ? '未取得可用数值' : `${item.value} ${item.unit || ''}`.trim(); }
function domId(runId, evidenceId) { return `ev-${runId}-${evidenceId}`.replace(/[^\w-]/g, '-'); }
function timeText(time) {
  if (!time) return '';
  if (time.period_end) return `报告期末 ${time.period_end}${time.base_period_end ? `（基期 ${time.base_period_end}）` : ''}`;
  if (time.date) return `日期 ${time.date}`;
  if (time.start) return `${time.start} 至 ${time.end}`;
  return '';
}
const primaryScope = ['period_basis', 'consolidation', 'adjust', 'numerator', 'denominator', 'weighting', 'filter'];
function scopeText(scope) {
  return primaryScope.filter(key => scope?.[key]).map(key => `${scopeNames[key]}：${basisNames[scope[key]] || scope[key]}`).join('；');
}
function jumpTo(runId, id) {
  const target = document.getElementById(domId(runId, id));
  const card = target?.closest('.answer.collapsed'); if (card) setCollapsed(card, false);
  if (target) { target.open = true; target.scrollIntoView({ behavior: 'smooth', block: 'center' }); }
}
function renderEvidence(item, byId, runId) {
  const status = item.quality.status;
  const details = el('details', `evidence status-${status}`); details.id = domId(runId, item.id);
  const summary = el('summary');
  const name = addText(summary, 'span', 'evidence-name', evidenceName(item));
  if (item.kind === 'computed') addText(name, 'span', 'kind-badge', '计算');
  addText(summary, 'span', 'evidence-value', item.value === null ? '—' : `${item.value} ${item.unit || ''}`.trim());
  addText(summary, 'span', `evidence-state state-${status}`, labels[status] || status);
  details.append(summary);

  const body = el('div', 'evidence-body'), grid = el('dl', 'evidence-grid');
  detailPair(grid, '数值', evidenceValue(item));
  detailPair(grid, '时间', timeText(item.time));
  detailPair(grid, '口径', scopeText(item.scope));
  body.append(grid);
  if (status !== 'valid' && item.quality.reason) addText(body, 'div', `status-reason state-${status}`, `${labels[status] || status}：${item.quality.reason}`);
  if (item.calculation) {
    const calc = item.calculation, box = el('div', 'calc-box');
    addText(box, 'div', 'calc-label', '计算方法');
    addText(box, 'div', 'calc-formula', calc.formula_text || (calc.formula_id === 'operating_cash_flow_div_net_profit' ? '经营活动现金流净额 ÷ 净利润；净利润须大于零，结果保留两位小数' : calc.formula_id));
    if (calc.summary) addText(box, 'div', 'calc-summary', Object.entries(calc.summary).map(([k, v]) => `${{ min: '最低', max: '最高', median: '中位数', n: '样本数', unit: '单位' }[k] || k} ${v}`).join(' · '));
    addText(box, 'div', 'calc-label', '输入证据（点击定位）');
    const inputs = el('div', 'input-list');
    for (const id of calc.input_evidence_ids || []) {
      const input = byId[id];
      const button = addText(inputs, 'button', 'input-link', input ? `${evidenceName(input)}：${evidenceValue(input)}` : id);
      button.type = 'button'; button.addEventListener('click', () => jumpTo(runId, id));
    }
    box.append(inputs); body.append(box);
  }
  const tech = el('details', 'tech'); addText(tech, 'summary', '', '技术信息');
  const techGrid = el('dl', 'evidence-grid tech-grid');
  if (item.source) {
    detailPair(techGrid, '来源', item.source.provider);
    detailPair(techGrid, '接口 / 字段', `${item.source.endpoint} · ${item.source.field}`);
    detailPair(techGrid, '查询定位', item.source.query_ref);
  }
  detailPair(techGrid, '快照下载', beijing(item.time?.fetched_at));
  if (item.scope?.unit_conversion) detailPair(techGrid, '单位换算', item.scope.unit_conversion);
  if (item.calculation) detailPair(techGrid, '公式编号', `${item.calculation.formula_id} · 版本 ${item.calculation.formula_version}`);
  detailPair(techGrid, '展示优先级', `${labels[item.priority.tier] || item.priority.tier}（${item.priority.field_id}）：${item.priority.reason}`);
  detailPair(techGrid, '优先级配置', item.priority.profile_version);
  tech.append(techGrid); body.append(tech);
  details.append(body); return details;
}
function renderConclusion(conclusion, byId, runId, snapshot) {
  const card = el('div', 'answer'), header = el('div', 'answer-header');
  addText(header, 'span', `tag ${conclusion.assessment}`, labels[conclusion.assessment] || conclusion.assessment);
  addText(header, 'span', 'tag type', labels[conclusion.type] || conclusion.type);
  addText(header, 'span', `tag tier-${conclusion.priority.tier}`, labels[conclusion.priority.tier] || conclusion.priority.tier);
  card.append(header);
  addText(card, 'p', 'answer-text', conclusion.text);
  if (conclusion.highlights?.length) {
    const chips = el('div', 'figures');
    for (const id of conclusion.highlights) {
      const item = byId[id]; if (!item) continue;
      const chip = el('button', `figure state-${item.quality.status}`); chip.type = 'button';
      addText(chip, 'span', 'figure-label', evidenceName(item));
      addText(chip, 'strong', '', item.value === null ? (labels[item.quality.status] || '—') : `${item.value} ${item.unit || ''}`);
      chip.addEventListener('click', () => jumpTo(runId, id));
      chips.append(chip);
    }
    card.append(chips);
  }
  addText(card, 'div', 'answer-meta', `固定快照 · 下载于 ${beijing(snapshot.created_at)} · ${conclusion.validation === 'passed' ? '受限模型文案已校验' : '程序回退文案'}`);
  if (conclusion.validation_failures?.length) addText(card, 'div', 'answer-note', `模型文案回退原因：${conclusion.validation_failures.join('、')}`);
  const list = el('div', 'evidence-list');
  for (const link of conclusion.evidence_links) { const item = byId[link.evidence_id]; if (item) list.append(renderEvidence(item, byId, runId)); }
  card.append(list);
  if (conclusion.limitations?.length) addText(card, 'div', 'answer-note', `限制：${conclusion.limitations.join('；')}`);
  return makeCollapsible(card, header, conclusion.required_anchor);
}
function setCollapsed(card, collapsed) {
  card.classList.toggle('collapsed', collapsed);
  const button = card.querySelector('.collapse-btn');
  if (button) { button.textContent = collapsed ? '展开' : '收起'; button.setAttribute('aria-expanded', String(!collapsed)); }
}
function makeCollapsible(card, header, brief) {
  const body = el('div', 'answer-body');
  while (header.nextSibling) body.append(header.nextSibling);
  card.append(body);
  addText(header, 'span', 'answer-brief', brief);
  const button = addText(header, 'button', 'collapse-btn', '收起'); button.type = 'button'; button.setAttribute('aria-expanded', 'true');
  header.addEventListener('click', event => { if (event.target.closest('.figure, .input-link, a')) return; setCollapsed(card, !card.classList.contains('collapsed')); });
  return card;
}
function renderGaps(fields, title) {
  const card = el('div', 'answer');
  const header = el('div', 'answer-header'); addText(header, 'span', 'tag unknown', '待接入'); card.append(header);
  addText(card, 'p', 'answer-text', title);
  const box = el('div', 'planned-fields');
  for (const field of fields) {
    const row = el('div', 'planned-field'); addText(row, 'strong', '', `${field.label} · ${labels[field.priority_tier] || field.priority_tier}`);
    addText(row, 'span', '', `候选状态：${field.candidate_status}；产品状态：数据或计算待接入；预期来源：${String(field.source_ref || '未定').replaceAll('`', '')}`);
    box.append(row);
  }
  card.append(box); return makeCollapsible(card, header, title);
}
function renderClues(clues) {
  const card = el('div', 'answer');
  const header = el('div', 'answer-header'); addText(header, 'span', 'tag unknown', '待核线索'); card.append(header);
  addText(card, 'p', 'answer-text', '以下为公告与新闻检索线索，未逐条核对原文，不构成事件结论。');
  addText(card, 'div', 'answer-note', `${clues.note}。共 ${clues.total.notices} 条公告、${clues.total.news} 条新闻，此处按日期列出最近各 ${clues.notices.length}/${clues.news.length} 条。`);
  for (const [title, rows] of [['公告标题（iFinD 检索，无原文链接）', clues.notices], ['新闻（第三方资讯）', clues.news]]) {
    addText(card, 'div', 'clue-title', title);
    const list = el('ul', 'clue-list');
    for (const row of rows) {
      const li = el('li'); addText(li, 'span', 'clue-date', row.date);
      if (row.url) { const a = addText(li, 'a', '', row.title); a.href = row.url; a.target = '_blank'; a.rel = 'noopener noreferrer'; }
      else addText(li, 'span', '', row.title);
      list.append(li);
    }
    card.append(list);
  }
  return makeCollapsible(card, header, `公告与新闻待核线索（${clues.total.notices} 条公告、${clues.total.news} 条新闻）`);
}
const markSymbols = { positive: '↑', negative: '↓', mixed: '⇅', neutral: '·', unknown: '?' };
function renderOverview(runs) {
  const grid = el('div', 'dim-overview');
  for (const run of runs) {
    const tile = el('button', `dim-tile dim-${run.route.dimension}`); tile.type = 'button';
    addText(tile, 'span', 'dim-tile-name', run.route.dimension_label);
    const marks = el('span', 'dim-tile-marks');
    for (const c of run.conclusions) {
      const mark = addText(marks, 'span', `mark ${c.assessment}`, markSymbols[c.assessment] || '·');
      mark.title = `${labels[c.assessment] || c.assessment}：${c.required_anchor}`;
    }
    tile.append(marks);
    const lead = run.conclusions.find(c => c.type !== 'unknown') || run.conclusions[0];
    if (lead) addText(tile, 'span', 'dim-tile-brief', lead.required_anchor);
    tile.addEventListener('click', () => document.getElementById(`sec-${run.id}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' }));
    grid.append(tile);
  }
  return grid;
}
function renderProgress(question) {
  const card = el('div', 'progress-card');
  const head = el('div', 'progress-head');
  head.append(el('span', 'spinner'));
  addText(head, 'span', '', '正在诊断');
  const time = addText(head, 'span', 'progress-time', '0 秒');
  card.append(head);
  const steps = el('ol', 'progress-steps');
  for (const step of ['识别问题与维度', '读取固定快照', '程序计算指标与证据', '模型解读并校验']) addText(steps, 'li', '', step);
  card.append(steps);
  const broad = /全面|诊断|怎么样|整体/.test(question);
  addText(card, 'div', 'progress-note', broad ? '全面诊断涉及六个维度，通常需要十几秒。' : '单维度问题通常需要几秒到十几秒。');
  const node = addMessage(card);
  const start = Date.now();
  const timer = setInterval(() => { time.textContent = `${Math.round((Date.now() - start) / 1000)} 秒`; }, 1000);
  return { remove() { clearInterval(timer); node.remove(); } };
}
function renderRuns(payload) {
  const wrap = el('div', 'runs');
  const runs = payload.runs || [payload.run];
  if (payload.resolved_question) addText(wrap, 'div', 'answer-note', `按受限追问解析为：${payload.resolved_question}`);
  if (payload.summary) {
    const lead = el('div', 'summary-lead');
    addText(lead, 'div', 'summary-label', '总体解读');
    addText(lead, 'p', 'summary-text', payload.summary.text);
    addText(lead, 'div', 'summary-meta', `${payload.summary.validation === 'passed' ? '受限模型解读，已校验只重述程序结论' : '程序汇总各维度结论'} · 固定快照，不构成投资建议 · 下方为分维度结论与证据`);
    const tools = el('div', 'collapse-tools');
    for (const [text, collapsed] of [['全部收起', true], ['全部展开', false]]) {
      const button = addText(tools, 'button', 'collapse-all', text); button.type = 'button';
      button.addEventListener('click', () => wrap.querySelectorAll('.answer').forEach(card => card.querySelector('.collapse-btn') && setCollapsed(card, collapsed)));
    }
    lead.append(tools);
    wrap.append(lead);
  }
  if (runs.length > 1) {
    wrap.append(renderOverview(runs));
    addText(wrap, 'div', 'overview-legend', '维度概览　↑ 正面　↓ 负面　⇅ 矛盾　· 中性　? 未知　点击方块跳到对应维度');
  }
  for (const run of runs) {
    const byId = Object.fromEntries(run.evidence.map(item => [item.id, item]));
    const section = el('section', `run-section dim-${run.route.dimension || 'financial_trend'}`);
    section.id = `sec-${run.id}`;
    if (runs.length > 1 || run.route.dimension_label) addText(section, 'h3', 'run-title', run.route.dimension_label || '财务诊断');
    for (const conclusion of run.conclusions) section.append(renderConclusion(conclusion, byId, run.id, payload.snapshot));
    wrap.append(section);
  }
  if (payload.clues) { addText(wrap, 'h3', 'run-title', '重要事件'); wrap.append(renderClues(payload.clues)); }
  if (payload.gaps?.length) { addText(wrap, 'h3', 'run-title', '尚未接入的维度'); wrap.append(renderGaps(payload.gaps, '以下维度的优先字段尚未接入，仅列证据缺口，不构成诊断。')); }
  addMessage(wrap);
}
function renderPlanned(payload) {
  const wrap = el('div', 'runs');
  wrap.append(renderGaps(payload.missing_evidence, `${payload.message} 涉及 ${payload.route.dimensions.length} 个维度、${payload.route.field_ids.length} 个候选字段；下方仅显示优先核准项。`));
  if (payload.clues) wrap.append(renderClues(payload.clues));
  addMessage(wrap);
}
function renderSuggestions(payload) {
  const card = el('div', 'answer scope-card');
  const header = el('div', 'answer-header');
  addText(header, 'span', 'tag unknown', payload.reason === 'out_of_scope' ? '超出能力范围' : '未能识别');
  card.append(header);
  addText(card, 'p', 'answer-text', payload.message);
  const box = el('div', 'examples suggestion-list');
  for (const question of payload.suggestions) {
    const button = addText(box, 'button', 'example', question); button.type = 'button';
    button.addEventListener('click', () => submitQuestion(question));
  }
  card.append(box); addMessage(card);
}
async function submitQuestion(question) {
  if (!question.trim() || send.disabled) return;
  addMessage(question, 'user'); input.value = ''; send.disabled = true;
  document.querySelector('.composer-wrap')?.classList.add('compact');
  const pending = renderProgress(question);
  try {
    const response = await fetch('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question, context }) });
    const payload = await response.json(); pending.remove();
    context = payload.context || null;
    if (payload.status === 'ok') renderRuns(payload);
    else if (payload.status === 'not_implemented') renderPlanned(payload);
    else if (payload.suggestions?.length) renderSuggestions(payload);
    else addMessage(payload.message || '当前无法完成诊断。');
  } catch (_) { pending.remove(); context = null; addMessage('服务连接失败，请稍后重试。'); }
  finally { send.disabled = false; input.focus(); scrollDown(); }
}
form.addEventListener('submit', event => { event.preventDefault(); submitQuestion(input.value.trim()); });
input.addEventListener('keydown', event => { if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) { event.preventDefault(); form.requestSubmit(); } });

fetch('/api/bootstrap').then(response => response.json()).then(data => {
  const banner = document.querySelector('#snapshot-banner');
  const product = data.product_snapshot;
  if (product.status === 'fixed') banner.textContent = `完整产品快照已连接 · 下载时间 ${beijing(product.created_at)} · ID ${product.id} · ${product.trading_days} 个交易日 · 观察区间 ${data.window.start} 至 ${data.window.end}`;
  else if (data.snapshot.status === 'fixed') { banner.classList.add('unavailable'); banner.textContent = `${product.message} 两字段快照仍可回答四类财务问题（下载时间 ${beijing(data.snapshot.created_at)}）。`; }
  else { banner.classList.add('unavailable'); banner.textContent = data.snapshot.message; }
  const dimensions = document.querySelector('#dimensions');
  const statusText = { implemented: '可诊断', limited: '四类问题', clues: '待核线索', planned: '待接入' };
  for (const dim of data.dimensions) { const row = el('div', 'dimension'); addText(row, 'span', '', dim.label); addText(row, 'span', `dim-status ${dim.status}`, statusText[dim.status] || dim.status); dimensions.append(row); }
  const examples = document.querySelector('#examples');
  const addExample = (parent, question) => { const button = addText(parent, 'button', 'example', question); button.type = 'button'; button.addEventListener('click', () => submitQuestion(question)); };
  const primary = data.dimension_examples?.length ? data.dimension_examples : data.examples;
  for (const question of primary) addExample(examples, question);
  if (primary !== data.examples) {
    const more = el('details', 'more-examples'); addText(more, 'summary', '', '更多示例');
    const box = el('div', 'examples'); for (const question of data.examples) addExample(box, question);
    more.append(box); examples.append(more);
  }
  const pill = document.querySelector('.live-pill');
  if (pill && product.status === 'fixed') pill.lastChild.textContent = ' 六维诊断可运行';
}).catch(() => { const banner = document.querySelector('#snapshot-banner'); banner.classList.add('unavailable'); banner.textContent = '服务状态暂时无法读取。'; });
