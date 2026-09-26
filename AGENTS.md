# Agent 工作指南

适用范围：本仓库 `D:\同花顺`。本文件帮助新会话快速接手；用户最新指令和题目原文优先于这里的历史状态。发现文档与工作树不一致时，先核实实际文件、Git 状态和接口返回，再更新记录。

## 1. 任务与交付

- 本项目是同花顺线上笔试题目 03：构建一只 A 股的 AI Native 多维诊断 Web 产品。完整要求见 [`docs/03_个股多维诊断与证据验证.md`](docs/03_个股多维诊断与证据验证.md)。
- 主标的是天齐锂业 `002466.SZ`，不是前期权限探测样本 `600519.SH`。选择理由见 [`docs/decisions/0003-target-stock.md`](docs/decisions/0003-target-stock.md)。
- 提交物包括可访问且可操作的 Web URL、源码与 README、AI 使用及人工验证记录、测试说明。演示视频可选。题目**没有规定必须确定两个具体研究问题**；按公司特点和用户问题设计入口。
- 记录中的截止时间是 **2026-09-26 23:10，北京时间**。每次接手先核对当前时间和用户最新安排，不沿用旧会话的剩余时间估算。

## 2. 新会话接手顺序

1. 运行 `git status --short --branch`、`git log -1 --oneline`，确认当前工作树、分支和最近提交；保留任何已有改动。
2. 依次阅读 [`README.md`](README.md)、[题目原文](docs/03_个股多维诊断与证据验证.md)、[TODO](docs/todo/TODO.md)、[当天工作日志](docs/worklog/)、[架构草案](docs/ARCHITECTURE.md)和[数据契约](docs/data-contract.md)。
3. 以 [`docs/field-candidates-002466-v2.md`](docs/field-candidates-002466-v2.md) 为**当前字段范围**：72 条，分静态/动态，逐条标有可用性。[`docs/field-candidates-002466.md`](docs/field-candidates-002466.md) 的 21 个 `2` 是旧筛选记录，**不再表示排除**。
4. 读取相关 [`docs/decisions/`](docs/decisions/) 和 [`docs/data-access-audit.md`](docs/data-access-audit.md)；需要使用数据时再做针对性实测。避免只凭旧日志断定当前权限或数值仍有效。
5. 明确本次要完成的交付切片；动手前按第 6 节识别受影响文档，完成后同步更新，避免代码、状态表和交付说明相互矛盾。

## 3. 已确定的产品与数据边界

