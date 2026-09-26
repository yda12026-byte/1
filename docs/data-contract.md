# 数据与证据契约

状态：Python 核心切片和候选字段路由已实现；其余字段的快照适配、计算和 Web 钻取仍待扩展。实现见 `src/diagnosis/models.py`、`profit_cash.py`、`routing.py`、`validator.py`。

## 候选字段与问题路由

`config/diagnosis_fields.json` 是 72 条候选字段的机器可读配置，每条含 `id`、`label`、`dimension`、`source_ref`、`source_groups`、`candidate_status`、`review_note`、`kind` 和 `product_state`；候选计算项另含 `formula_id`、`input_fields`。`candidate_status` 是候选表的实验核查结果，`product_state=implemented` 仅表示已接入当前诊断切片，二者均不能代替运行时 `Evidence.quality.status`。原始来源字段与单位、报告期和授权范围仍须逐项核准。

`route_question` 返回 `intent`、`dimensions`、`field_ids`、完整字段需求、`execution_status`、`config_version` 和观察区间。`overview` 展开全部七维；多维问题取并集。当前 `execution_status=implemented` 的四个窄意图及字段如下：

| 意图 | 所需候选字段 | 回答边界 |
| --- | --- | --- |
| `net_profit_status` | `f021` | 净利润在快照报告期的正、负或零 |
| `operating_cash_flow_status` | `f022` | 经营活动现金流净额在快照报告期的正、负或零 |
| `profit_cash_ratio` | `f021`、`f022`、`f024` | 同期同口径且净利润为正时的确定性比值 |
| `profit_cash_alignment` | `f021`、`f022`、`f024`、`f066` | 两项指标方向关系 |

其他可识别问题为 `planned`，直接投资建议或无法归类问题为 `unsupported`。同比、趋势、指定年份和两项绝对差额不能误路由到窄意图。路由本身不读取快照、不算数、不生成结论；已有诊断入口对 `planned` 返回 `not_implemented`。字段配置由 `py scripts/build_route_catalog.py` 从当前候选表生成，变更时须审阅差异及[决策 0008](decisions/0008-question-route-catalog.md)、[0009](decisions/0009-narrow-financial-questions.md)。

各问题类别的完整字段、来源、计算依赖与产品状态见[问题类别与证据展开对照表](question-routing-map.md)，可运行 `py scripts/export_question_routing_md.py --check` 检查文档是否与配置一致。

`config/priority_profile_002466.json` 独立记录天齐锂业每项字段的展示优先级和理由。路由新增 `display_plan`：`profile_version`、`budget`、`selection_rule`、`focus_field_ids`、`default_field_ids`、`drilldown_field_ids`。单维/多维/全面问题的默认上限分别为 5/8/12 项；`field_ids` 仍保留全部候选，不因弱化展示而删除。`fields` 中的 `priority_tier`、`priority_reason` 和 `default_display` 是产品编排元数据，不能代替 `candidate_status` 或运行时 `Evidence.quality.status`。用户明确问研发等低优先级字段时，该字段进入默认展示；四个可执行窄意图的输入不受展示预算裁剪。高优先级但未核准的字段应表现为证据缺口，不能被低优先级字段悄悄替代。见[决策 0010](decisions/0010-company-specific-display-priority.md)。

## 对象关系

一次 `DiagnosisRun` 记录 `id`、用户问题、标的、意图路由及方式、配置版本、创建时点、全部 `Evidence` 和 `Conclusion`。结论以 `evidence_id` 关联本次运行的证据；程序计算结果再以输入证据 ID 回指原始字段。接口不应只返回自然语言摘要。

固定快照模式下，`route.snapshot` 另记录快照 ID、下载时间和 `fixed` 状态。诊断运行的 `created_at` 是用户提问时刻；来源证据的 `time.fetched_at` 是快照下载时刻，两者不得混用。固定快照没有自动过期时限；界面须标明报告期和快照下载时间。

最终产品观察区间固定为 2025-08-31 至 2026-08-31，数据截止日为 2026-08-31。每条证据分别记录观察/报告期、实际披露日（核准后）和下载时间；任何日期晚于截止日的事件或披露不得进入该版结论。财务同比允许引入早于观察区间的比较基期，并在证据上注明用途。见[决策 0007](decisions/0007-observation-window.md)。

### Evidence：可复核的数据或缺口

统一字段：`id`、`metric_id`、`subject`、`kind`（`source` / `computed`）、`value`（十进制字符串或 `null`）、`unit`、`time`、`scope`、`quality`、`priority`。来源证据必须含 `source.provider`、`endpoint`、`field`、`query_ref`；计算证据必须含 `calculation.formula_id`、`formula_version` 和 `input_evidence_ids`。

