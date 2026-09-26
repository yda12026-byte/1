# 天齐锂业多维诊断与证据验证

同花顺线上笔试题目 03：为一只 A 股构建 AI Native 的多维诊断 Web 产品。标的为**天齐锂业（002466.SZ）**，选择理由见[决策 0003](docs/decisions/0003-target-stock.md)。题目原文见[这里](docs/03_个股多维诊断与证据验证.md)。

## 在线访问

- 地址：<https://lithium-diagnosis-319862-8-1496111595.sh.run.tcloudbase.com>（腾讯云 CloudBase 云托管）
- 首次打开会出现 CloudBase 测试域名的“风险提醒”页，等待倒计时后点击“确定访问”即可进入。
- 状态：服务已从本仓库 `main` 分支构建上线，当前两份快照仍不可用，诊断问题返回 503。CloudBase 存储挂载在实例启动前因平台生成的 COS URL 格式错误而失败；公网全量验收尚未通过，见[测试说明](docs/test-plan.md)。

## 产品能做什么

在对话框提问，或点击输入框上方的示例问题：

| 问题类型 | 示例 | 回答方式 |
| --- | --- | --- |
| 全面诊断 | 天齐锂业全面诊断一下 | 六个维度的结论和证据，外加事件线索 |
| 单维度 | 估值处于什么位置？各业务的毛利率如何？有哪些主要风险？ | 该维度的结论和证据 |
| 组合 | 锂价和同行比较情况如何？ | 相关维度 |
| 窄财务问题（“更多示例”） | 利润和经营现金流匹配吗？→ 追问“它们的比值呢” | 单条结论，支持有限追问 |
| 重要事件 | 近期有哪些公告？ | 仅列公告/新闻**待核检索线索**，不下结论 |
| 超出范围 | 明天会涨吗？要不要买？ | 说明原因与模型能力范围，推荐可回答的问题 |

每次回答的结构：

1. **总体解读**：2–4 句概括，先给最重要的判断，再点出不同维度之间的一致或分歧。
2. **分维度结论卡片**：每张卡片标明评价（正面 / 负面 / 矛盾 / 中性 / 未知）、类型（事实 / 推断 / 未知）、公司专属优先级，并附关键数字。卡片可单独收起，也可“全部收起”。
3. **证据**：展开可看数值、时间、口径和异常原因。计算项列出公式与输入证据，点击可定位到来源证据。来源接口、查询定位、快照时间等放在“技术信息”中，再展开一层才显示。

六个维度：

- **经营质量**：业务结构与毛利率、投资收益贡献、锂精矿产量。
- **财务趋势**：收入与利润同比、现金转化、净现金、存货与负债率。
- **估值**：PE/PB 等倍数、自身历史分位、同行中位数。
- **行情特征**：区间涨跌、回撤与波动、相对行业表现。
- **行业位置**：锂价环境、同行财务与股价比较。
- **风险**：短期偿债、现金对有息债务的覆盖、减值、资本开支压力。

## 设计要点（AI Native 与可验证）

- **程序算数，LLM 只解读**：所有指标由 Python 用 `Decimal` 确定性计算，并记录公式与输入。LLM（DeepSeek）不接收财务数值，只接收结论元数据，负责把已确定的结论改写成自然语言，并生成总体解读。
- **输出必须通过校验，否则回退**：
  - 模型文案必须逐字包含程序给出的结论锚点，不得出现数字；
  - 不得出现禁区用语，如买卖建议、涨跌预测、“低估/高估”、因果断言、“实时/最新”；
  - 引用的证据必须覆盖支撑证据。
  - 不通过就显示程序生成的回退文案，并标明回退原因。
- **固定快照，不冒充实时**：数据截止 2026-08-31，观察区间 2025-08-31 至 2026-08-31。所有数据一次性下载，经核准后冻结为带内容摘要的产品快照；提问时不调用金融接口。页面显示快照下载时间和快照 ID。
- **缺失、冲突、不适用都显式呈现**：
  - 不把缺失当成零；
  - 两个来源对不上时标为“冲突”（例如程序算的同比与扶摇的同名比率不一致）；
  - 分母非正时标为“不适用”。
- **公司专属优先级**：锂价周期、矿与锂化工的量价成本、利润现金、存货和债务风险优先展示；研发费用等字段弱化，但仍可钻取（[决策 0010](docs/decisions/0010-company-specific-display-priority.md)）。
- **合规边界**：不提供确定性涨跌预测、收益承诺或买卖建议。遇到这类提问时，说明涉及的类别，解释模型能做什么，并推荐几个可以直接点的问题（[决策 0019](docs/decisions/0019-out-of-scope-guidance-and-routing-fixes.md)）。

