# 数据与证据契约

状态：Python 核心切片已实现；其余字段映射和 Web 钻取仍待扩展。实现见 `src/diagnosis/models.py`、`profit_cash.py`、`validator.py`。

## 对象关系

一次 `DiagnosisRun` 记录 `id`、用户问题、标的、意图路由及方式、配置版本、创建时点、全部 `Evidence` 和 `Conclusion`。结论以 `evidence_id` 关联本次运行的证据；程序计算结果再以输入证据 ID 回指原始字段。接口不应只返回自然语言摘要。

固定快照模式下，`route.snapshot` 另记录快照 ID、下载时间和 `fixed` 状态。诊断运行的 `created_at` 是用户提问时刻；来源证据的 `time.fetched_at` 是快照下载时刻，两者不得混用。固定快照没有自动过期时限；界面须标明报告期和快照下载时间。

最终产品观察区间固定为 2025-08-31 至 2026-08-31，数据截止日为 2026-08-31。每条证据分别记录观察/报告期、实际披露日（核准后）和下载时间；任何日期晚于截止日的事件或披露不得进入该版结论。财务同比允许引入早于观察区间的比较基期，并在证据上注明用途。见[决策 0007](decisions/0007-observation-window.md)。

### Evidence：可复核的数据或缺口

统一字段：`id`、`metric_id`、`subject`、`kind`（`source` / `computed`）、`value`（十进制字符串或 `null`）、`unit`、`time`、`scope`、`quality`。来源证据必须含 `source.provider`、`endpoint`、`field`、`query_ref`；计算证据必须含 `calculation.formula_id`、`formula_version` 和 `input_evidence_ids`。

`time.period_end` 是报告期末，`time.fetched_at` 是获取时间；实际披露日只有经原公告核准才可写入 `published_at`。行情证据以后另用快照时间或观察区间，不能与财报期末混用。`scope` 记录年报/累计/单季、合并口径、复权方式或同行组等适用信息。

`quality.status` 取 `valid`、`missing`、`stale`、`conflict`、`error`、`not_applicable`。只有 `valid` 可携带 `value`；其他状态为 `null` 并说明原因。源间数值冲突属于数据质量问题；两个有效指标发出相反经营信号，属于结论的 `mixed`，不能混同。

## 快照契约

当前 `src/diagnosis/snapshot.py` 在 `data/cache/profit_cash_002466.json` 保存 `schema_version`、`subject`、`created_at`、两项标准化来源字段及内容摘要 `snapshot_id`。发布前拒绝接口错误或缺少字段组；写入临时文件后一次性发布，目标文件已存在时拒绝覆盖。读取时检查版本、标的、摘要与时间；下载时间不改变证据原有状态，也不会触发七天过期。提问路径只读该文件，不请求金融数据接口；完整受限 API 响应不写入仓库。

考试产品部署时从服务器私有文件读取已核准的完整快照，一次诊断固定一个 `snapshot_id`，不能在计算中混用两批数据。不安排刷新任务或服务器数据库。行情、估值、公告和 iFinD 字段仍须逐项确定观察时点、统计口径、来源定位及保存/展示范围；当前两字段快照不代表完整产品数据集。

### Conclusion：有边界的判断

统一字段：`id`、`dimension`、`claim_code`、`type`（`fact` / `inference` / `unknown`）、`assessment`（`positive` / `negative` / `mixed` / `unknown`）、`evidence_links`、`limitations`、`cannot_say`、`required_anchor`、`text`、`validation`。每条证据链接记录 `supports`、`counters` 或 `context` 角色；数据自身不预先固定为正面或负面。

`cannot_say` 每项有规则编号、禁止说法及理由。`NO_LIVE_DATA` 禁止把固定快照称为实时、最新或今天的数据。服务端按规则编号校验 LLM 文案，另外要求引用本次运行的来源证据、包含程序给定的事实锚点，且自然语言中不写数字。未通过、未知规则或 LLM 失败均返回确定性文案，并在 `validation_failures` 记录原因。词面校验不能证明任意自然语言都无越界含义；后续扩展自由解读时需继续收紧生成空间和做人工失败案例检查。

## 首条样例口径

标的为 `002466.SZ`，取扶摇利润表 `net_profit` 与现金流量表 `act_cash_flow_net` 的最近共同**年报**期。仅在报告期、年报口径、合并口径和币种一致且两值有效时比较符号；缺失、接口失败或口径不齐返回 `unknown`。比值为 `act_cash_flow_net / net_profit`，使用 Python `Decimal` 四舍五入到小数点后两位；净利润不大于零时比值为 `not_applicable`，不以普通倍数解释。比值只是辅助证据，不单独证明整体盈利质量或造假。

原始受限批量响应、密钥和授权头不写入公开仓库。运行对象保存用于钻取的字段、值、报告期与查询定位；公告等文本证据后续须增加原文链接/页码或明确待核状态。

## 待补

- 其余候选字段的实际映射、单位、快照观察时点和证据定位。
- 同行组及横比口径、公告原文定位、受限数据在部署环境中的保存与展示许可。
- Web 端按运行 ID 和证据 ID 的钻取接口。