- 当前表恢复了筛选前的 72 条范围。原组合项“异动原因 / 主力资金”只保留**个股异动原因**。扶摇[主力资金文档](https://fuyao.aicubes.cn/docs/api-reference/capital-flow/)注明暂未开放外部接入，项目不接入该能力。
- 72 条是当前实施范围，但“已取值”“可计算”“部分可用”“待核”“当前未取得”含义不同。部分字段需要报告原文、统一口径或计算，不能因列在表中就展示为已证实结论。
- 最新实测及限制写在字段表和数据访问审计中。例如自由现金流近似值依赖 `act_cash_flow_net - pay_fixed_assets_etc_cash`；公告检索片段不等于完整公告；`report_date_ms` 不可未经核对当成实际披露日。
- 财务趋势、估值、行情、行业、事件和风险数据需注明来源、获取/披露时点、报告期、单位、统计口径、查询参数和状态。缺失、冲突、下载失败均显式呈现，不能默认为正常或零；固定快照须展示其时点，不称实时或最新。
- 指标和比值由程序确定性计算，并记录输入和公式。LLM 只解释经过校验的证据，区分 `fact`、`inference`、`unknown`，以及正面、负面、矛盾、未知证据；关键结论能钻取到原始字段或公告原文。不得生成确定性涨跌预测、收益承诺或直接买卖建议。
- 已实现的证据和结论均记录公司专属四档优先级（字段 ID、档位、理由、配置版本）；计算证据记录输入优先级来源，LLM 受限翻译读取优先级。优先级只指导计算编排与解读详略，不改变数值公式或证据质量状态；其他维度的计算编排仍待实现。见 `docs/decisions/0011-evidence-priority-propagation.md`。

## 4. 本地环境与调用

- 环境变量名称见 [`.env.example`](.env.example)。真实 `.env` 和根目录 `apikey.md` 已被 `.gitignore` 排除；不得打印、复制到文档、提交或送到客户端。当前独立下载任务调用金融数据，提问路径只读已发布快照；部署时凭据只放平台环境变量，LLM 仍由服务端调用。
- LLM 使用用户指定的 DeepSeek-V4.1-Flash；已验证的 API 模型名为 `deepseek-flash`，相关变量是 `DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL`、`DEEPSEEK_MODEL`。见 [`docs/decisions/0002-deepseek-llm.md`](docs/decisions/0002-deepseek-llm.md)。
- 扶摇使用 `FUYAO_API_KEY`、`FUYAO_BASE_URL`；iFinD 使用 `IFIND_MCP_AUTH_TOKEN`、`IFIND_MCP_URL`。可用 `py scripts/probe_fuyao.py 002466.SZ` 和 `py scripts/probe_ifind.py` 复核基础权限。探测脚本不输出密钥或完整数据。
- 当前一次性下载入口是 `py scripts/download_data.py`，只发布两项扶摇年报字段到 Git 忽略的 `data/cache/`；文件已存在时不再下载或覆盖。`py scripts/diagnose_profit_cash.py` 只读固定快照，可用 `DIAGNOSIS_SNAPSHOT_PATH` 指定服务器私有文件。快照不自动过期；iFinD 产品字段尚未纳入。完整产品数据须另行一次性准备，见决策 0006。
- 用户已确定使用 CloudBase 个人版：云托管从 Git 构建 Python Web 代码，已核准的固定快照单独存 CloudBase 云存储，运行时经存储挂载和 `DIAGNOSIS_SNAPSHOT_PATH` 读取。禁止把快照打进 Git/镜像或让浏览器直连云存储；云上部署、完整快照模式与保存/展示许可仍待验证。见 `docs/decisions/0012-cloudbase-git-and-storage-deployment.md` 和 `docs/deployment-cloudbase.md`。
- 一年原始数据准备入口是 `py scripts/download_annual_raw.py --source all`（可分别运行 `fuyao`、`ifind`、`official` 并重跑补缺），字段覆盖与日频日期审计分别为 `py scripts/audit_annual_coverage.py`、`py scripts/check_annual_dates.py`；原始响应和审计文件在 Git 忽略的 `data/raw/annual-2025-08-31_2026-08-31/`。文件在位只代表下载，不代表字段、单位、报告期或公告原文已核准，也不会自动发布为产品快照。结果与缺口见 `docs/experiments/2025-08-to-2026-08-full-download-audit.md`。
- `config/diagnosis_fields.json` 已映射当前 72 条候选字段到七维、来源、候选状态及计算依赖；可读对照见 `docs/question-routing-map.md`，用 `py scripts/export_question_routing_md.py --check` 核对。`py scripts/route_question.py "问题"` 只展示路由。`py scripts/diagnose_question.py "问题"` 可用固定两字段快照回答净利润正负、经营现金流正负、两者比值与方向关系四类窄问题；同比、指定年份、绝对差额及其他维度仍为 `planned`，不可把路由中的候选项称作已核准证据。候选表改动后可运行 `py scripts/build_route_catalog.py` 重建并审阅差异；见决策 0008、0009。
- Web 入口是 `webapp.py`（Flask；本地 `py -m pip install -r requirements.txt` 后 `py webapp.py`，端口 8080；容器用 `Dockerfile` 中的 Gunicorn）。接口 `/healthz`、`/api/bootstrap`、`/api/chat`，测试在 `tests/test_webapp.py`；状态语义、有限追问与 LLM 分工见决策 0015。可执行意图不调用 LLM 分类。
- 完整产品快照由 `py scripts/build_product_snapshot.py` 从一年原始文件一次性生成到 `data/cache/product_snapshot_002466.json`（不覆盖；`DIAGNOSIS_PRODUCT_SNAPSHOT_PATH` 可覆盖路径，默认与两字段快照同目录）。`src/diagnosis/dimensions.py` 实现估值、财务趋势、行情、行业四维；事件只列待核线索；经营质量与风险仍为缺口。结论锚点不得含数字或禁词，且必须出现在回退文案中（测试强制）。测试用合成快照 `tests/product_fixture.py`，不得读取真实 `data/cache`。见决策 0016。
- `config/priority_profile_002466.json` 为天齐锂业设置独立的字段展示优先级：默认突出锂价周期、矿/锂化工量价成本、利润现金、存货及债务/项目风险，研发费用等弱化但保留钻取。`route_question` 的 `field_ids` 是全部候选，`display_plan.default_field_ids` 才是有限首屏；优先级不等于证据有效性或投资评分。用户点名弱化字段时优先展示；重要但未核准的字段显示缺口。见决策 0010。
- 产品数据截止日是 2026-08-31，统一观察区间是 2025-08-31 至 2026-08-31；同比基期可早于窗口。2026 年 8 月的实验数据保存在 Git 忽略的 `data/raw/experiment-2026-08/`，由 `py scripts/experiment_august_data.py` 取得；它不是产品发布快照。见[决策 0007](docs/decisions/0007-observation-window.md)及[实验审计](docs/experiments/2026-08-one-month-data-audit.md)。
- 一年原始数据的核准口径已由用户确定并记入[决策 0013](docs/decisions/0013-annual-data-approval-decisions.md)：扶摇按累计值标注、负基期同比用绝对基期并注明、估值/行业/价格按实际交易日过滤、EDB 锂价作行业环境证据、正式同行组为赣锋/中矿资源/永兴材料、iFinD 估值 TTM/MRQ 先确认再展示、`f059` 显示“该请求范围无匹配事件”、`f048` 保留为历史数据缺口；公告/新闻呈现方式暂缓。原始文件仍非产品证据，完整快照尚未生成。
- iFinD 估值 TTM/MRQ 口径已核实并记入[决策 0014](docs/decisions/0014-ifind-valuation-definitions.md)：分子为总股本（A+H）× A 股收盘价；`PE(TTM)` 用归母净利润 TTM（滚动 4 季、基准日=报表公告日期），`PE(MRQ)` 用最新一期归母净利润×年化系数（一季报 ×4／半年报 ×2／三季报 ×4/3／年报 ×1，均已验证），`PB(MRQ)` 用归母净资产（iFinD 直接提供），`PS/PCF(TTM)` 用收入/经营现金流 TTM；亏损期返回负 PE，产品须标不适用。原记“约 5% 未解释”已查明：iFinD 独立查询的“总市值”对 H 股按港股价计价（2026-09-26 第三轮核实）。历史分位只在 iFinD 自身序列内计算，不与其它来源混算。
- 本机已安装 iFinD Skill：`C:\Users\qyw\.codex\skills\ifind-finance-data\SKILL.md`；另配置了 iFinD MCP 服务。换会话时先确认这些能力仍可用，再按 Skill 的服务文档、并发与查询要求调用。扶摇/iFinD 的实时权限、返回结构和数值以本次请求为准。
- 不在公开仓库保存原始受限行情、财报批量响应、授权头或用户隐私；可公开的构造测试样本放 `data/fixtures/`。

## 5. 实施与验证约定

- **技术语言偏好：除 HTML 前端（含必要的 CSS、浏览器 JavaScript）外，能用 Python 实现的后端、数据适配、指标计算、LLM 调用、自动化脚本和测试都优先用 Python。** 只有 Python 明显不适合或现有依赖要求其他语言时才例外，并在决策记录写明理由。原有 Node 探测脚本已在验证等价 Python 实现后移除；现有核心后端见 `src/diagnosis/`。见 [`docs/decisions/0004-python-default.md`](docs/decisions/0004-python-default.md)。
- 实现状态以当前工作树、提交和验证结果为准；`src/` 可能有进行中的代码。先检查实际目录，勿把草稿或未提交原型当作已交付的 Web 产品。
- 参照 [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) 的数据适配 → 校验/计算 → 证据组织 → LLM 解读 → Web 展示主链路。架构草案可调整；重大选择记入 [`docs/decisions/`](docs/decisions/)。
- 测试至少覆盖正常主链路、证据钻取、缺失/下载失败/冲突、固定快照时点、零分母或极端值、合规边界及公开部署可操作性；结果写入 [`docs/test-plan.md`](docs/test-plan.md)。AI 参与和人工纠错写入 [`docs/ai-use-and-validation.md`](docs/ai-use-and-validation.md)。
- 修改前检查 `git status`，尊重用户直接编辑的 Markdown；不对未知改动执行 `reset`、强制覆盖或清理。提交前运行相关检查、`git diff --check` 并检查待提交内容无密钥或受限数据。仓库远端是 `https://github.com/yda12026-byte/1.git`；同步时正常提交并推送，勿强推。

## 6. 文档清单与维护规则

下面的“更新时机”指该类事实发生变化时，在**同一次工作中**同步修改对应文档。先读当前内容，再追加或修订；记录已完成的事、证据和未解决事项，不把计划写成验证结果。

| 文档 | 用途 | 更新时机与写法 |
| --- | --- | --- |
| [`docs/03_个股多维诊断与证据验证.md`](docs/03_个股多维诊断与证据验证.md) | 题目原文，核对必交项与边界 | 作为只读需求来源。不要为配合设计改写题目；解释或取舍写入决策记录。 |
| [`README.md`](README.md) | 给评审者的产品入口和运行说明 | 技术栈、启动命令、环境变量名、公开 URL、产品功能、数据来源或已知限制变化时更新；只写实际可运行或明确标为待实现的状态。 |
| [`docs/todo/TODO.md`](docs/todo/TODO.md) | 当前任务与交付检查表 | 开始新工作时调整优先级；任务完成并有验证证据后才勾选。阻塞项写清原因及下一步，不用“完成”掩盖部分实现。 |
| [`docs/worklog/`](docs/worklog/) | 按北京时间记录事实和交接进度 | 每个有实质进展的工作日更新 `YYYY-MM-DD.md`：完成内容、验证命令/结果、关键问题、下一步。保留历史，不把后来决定悄悄改写成当时已确定。 |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | 当前系统结构、模块边界和数据流 | 选定技术栈、增加/改变模块、接口、部署方式或证据流时更新；区分“计划”和“已实现”，让图文与代码一致。 |
| [`docs/decisions/`](docs/decisions/) | 关键选择的理由及影响；格式见 [`docs/decisions/README.md`](docs/decisions/README.md) | 标的、数据源、口径/公式、同行组、LLM 分工、技术栈或部署方案出现实质选择时，新建递增编号的 `000N-*.md`，写日期、状态、选择、理由、替代方案与影响。决定改变时追加新记录并标注旧记录被取代，保留决策脉络。 |
| [`docs/field-candidates-002466-v2.md`](docs/field-candidates-002466-v2.md) | 当前 72 条字段范围与可用性 | 字段增删、分组、来源、公式、实际可用性或证据缺口变化时逐行更新，并核对总数与结论。[原始表](docs/field-candidates-002466.md)保留旧筛选标记作历史记录，不用它恢复旧范围。 |
| [`docs/data-contract.md`](docs/data-contract.md) | 证据结构、字段映射、单位、状态与计算口径 | 实现适配器、确定公式、时间对齐、缺失/冲突/固定快照时点规则或更改 API 映射时更新；写清输入、输出、来源和异常语义。 |
| [`docs/data-access-audit.md`](docs/data-access-audit.md) | 接口权限与真实返回的审计 | 新增/失效数据接口、授权变化或重新探测时，追加日期、标的、请求范围、HTTP/业务状态、记录数、可用字段和限制；不写密钥或受限原始数据。 |
| [`docs/ai-use-and-validation.md`](docs/ai-use-and-validation.md) | 必交的 AI 使用与人工验证记录 | AI 参与需求分析、代码、文案、数据解释或测试时，及时记录工具、用途、产出、人工核验、发现的错误及修正、证据位置；不要只在提交前笼统补写。 |
| [`docs/test-plan.md`](docs/test-plan.md) | 必交的测试说明与执行证据 | 功能或边界改变时补场景；执行后写日期、环境/命令、预期与实际结果、失败处理和证据链接。未执行的场景保持“待测”。 |
| [`.env.example`](.env.example) 与 [`AGENTS.md`](AGENTS.md) | 配置模板与接手指南 | 增删环境变量时更新**变量名与非密钥示例**；目录、运行方式、核心决定或维护流程变化时更新本指南。 |

**联动检查：** 新数据源通常涉及字段表、数据契约、访问审计、架构和工作日志；新产品能力涉及架构、README、TODO、测试和 AI 使用记录；部署完成涉及 README 的真实 URL、测试结果、TODO 与工作日志。按实际改动选择文档，避免机械修改无关文件。