`priority` 必须记录 `field_id`、`tier`、`reason`、`profile_version`，取自天齐锂业的版本化公司配置。`tier` 四档依次为 `driver`（核心驱动/风险）、`support`（解释与交叉验证）、`context`（背景或钻取）、`low`（弱化展示）。现有来源证据净利润/经营现金流对应 `f021`/`f022`，计算比值对应 `f024`；结论的 `priority` 也记录相同结构，方向关系对应 `f066`。即使 `quality.status` 是缺失、冲突或错误，也保留字段优先级以呈现重要缺口；优先级绝不表示证据有效。

计算证据的 `calculation.priority_inputs` 按 `input_evidence_ids` 顺序保存每个输入的证据 ID 和完整优先级快照，`priority_policy=output_field_profile_no_numeric_weight` 表示输出字段按自身配置定级，输入优先级供计算编排和解释追溯。程序校验本次输入引用与优先级快照一致；优先级不进入数值公式，不改变比值、分母限制、状态判断或事实结论。当前只有两字段比值计算已实现，其他指标的优先计算编排仍待实现。见[决策 0011](decisions/0011-evidence-priority-propagation.md)。

`time.period_end` 是报告期末，`time.fetched_at` 是获取时间；实际披露日只有经原公告核准才可写入 `published_at`。行情证据以后另用快照时间或观察区间，不能与财报期末混用。`scope` 记录年报/累计/单季、合并口径、复权方式或同行组等适用信息。

`quality.status` 取 `valid`、`missing`、`stale`、`conflict`、`error`、`not_applicable`。只有 `valid` 可携带 `value`；其他状态为 `null` 并说明原因。源间数值冲突属于数据质量问题；两个有效指标发出相反经营信号，属于结论的 `mixed`，不能混同。

## 快照契约

一年原始下载与发布快照分层：`scripts/download_annual_raw.py` 依据 2025-08-31 至 2026-08-31 的窗口保存扶摇、iFinD 和官方 PDF 的私有原始响应，每个请求记录参数、HTTP 状态、业务状态、下载时间及文件 SHA-256；已有文件不覆盖，失败项保留在审计并可重试。`scripts/audit_annual_coverage.py` 为全部 72 条候选项建立来源文件覆盖检查，`raw_files_present_review_required` 仅说明文件在位。自然日/交易日筛选、报告披露日、单位、历史修订、公告原文及受限数据展示权限仍需逐项核准。原始响应不能直接充当 `Evidence.quality.status=valid`，也不能作为产品固定快照。个股异动原因接口是当日能力，历史一年窗口无对应原始序列时保持未知。

当前 `src/diagnosis/snapshot.py` 在 `data/cache/profit_cash_002466.json` 保存 `schema_version`、`subject`、`created_at`、两项标准化来源字段及内容摘要 `snapshot_id`。发布前拒绝接口错误或缺少字段组；写入临时文件后一次性发布，目标文件已存在时拒绝覆盖。读取时检查版本、标的、摘要与时间；下载时间不改变证据原有状态，也不会触发七天过期。提问路径只读该文件，不请求金融数据接口；完整受限 API 响应不写入仓库。

考试产品部署时把已核准的完整快照以不可变对象名放入 CloudBase 云存储；云托管从 Git 构建代码，运行时通过私有存储挂载路径读取，不把数据打入镜像或前端。`DIAGNOSIS_SNAPSHOT_PATH` 指向容器内的准确文件，一次诊断固定一个 `snapshot_id`，不能在计算中混用两批数据。挂载缺失、摘要/版本/标的校验失败时返回快照不可用，不退回构造样本或原始下载。不安排刷新任务或服务器数据库。云上挂载与完整快照模式尚未实测；行情、估值、公告和 iFinD 字段仍须逐项确定观察时点、统计口径、来源定位及保存/展示范围。见[决策 0012](decisions/0012-cloudbase-git-and-storage-deployment.md)。

### Conclusion：有边界的判断

统一字段：`id`、`dimension`、`claim_code`、`type`（`fact` / `inference` / `unknown`）、`assessment`（`positive` / `negative` / `mixed` / `unknown`）、`evidence_links`、`limitations`、`cannot_say`、`required_anchor`、`text`、`validation`、`priority`。每条证据链接记录 `supports`、`counters` 或 `context` 角色；数据自身不预先固定为正面或负面。结论优先级影响解读篇幅和展示顺序，不能推翻证据质量或 `cannot_say`。

`cannot_say` 每项有规则编号、禁止说法及理由。`NO_LIVE_DATA` 禁止把固定快照称为实时、最新或今天的数据。服务端按规则编号校验 LLM 文案，另外要求引用本次运行的来源证据、包含程序给定的事实锚点，且自然语言中不写数字。未通过、未知规则或 LLM 失败均返回确定性文案，并在 `validation_failures` 记录原因。词面校验不能证明任意自然语言都无越界含义；后续扩展自由解读时需继续收紧生成空间和做人工失败案例检查。