## 数据来源与已知限制

- **来源**：
  - 扶摇：前复权日线、三大报表、财务指标；
  - iFinD：估值、行业板块、EDB 锂价、同行估值、公告与新闻检索；
  - 官方半年报 PDF：分业务、有息债务、减值、在建项目等，人工摘录并附页码，与 iFinD 交叉核对。
- **正式同行组**：赣锋锂业、中矿资源、永兴材料（[决策 0013](docs/decisions/0013-annual-data-approval-decisions.md)）。
- **口径**：
  - 财务报表按半年报累计值比较；
  - 估值按 iFinD 口径原样引用，分子为总股本 × A 股价（[决策 0014](docs/decisions/0014-ifind-valuation-definitions.md)）；
  - 日频序列按 242 个交易日过滤。
- **已知限制**：
  - 锂价对公司利润的敏感性、海外资产/政策/汇率敞口尚无经核准的数据，显示为缺口；
  - 重要事件只给检索线索，未逐条核对公告原文；
  - 锂精矿销量、均价和单位成本在半年报中未披露；
  - 历史个股异动原因接口无法回溯。
- 数据公开展示已获确认，接口不设限流（[决策 0017](docs/decisions/0017-public-display-no-rate-limit.md)）。原始数据与快照不在仓库中，部署时放在私有云存储。

## 架构

```text
一次性数据准备（扶摇 / iFinD / 官方 PDF 摘录）
  → scripts/build_product_snapshot.py：按交易日过滤、口径标注、交叉核对、内容摘要 → 固定产品快照（私有存储）
提问：webapp.py（Flask / Gunicorn）
  → routing：固定意图与维度路由（问句含未覆盖年份等时只返回缺口）
  → dimensions*.py：确定性计算 → Evidence（来源 / 计算） → Conclusion（事实 / 推断 / 未知 + 禁区）
  → DeepSeek 受限改写与总体解读（并行）→ 校验 / 回退
  → 前端（HTML/CSS/JS）：总体解读 → 分维度卡片 → 证据钻取
```

详见[架构说明](docs/ARCHITECTURE.md)与[数据契约](docs/data-contract.md)。

## 本地运行与测试

需要 Python 3.10+。

```powershell
py -m pip install -r requirements.txt
py webapp.py                                     # http://127.0.0.1:8080
py -m unittest discover -s tests -p 'test_*.py'  # 60 项单元与接口测试（合成快照，不需要真实数据）
py scripts/smoke_public.py http://127.0.0.1:8080 # 21 项验收检查；不带参数时检查线上地址
```

- **运行真实诊断**：需要本地快照 `data/cache/profit_cash_002466.json` 与 `data/cache/product_snapshot_002466.json`（Git 忽略）。
  - 两字段快照由 `py scripts/download_data.py` 生成；
  - 产品快照由 `py scripts/download_annual_raw.py --source all` 下载一年原始数据后，再用 `py scripts/build_product_snapshot.py` 生成。这两步需要扶摇和 iFinD 凭据。
  - 两份快照都已存在则不覆盖。
- **环境变量**：名称见 [.env.example](.env.example)：`DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL`、`DEEPSEEK_MODEL`，以及可选的 `DIAGNOSIS_SNAPSHOT_PATH`、`DIAGNOSIS_PRODUCT_SNAPSHOT_PATH`。不配置 DeepSeek 时，页面使用程序文案。
- **部署**：仓库根目录的 `Dockerfile`（Gunicorn，端口 8080），步骤见 [CloudBase 部署清单](docs/deployment-cloudbase.md)。

## 提交材料与文档导航

- [AI 使用与人工验证记录](docs/ai-use-and-validation.md)：各阶段 AI 工具的用途、产出、人工核验及发现的错误
- [测试说明](docs/test-plan.md)：测试场景、命令与执行结果
- [决策记录](docs/decisions/)：标的、数据口径、同行组、LLM 分工、部署等 18 项关键选择及理由
- [问题路由对照表](docs/question-routing-map.md)与[72 条字段候选表](docs/field-candidates-002466-v2.md)：各类问题的字段来源、计算依赖与实现状态
- [数据访问审计](docs/data-access-audit.md)、[一年原始数据审计](docs/experiments/2025-08-to-2026-08-full-download-audit.md)
- [工作日志](docs/worklog/)、[TODO](docs/todo/TODO.md)、[接手指南 AGENTS.md](AGENTS.md)
