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
// 桌面端消息区自带滚动，只滚它，避免整页跟着跳；窄屏整页滚动时才用 scrollIntoView。
function revealMessage(node) {
  if (messages.scrollHeight > messages.clientHeight + 1) messages.scrollTop += node.getBoundingClientRect().top - messages.getBoundingClientRect().top - 12;
  else node.scrollIntoView({ block: 'start' });
}
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
  if (target) {
    target.open = true; target.scrollIntoView({ behavior: 'smooth', block: 'center' });
    target.classList.remove('flash'); void target.offsetWidth; target.classList.add('flash');
  }
}
// 计算的输入证据可能没有被任何结论直接引用、页面上还不存在；这时就地展开在计算框下方再定位。
function openInput(runId, id, byId, box) {
  if (!document.getElementById(domId(runId, id)) && byId[id]) {
    let holder = box.querySelector(':scope > .input-evidence');
    if (!holder) { holder = el('div', 'evidence-list input-evidence'); box.append(holder); }
    holder.append(renderEvidence(byId[id], byId, runId));
  }
  jumpTo(runId, id);
}
function renderEvidence(item, byId, runId) {
  const status = item.quality.status;
  const details = el('details', `evidence status-${status}`); details.id = domId(runId, item.id);
  const summary = el('summary');
  const name = addText(summary, 'span', 'evidence-name', evidenceName(item));
  if (item.kind === 'computed') addText(name, 'span', 'kind-badge', '计算');
  addText(summary, 'span', 'evidence-value', item.value === null ? '—' : item.unit === '文本' ? '原文摘录' : tableValue(item));
  addText(summary, 'span', `evidence-state state-${status}`, labels[status] || status);
  details.append(summary);

  const body = el('div', 'evidence-body'), grid = el('dl', 'evidence-grid');
  if (item.unit === '文本' && item.value !== null) addText(body, 'blockquote', 'excerpt', item.value);
  else detailPair(grid, '数值', evidenceValue(item));
  detailPair(grid, '时间', timeText(item.time));
  detailPair(grid, '口径', scopeText(item.scope));
  body.append(grid);
  if (/^https:\/\/static\.cninfo\.com\.cn\//.test(item.source?.url || '')) {
    const link = addText(body, 'a', 'source-link', `打开公告原文${item.source.page ? `（第 ${item.source.page} 页）` : ''} ↗`);
    link.href = item.source.page ? `${item.source.url}#page=${item.source.page}` : item.source.url;
    link.target = '_blank'; link.rel = 'noopener noreferrer';
  }
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
      button.type = 'button'; button.addEventListener('click', () => openInput(runId, id, byId, box));
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
function tableValue(item) {
  if (!item) return '—';
  if (item.value === null) return labels[item.quality.status] || '—';
  const number = Number(item.value);
  const text = Number.isFinite(number) && /\.\d{3,}/.test(item.value) ? number.toFixed(2) : item.value;
  return `${text}${item.unit ? ' ' + item.unit : ''}`;
}
function renderTable(table, byId, runId) {
  const wrap = el('div', 'compare-wrap');
  const t = el('table', 'compare-table');
  const head = el('tr'); addText(head, 'th', '', '指标');
  table.columns.forEach((name, i) => addText(head, 'th', i === 0 ? 'own' : '', name));
  const thead = el('thead'); thead.append(head); t.append(thead);
  const body = el('tbody');
  for (const row of table.rows) {
    const tr = el('tr'); addText(tr, 'th', '', row.label);
    row.cells.forEach((id, i) => {
      const td = el('td', i === 0 ? 'own' : '');
      const item = id ? byId[id] : null;
      if (item) { const b = addText(td, 'button', 'cell-link', tableValue(item)); b.type = 'button'; b.addEventListener('click', () => jumpTo(runId, id)); }
      else td.textContent = '—';
      tr.append(td);
    });
    body.append(tr);
  }
  t.append(body); wrap.append(t);
  addText(wrap, 'div', 'compare-note', '点击数值可定位到对应证据；表内数值保留两位小数，证据中为原值。');
  return wrap;
}
function renderConclusion(conclusion, byId, runId, snapshot) {
  const card = el('div', 'answer'), header = el('div', 'answer-header');
  addText(header, 'span', `tag ${conclusion.assessment}`, labels[conclusion.assessment] || conclusion.assessment);
  addText(header, 'span', 'tag type', labels[conclusion.type] || conclusion.type);
  addText(header, 'span', `tag tier-${conclusion.priority.tier}`, labels[conclusion.priority.tier] || conclusion.priority.tier);
  card.append(header);
  addText(card, 'p', 'answer-text', conclusion.text);
  if (conclusion.highlights?.length && !conclusion.table) {
    const chips = el('div', 'figures');
    for (const id of conclusion.highlights) {
      const item = byId[id]; if (!item) continue;
      const chip = el('button', `figure state-${item.quality.status}`); chip.type = 'button';
      addText(chip, 'span', 'figure-label', evidenceName(item));
      addText(chip, 'strong', '', tableValue(item));
      chip.addEventListener('click', () => jumpTo(runId, id));
      chips.append(chip);
    }
    card.append(chips);
  }
  if (conclusion.table) card.append(renderTable(conclusion.table, byId, runId));
  const basis = el('div', 'priority-basis');
  addText(basis, 'span', `tag tier-${conclusion.priority.tier}`, labels[conclusion.priority.tier] || conclusion.priority.tier);
  addText(basis, 'span', '', `优先级依据：${conclusion.priority.reason}`);
  card.append(basis);
  const list = el('div', 'evidence-list');
  for (const link of conclusion.evidence_links) { const item = byId[link.evidence_id]; if (item) list.append(renderEvidence(item, byId, runId)); }
  card.append(list);
  const foot = el('div', 'answer-foot');
  addText(foot, 'div', '', `限制：${withSnapshotTime(conclusion.limitations || [], snapshot.created_at).join('；')}。`);
  const failures = conclusion.validation_failures?.length ? `（模型文案未通过校验：${conclusion.validation_failures.join('、')}）` : '';
  addText(foot, 'div', '', conclusion.validation === 'passed' ? '文字说明：由受限模型生成，已校验只重述程序结论。' : `文字说明：程序生成${failures}。`);
  card.append(foot);
  return makeCollapsible(card, header, conclusion.required_anchor);
}
// 把快照下载时间并入“仅代表固定快照”那条限制；没有这条时补上，保证每张卡都标明数据时点。
function withSnapshotTime(limitations, createdAt) {
  const when = `下载于 ${beijing(createdAt).replace('（北京时间）', ' 北京时间')}`;
  let found = false;
  const items = limitations.map(raw => {
    const text = raw.replace(/[。；;]+$/, '');
    const match = text.match(/^仅代表固定快照(?:（([^）]*)）)?(.*)$/);
    if (!match) return text;
    found = true;
    return `仅代表固定快照（${match[1] ? `${match[1]}，` : ''}${when}）${match[2]}`;
  });
  if (!found) items.push(`仅代表固定快照（${when}），不代表实时状态`);
  return items;
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
  const official = clues.total.notices === 0;
  addText(card, 'p', 'answer-text', official ? '以下为新闻检索线索，未逐条核对原文，不构成事件结论。' : '以下为公告与新闻检索线索，未逐条核对原文，不构成事件结论。');
  addText(card, 'div', 'answer-note', official ? `${clues.note}。共 ${clues.total.news} 条新闻，此处按日期列出最近 ${clues.news.length} 条。`
    : `${clues.note}。共 ${clues.total.notices} 条公告、${clues.total.news} 条新闻，此处按日期列出最近各 ${clues.notices.length}/${clues.news.length} 条。`);
  for (const [title, rows] of [['公告标题（iFinD 检索，无原文链接）', clues.notices], ['新闻（第三方资讯）', clues.news]]) {
    if (!rows.length) continue;
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
  return makeCollapsible(card, header, official ? `新闻待核线索（${clues.total.news} 条）` : `公告与新闻待核线索（${clues.total.notices} 条公告、${clues.total.news} 条新闻）`);
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
    tile.addEventListener('click', () => {
      const section = document.getElementById(`sec-${run.id}`);
      if (!section) return;
      section.querySelectorAll('.answer.collapsed').forEach(card => setCollapsed(card, false));
      section.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
    grid.append(tile);
  }
  return grid;
}
// 天齐与三家同行期初 = 100 的前复权走势，阴影为天齐最大回撤区间，▲ 为官方事件日期；只做时间并列，不做归因。
function renderPriceChart(chart) {
  const svgNS = 'http://www.w3.org/2000/svg';
  const W = 720, H = 260, L = 40, R = 70, T = 14, B = 48;
  const dates = chart.dates, n = dates.length;
  const subject = chart.series.find(s => s.role === 'subject');
  const all = chart.series.flatMap(s => s.values);
  const lo = Math.min(...all), hi = Math.max(...all), pad = (hi - lo) * 0.06 || 1;
  const y0 = lo - pad, y1 = hi + pad;
  const x = i => L + (W - L - R) * i / (n - 1);
  const y = v => T + (H - T - B) * (1 - (v - y0) / (y1 - y0));
  const index = Object.fromEntries(dates.map((d, i) => [d, i]));
  const nearest = day => { if (day in index) return index[day]; const i = dates.findIndex(d => d >= day); return i < 0 ? n - 1 : i; };
  const node = (tag, attrs, parent) => { const e = document.createElementNS(svgNS, tag); for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v); if (parent) parent.append(e); return e; };

  const figure = el('figure', 'price-chart');
  addText(figure, 'figcaption', 'chart-title', `天齐锂业与三家同行股价走势（期初 = 100，前复权，${dates[0]} 至 ${dates[n - 1]}）`);
  const holder = el('div', 'chart-holder'); figure.append(holder);
  const last = s => s.values[n - 1];
  const summary = chart.series.map(s => `${s.label} ${last(s).toFixed(2)}`).join('，');
  const svg = node('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img',
    'aria-label': `期末指数：${summary}；天齐锂业最大回撤 ${chart.drawdown.pct}%（${chart.drawdown.start} 至 ${chart.drawdown.end}）；标出 ${chart.markers.length} 份事件公告` }, holder);

  // 回撤阴影在最底层
  const d0 = index[chart.drawdown.start], d1 = index[chart.drawdown.end];
  node('rect', { x: x(d0), y: T, width: Math.max(x(d1) - x(d0), 1), height: H - T - B, class: 'drawdown' }, svg);
  const ddLabel = node('text', { x: (x(d0) + x(d1)) / 2, y: T + 12, class: 'drawdown-label', 'text-anchor': 'middle' }, svg);
  ddLabel.textContent = `最大回撤 ${chart.drawdown.pct}%`;

  const step = (hi - lo) > 120 ? 50 : 25;
  for (let v = Math.ceil(y0 / step) * step; v <= y1; v += step) {
    node('line', { x1: L, x2: W - R, y1: y(v), y2: y(v), class: v === 100 ? 'grid base' : 'grid' }, svg);
    const label = node('text', { x: L - 6, y: y(v) + 4, class: 'axis', 'text-anchor': 'end' }, svg); label.textContent = v;
  }
  for (const [i, anchor] of [[0, 'start'], [n - 1, 'end']]) {
    const t = node('text', { x: x(i), y: H - B + 16, class: 'axis', 'text-anchor': anchor }, svg); t.textContent = dates[i];
  }
  // 同行先画（灰色细线），天齐最后画（强调色粗线）
  const ordered = [...chart.series.filter(s => s.role !== 'subject'), subject];
  for (const s of ordered) {
    node('path', { d: s.values.map((v, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(''),
      class: s.role === 'subject' ? 'price-line subject' : 'price-line peer' }, svg);
  }
  // 线尾直接标名称，按纵向位置错开避免重叠
  const ends = chart.series.map(s => ({ s, y: y(last(s)) })).sort((a, b) => a.y - b.y);
  for (let i = 1; i < ends.length; i++) ends[i].y = Math.max(ends[i].y, ends[i - 1].y + 13);
  for (const e of ends) {
    const label = node('text', { x: W - R + 6, y: e.y + 4, class: e.s.role === 'subject' ? 'end-label subject' : 'end-label' }, svg);
    label.textContent = `${e.s.label} ${last(e.s).toFixed(0)}`;
  }
  const byDay = {};
  for (const m of chart.markers) (byDay[m.date] ||= []).push(m);
  const markerY = H - B + 32;
  for (const [day, items] of Object.entries(byDay)) {
    const i = nearest(day), cx = x(i), cy = y(subject.values[i]);
    node('line', { x1: cx, x2: cx, y1: cy, y2: markerY - 6, class: 'event-stem' }, svg);
    node('circle', { cx, cy, r: 3.5, class: 'event-dot' }, svg);
    const link = node('a', { href: items[0].url, target: '_blank', rel: 'noopener noreferrer' }, svg);
    node('path', { d: `M${cx},${markerY - 6}l5,9h-10z`, class: 'event-mark' }, link);
    node('rect', { x: cx - 8, y: markerY - 10, width: 16, height: 18, class: 'hit' }, link);
    node('title', {}, link).textContent = `${day}\n${items.map(m => `【${m.category}】${m.title}`).join('\n')}\n点击打开第一份公告原文`;
  }
  const cross = node('line', { y1: T, y2: H - B, class: 'crosshair', visibility: 'hidden' }, svg);
  const tip = addText(holder, 'div', 'chart-tip'); tip.hidden = true;
  svg.addEventListener('mousemove', event => {
    const box = svg.getBoundingClientRect(), px = (event.clientX - box.left) * W / box.width;
    if (px < L || px > W - R) { cross.setAttribute('visibility', 'hidden'); tip.hidden = true; return; }
    const i = Math.round((px - L) / (W - L - R) * (n - 1));
    cross.setAttribute('x1', x(i)); cross.setAttribute('x2', x(i)); cross.setAttribute('visibility', 'visible');
    const lines = [dates[i], ...[subject, ...chart.series.filter(s => s !== subject)].map(s => `${s.label}　${s.values[i].toFixed(2)}（收盘 ${s.closes[i].toFixed(2)} 元）`)];
    for (const m of byDay[dates[i]] || []) lines.push(`【${m.category}】${m.title}`);
    tip.textContent = lines.join('\n'); tip.hidden = false;
    tip.style.left = `${Math.min(Math.max(x(i) / W * 100, 22), 70)}%`;
  });
  svg.addEventListener('mouseleave', () => { cross.setAttribute('visibility', 'hidden'); tip.hidden = true; });
  const legend = el('div', 'chart-legend');
  addText(legend, 'span', 'key subject', '天齐锂业');
  addText(legend, 'span', 'key peer', '同行（赣锋锂业、中矿资源、永兴材料）');
  addText(legend, 'span', 'key shade', '最大回撤区间');
  addText(legend, 'span', 'key event', '▲ 事件公告日');
  figure.append(legend);
  addText(figure, 'div', 'chart-note', `${chart.note}。▲ 共 ${chart.markers.length} 份公告（同日合并），悬停看标题，点击打开原文。来源：${chart.source}。`);
  return figure;
}
// 四类锂价期初 = 100 的走势：铜色深浅加线型区分，锂精矿最深；线尾直接标名称。
function renderLithiumChart(chart) {
  const svgNS = 'http://www.w3.org/2000/svg';
  const W = 720, H = 240, L = 40, R = 118, T = 14, B = 34;
  const dates = chart.dates, n = dates.length;
  const all = chart.series.flatMap(s => s.values.filter(v => v !== null));
  const lo = Math.min(...all), hi = Math.max(...all), pad = (hi - lo) * 0.06 || 1;
  const y0 = lo - pad, y1 = hi + pad;
  const x = i => L + (W - L - R) * i / (n - 1);
  const y = v => T + (H - T - B) * (1 - (v - y0) / (y1 - y0));
  const node = (tag, attrs, parent) => { const e = document.createElementNS(svgNS, tag); for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v); if (parent) parent.append(e); return e; };
  const styles = { spodumene: 'li-1', carbonate: 'li-2', hydroxide: 'li-3', futures: 'li-4' };
  const short = { spodumene: '锂精矿', carbonate: '碳酸锂现货', hydroxide: '氢氧化锂现货', futures: '碳酸锂期货' };

  const figure = el('figure', 'price-chart');
  addText(figure, 'figcaption', 'chart-title', `锂价走势（期初 = 100，${dates[0]} 至 ${dates[n - 1]}）`);
  const holder = el('div', 'chart-holder'); figure.append(holder);
  const lastValue = s => [...s.values].reverse().find(v => v !== null);
  const svg = node('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img',
    'aria-label': `期末指数：${chart.series.map(s => `${short[s.key]} ${lastValue(s).toFixed(2)}`).join('，')}` }, holder);
  const step = (hi - lo) > 150 ? 50 : 25;
  for (let v = Math.ceil(y0 / step) * step; v <= y1; v += step) {
    node('line', { x1: L, x2: W - R, y1: y(v), y2: y(v), class: v === 100 ? 'grid base' : 'grid' }, svg);
    node('text', { x: L - 6, y: y(v) + 4, class: 'axis', 'text-anchor': 'end' }, svg).textContent = v;
  }
  for (const [i, anchor] of [[0, 'start'], [n - 1, 'end']]) node('text', { x: x(i), y: H - B + 16, class: 'axis', 'text-anchor': anchor }, svg).textContent = dates[i];
  for (const s of [...chart.series].reverse()) {  // darkest (锂精矿) drawn last, on top
    let d = '', pen = false;
    s.values.forEach((v, i) => { if (v === null) { pen = false; return; } d += `${pen ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`; pen = true; });
    node('path', { d, class: `li-line ${styles[s.key]}` }, svg);
  }
  const ends = chart.series.map(s => ({ s, y: y(lastValue(s)) })).sort((a, b) => a.y - b.y);
  for (let i = 1; i < ends.length; i++) ends[i].y = Math.max(ends[i].y, ends[i - 1].y + 13);
  for (const e of ends) node('text', { x: W - R + 6, y: e.y + 4, class: 'end-label' }, svg).textContent = `${short[e.s.key]} ${lastValue(e.s).toFixed(0)}`;
  const cross = node('line', { y1: T, y2: H - B, class: 'crosshair', visibility: 'hidden' }, svg);
  const tip = addText(holder, 'div', 'chart-tip'); tip.hidden = true;
  svg.addEventListener('mousemove', event => {
    const box = svg.getBoundingClientRect(), px = (event.clientX - box.left) * W / box.width;
    if (px < L || px > W - R) { cross.setAttribute('visibility', 'hidden'); tip.hidden = true; return; }
    const i = Math.round((px - L) / (W - L - R) * (n - 1));
    cross.setAttribute('x1', x(i)); cross.setAttribute('x2', x(i)); cross.setAttribute('visibility', 'visible');
    tip.textContent = [dates[i], ...chart.series.map(s => s.values[i] === null ? `${short[s.key]}　无数据`
      : `${short[s.key]}　${s.values[i].toFixed(2)}（${Number(s.raw[i]).toLocaleString('zh-CN')} ${s.unit}）`)].join('\n');
    tip.hidden = false; tip.style.left = `${Math.min(Math.max(x(i) / W * 100, 22), 66)}%`;
  });
  svg.addEventListener('mouseleave', () => { cross.setAttribute('visibility', 'hidden'); tip.hidden = true; });
  const legend = el('div', 'chart-legend');
  for (const s of chart.series) { const k = addText(legend, 'span', `key li ${styles[s.key]}`, short[s.key]); k.title = s.label; }
  figure.append(legend);
  const dropped = chart.series.filter(s => s.dropped_non_trading_rows).map(s => `${short[s.key]} ${s.dropped_non_trading_rows} 行`).join('、');
  addText(figure, 'div', 'chart-note', `${chart.note}。基期均为 ${chart.series[0].base_date}；已剔除非交易日数据：${dropped || '无'}。来源：${chart.source}。`);
  return figure;
}
// 估值历史位置：PB 在上、PE(TTM) 在下，共用时间轴；虚线为三分位边界，圆点为截止日。
function renderValuationChart(chart) {
  const svgNS = 'http://www.w3.org/2000/svg';
  const W = 720, PH = 120, GAP = 26, L = 44, R = 112, T = 18;
  const dates = chart.dates, n = dates.length, H = T + chart.panels.length * (PH + GAP) + 10;
  const x = i => L + (W - L - R) * i / (n - 1);
  const node = (tag, attrs, parent) => { const e = document.createElementNS(svgNS, tag); for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v); if (parent) parent.append(e); return e; };
  const figure = el('figure', 'price-chart');
  addText(figure, 'figcaption', 'chart-title', `估值历史位置（${dates[0]} 至 ${dates[n - 1]}，逐交易日）`);
  const holder = el('div', 'chart-holder'); figure.append(holder);
  const svg = node('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img',
    'aria-label': chart.panels.map(p => `${p.label} 截止 ${p.current}，近一年分位 ${p.percentile ?? '不适用'}%（${p.band ?? '不适用'}）`).join('；') }, holder);
  const scales = chart.panels.map((p, k) => {
    const top = T + k * (PH + GAP), lo = Math.min(...p.values), hi = Math.max(...p.values), pad = (hi - lo) * 0.08 || 1;
    const y = v => top + PH * (1 - (v - (lo - pad)) / ((hi + pad) - (lo - pad)));
    node('text', { x: L, y: top - 5, class: 'panel-title' }, svg).textContent = p.label;
    for (const v of [lo, hi]) {
      node('line', { x1: L, x2: W - R, y1: y(v), y2: y(v), class: 'grid' }, svg);
      node('text', { x: L - 6, y: y(v) + 4, class: 'axis', 'text-anchor': 'end' }, svg).textContent = v.toFixed(1);
    }
    if (lo < 0 && hi > 0) node('line', { x1: L, x2: W - R, y1: y(0), y2: y(0), class: 'grid base' }, svg);
    for (const [v, name] of [[p.lower, '33.3% 分位'], [p.upper, '66.7% 分位']]) {
      if (v === null) continue;
      node('line', { x1: L, x2: W - R, y1: y(v), y2: y(v), class: 'band-line' }, svg);
      node('text', { x: W - R + 6, y: y(v) + 4, class: 'end-label' }, svg).textContent = `${name} ${v.toFixed(2)}`;
    }
    node('path', { d: p.values.map((v, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(''), class: 'price-line subject' }, svg);
    node('circle', { cx: x(n - 1), cy: y(p.current), r: 4.5, class: 'current-dot' }, svg);
    const tag = node('text', { x: x(n - 1) - 8, y: y(p.current) - 8, class: 'current-label', 'text-anchor': 'end' }, svg);
    tag.textContent = p.percentile === null ? `截止 ${p.current.toFixed(2)}（不适用）`
      : p.non_positive_days ? `截止 ${p.current.toFixed(2)}` : `截止 ${p.current.toFixed(2)} · 分位 ${p.percentile}%（${p.band}）`;
    if (p.non_positive_days) node('text', { x: L + 6, y: top + 12, class: 'switch-label' }, svg).textContent = `含 ${p.non_positive_days} 个负值交易日（亏损期倍数不适用），不画分位区间`;
    return { p, y, top };
  });
  const bottom = T + chart.panels.length * (PH + GAP) - GAP;
  for (const [i, anchor] of [[0, 'start'], [n - 1, 'end']]) node('text', { x: x(i), y: bottom + 16, class: 'axis', 'text-anchor': anchor }, svg).textContent = dates[i];
  if (chart.switch_date) {
    const i = dates.indexOf(chart.switch_date), pe = scales.find(s => s.p.key === 'pe_ttm');
    node('line', { x1: x(i), x2: x(i), y1: pe.top, y2: pe.top + PH, class: 'switch-line' }, svg);
    node('text', { x: x(i) - 4, y: pe.top + PH - 4, class: 'switch-label', 'text-anchor': 'end' }, svg).textContent = `${chart.switch_date} 半年报公告后 TTM 分母切换`;
  }
  const cross = node('line', { y1: T, y2: bottom, class: 'crosshair', visibility: 'hidden' }, svg);
  const tip = addText(holder, 'div', 'chart-tip'); tip.hidden = true;
  svg.addEventListener('mousemove', event => {
    const box = svg.getBoundingClientRect(), px = (event.clientX - box.left) * W / box.width;
    if (px < L || px > W - R) { cross.setAttribute('visibility', 'hidden'); tip.hidden = true; return; }
    const i = Math.round((px - L) / (W - L - R) * (n - 1));
    cross.setAttribute('x1', x(i)); cross.setAttribute('x2', x(i)); cross.setAttribute('visibility', 'visible');
    tip.textContent = [dates[i], ...chart.panels.map(p => `${p.label}　${p.values[i].toFixed(2)} 倍`)].join('\n');
    tip.hidden = false; tip.style.left = `${Math.min(Math.max(x(i) / W * 100, 18), 70)}%`;
  });
  svg.addEventListener('mouseleave', () => { cross.setAttribute('visibility', 'hidden'); tip.hidden = true; });
  addText(figure, 'div', 'chart-note', `${chart.note}。来源：${chart.source}。`);
  return figure;
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
  addText(card, 'div', 'progress-note', broad ? '全面诊断涉及七个维度，通常需要十几秒。' : '单维度问题通常需要几秒到十几秒。');
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
    // One price chart with event dates: under 行情 when present, otherwise under 重要事件.
    const dim = run.route.dimension, dims = runs.map(r => r.route.dimension);
    if (payload.price_chart && (dim === 'market' || (dim === 'events' && !dims.includes('market')))) section.append(renderPriceChart(payload.price_chart));
    if (payload.lithium_chart && dim === 'industry') section.append(renderLithiumChart(payload.lithium_chart));
    if (payload.valuation_chart && dim === 'valuation') section.append(renderValuationChart(payload.valuation_chart));
    for (const conclusion of run.conclusions) section.append(renderConclusion(conclusion, byId, run.id, payload.snapshot));
    if (dim === 'events' && payload.clues) { section.append(renderClues(payload.clues)); payload = { ...payload, clues: null }; }
    wrap.append(section);
  }
  if (payload.clues) { addText(wrap, 'h3', 'run-title', '重要事件'); wrap.append(renderClues(payload.clues)); }
  if (payload.gaps?.length) { addText(wrap, 'h3', 'run-title', '尚未接入的维度'); wrap.append(renderGaps(payload.gaps, '以下维度的优先字段尚未接入，仅列证据缺口，不构成诊断。')); }
  if (runs.length > 1) wrap.querySelectorAll('.answer').forEach(card => card.querySelector('.collapse-btn') && setCollapsed(card, true));
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
  const asked = addMessage(question, 'user'); input.value = ''; send.disabled = true;
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
  finally { send.disabled = false; input.focus({ preventScroll: true }); revealMessage(asked); }
}
// 输入区可收矮：隐藏示例与提示，只留一行输入框；偏好只存本浏览器。
const composerWrap = document.querySelector('.composer-wrap');
const composerToggle = document.querySelector('#composer-toggle');
function setComposerCollapsed(collapsed) {
  composerWrap.classList.toggle('collapsed', collapsed);
  composerToggle.setAttribute('aria-expanded', String(!collapsed));
  composerToggle.textContent = collapsed ? '展开 ▴' : '收起 ▾';
  try { localStorage.setItem('composerCollapsed', collapsed ? '1' : '0'); } catch (_) {}
}
composerToggle.addEventListener('click', () => setComposerCollapsed(!composerWrap.classList.contains('collapsed')));
try { if (localStorage.getItem('composerCollapsed') === '1') setComposerCollapsed(true); } catch (_) {}
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
  const ready = data.dimensions.filter(dim => dim.status === 'implemented').length;
  if (pill && product.status === 'fixed') pill.lastChild.textContent = ` ${'零一二三四五六七八九十'[ready] || ready}维诊断可运行`;
}).catch(() => { const banner = document.querySelector('#snapshot-banner'); banner.classList.add('unavailable'); banner.textContent = '服务状态暂时无法读取。'; });