## 首条样例口径

标的为 `002466.SZ`，取扶摇利润表 `net_profit` 与现金流量表 `act_cash_flow_net` 的最近共同**年报**期。仅在报告期、年报口径、合并口径和币种一致且两值有效时比较符号；缺失、接口失败或口径不齐返回 `unknown`。比值为 `act_cash_flow_net / net_profit`，使用 Python `Decimal` 四舍五入到小数点后两位；净利润不大于零时比值为 `not_applicable`，不以普通倍数解释。比值只是辅助证据，不单独证明整体盈利质量或造假。

原始受限批量响应、密钥和授权头不写入公开仓库。运行对象保存用于钻取的字段、值、报告期与查询定位；公告等文本证据后续须增加原文链接/页码或明确待核状态。

单项指标问题只引用自身来源证据，另一项来源缺失不阻止回答。来源字段必须有可解析且不晚于 2026-08-31 的报告期、有效数值、单位与累计/单季口径，否则结论为 `unknown`。数值为零是可证实事实，但不赋予正面或负面判断。比值问题引用两项来源和计算证据；净利润不大于零时计算证据为 `not_applicable`，结论为 `unknown`。比值数值只出现在可钻取证据中，LLM 文案不自行书写数字。

## 一年数据核准口径（决策 0013）

对 2025-08-31 至 2026-08-31 一年原始数据，用户已确定以下口径；未列出的口径仍按本文其他小节与字段表“待核”处理。见[决策 0013](decisions/0013-annual-data-approval-decisions.md)。

- **累计口径**：扶摇季度利润表/现金流量表按累计值使用并标注“累计”，不用相邻累计相减推导单季；由累计输入计算的 `f009` `f011` `f024` `f026` `f065` 注明基于累计期。单季度利润 `f020` 只取 iFinD 单季度字段。
- **负基期同比**：归母净利润同比采用绝对基期算法并注明；营业利润同比在近零基期同样加注，不作为普通同比解释。
- **交易日过滤**：估值、行业、价格序列统一以扶摇 242 个交易日历为准，非交易日（含周末与休市工作日）一律剔除；假日工作日的现货锂价也剔除。
- **EDB 锂价定位**：只作行业环境证据，不等同公司实现售价或销售均价，不作为交易信号；`f070` 经营敏感性仍未核准。
- **同行组**：正式同行组为赣锋锂业 `002460.SZ`、中矿资源 `002738.SZ`、永兴材料 `002756.SZ`；同日估值、同区间前复权行情、同报告期财务须统一口径。
- **估值口径门禁**：iFinD 估值 TTM/MRQ 口径已核实，见[决策 0014](decisions/0014-ifind-valuation-definitions.md)：分子为总股本（A+H）× A 股收盘价；`PE(TTM)` 分母为归母净利润 TTM（滚动 4 季，基准日=报表公告日期），`PE(MRQ)` 为最新一期累计归母净利润×年化系数（一季报 ×4、半年报 ×2、三季报 ×4/3、年报 ×1，均已验证），`PB(MRQ)` 分母为最新一期归母净资产（iFinD 直接提供，官方半年报可复核），`PS/PCF(TTM)` 分别用收入/经营现金流 TTM。分母为负时返回负 PE，产品须标 `not_applicable`。原记“PE/PB 市值比独立查询的‘总市值’约大 5%”已查明：“总市值”对 H 股按港股价计价，而 PE/PB 市值是全部股本按 A 股价计（复算比值 1.0000）。同行 PE 同样按“总股本 × A 股价”，口径一致。历史分位只在 iFinD 自身序列内计算，不与扶摇或其他来源市值/估值混算。
- **公告/新闻**：公告改用巨潮资讯官方清单与原文（决策 0022）；新闻仍只作待核线索。
- **特殊状态**：除复权事件 `code=3002` 记为 `source_no_matching_events`，文案为“该请求范围无匹配事件”；个股异动原因 `f048` 记为 `historical_interface_unavailable`，首屏不作当期结论但保留钻取。
- 上述口径不改变 `Evidence.quality.status`：未完成单位、报告期、披露日与来源定位核对的字段，仍以对应缺口状态呈现。

## 完整产品快照与四维计算（决策 0016）

- **文件**：`data/cache/product_snapshot_002466.json`，`schema_version=2`、`kind=product`，内容摘要 `snapshot_id`；由 `scripts/build_product_snapshot.py` 一次性生成，已存在不覆盖。`raw_manifest` 记录 142 个原始文件名与 SHA-256 前 16 位；每个数据块写明提供方、接口/工具、查询和原始文件。读取时校验版本、标的、摘要和时区；缺失或失败返回“不可用”，不退回原始文件或构造样本。
- **交易日**：以扶摇 002466 前复权日线 242 个交易日为日历；四只股票日线须与之完全对齐，否则拒绝生成。估值与 EDB 序列按日历过滤并记录剔除行数。
- **单位**：报表金额在证据中换算为亿元（元 ÷ 1e8，保留四位），`scope.unit_conversion` 标注；比率单位为 %、倍或次；锂价为元/吨。
- **计算证据**：`calculation.formula_text` 给出可读公式，`input_evidence_ids` 指向同一运行对象内的来源证据，`summary` 可附序列最小/最大/中位数/样本数。同比 = (本期 − 基期) ÷ |基期| × 100，与扶摇同名比率差超 0.1 个百分点标 `conflict`；基期为零标 `not_applicable`。分位 = 不高于截止值的交易日占比 × 100。年化波动率 = 日简单收益样本标准差 × √242。行业复合收益要求各月同为总市值加权，否则 `conflict`。
- **结论**：新增评价 `neutral`（估值位置、同行排序等事实性描述）；估值结论附加禁区 `NO_VALUATION_JUDGMENT`。`highlights` 列出首屏关键数字对应的证据 ID；锚点不含数字，回退文案必须包含锚点。
- **线索**：`clues` 只含公告标题/日期、新闻标题/日期/链接，状态 `unverified_clue`，不是 `Evidence`。

## 待补

- 其余候选字段的实际映射、单位、快照观察时点和证据定位。
- 同行组及横比口径、公告原文定位、受限数据在部署环境中的保存与展示许可。
- Web 端按运行 ID 和证据 ID 的钻取接口。

## 官方半年报摘录（决策 0018）

- 快照块 `official_h1.items`：每项含 `item`、`period_end`、`value`、`unit`（元、%、万吨、文本）、`pdf`、`page`、`table_or_section`、`note` 与 `crosscheck`（iFinD 交叉核对结论）。来源文件 `official_extract_h1.json`、`official_extract_crosscheck.json` 在 Git 忽略目录，快照记录其摘要。
- 证据来源显示为“天齐锂业官方半年报（人工摘录）”，查询定位为页码与表名；金额换算为亿元。空值为 `missing` 并保留“报告未披露”原因；交叉核对含“不一致”时为 `conflict`。文本项（在建项目进度）以原文短句作为证据值。
- 有息债务 = 短期借款 + 一年内到期的非流动负债 + 长期借款 + 应付债券 + 租赁负债；净现金 = 货币资金（扶摇）− 有息债务。任一项缺失则合计与净现金为 `missing`。

## 结论对比表（决策 0021）

- `Conclusion.table`（可选）：`{"columns": [列名…], "rows": [{"label": 指标名, "cells": [evidence_id 或 null, …]}]}`，单元格顺序与列一致。每个非空单元格必须是同一运行对象中的证据 ID，由 `validate_run` 校验，表格不引入新数值。
- 当前用于三处同行结论：估值（天齐、三家同行、同行中位数 × 市盈率 TTM / 市净率）、同行财务（四家 × 毛利率 / 加权 ROE / 资产负债率 / 营收同比）、同行股价（四家 × 观察区间涨跌幅）。页面显示保留两位小数，证据保存原值。

## 重要事件（决策 0022）

- **快照 `events` 块（可选）**：`announcements`（公告编号、披露日、标题、类别、PDF 链接；定期报告附 `periodic.kind/deadline`）、`excerpts`（类别、页码、程序摘录原文、`spot_check.status` ∈ consistent / inconsistent / pending / not_sampled）、`forecasts`（类型、归母净利润区间，单位万元，页码与原文片段）、`source`（巨潮接口、查询参数、下载时间）。
- **证据**：摘录为 `unit="文本"` 的来源证据，`source.url` 为 PDF 链接，`source.page` 为页码；抽查不一致时状态为 `conflict`、值置空。定期报告披露日为来源证据，“早于法定截止日（天）”为计算证据；业绩预告上下限按 万元 ÷ 1e4 换算为亿元，与扶摇累计利润表归母净利润计算“区间位置”。
- **分类**：`src/diagnosis/events.py` 标题规则；附件与例行文件计入“其他公告”。
- **行情图**：`/api/chat` 在涉及行情或事件维度时返回 `price_chart`：天齐与三家同行前复权收盘价按“当日 ÷ 首个交易日 × 100”指数化（Decimal，两位小数）并附原值；天齐最大回撤区间与行情维度 `max_drawdown` 证据同一算法；九类事项公告日期作标记。只做时间并列，不画趋势线、不外推。
