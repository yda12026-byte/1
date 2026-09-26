# 个股多维诊断与证据验证

同花顺线上笔试题目 03 的项目工作区。目标是在 **2026-09-26 23:10（北京时间）** 前交付可访问、可操作的 Web 产品、源代码及验证材料。

## 当前状态

目标个股为**天齐锂业（002466.SZ）**；选择理由见[决策记录](docs/decisions/0003-target-stock.md)。本地可操作的对话页面（Flask）现可诊断**估值、财务趋势、行情特征、行业位置**四维：每条结论可钻取到公式、输入证据与原始文件定位；重要事件只列公告/新闻待核检索线索；经营质量与风险显示证据缺口。四类窄财务问题与有限追问继续可用。见[决策 0016](docs/decisions/0016-core-four-dimensions-snapshot.md)。公开部署地址尚未完成。部署路径已确定为 CloudBase 云托管从 Git 构建代码、云存储保存固定快照，尚未进行云上实测。DeepSeek、扶摇和 iFinD 的本地访问已验证，现有辅助探测脚本也已统一为 Python。

产品数据截止日定为 **2026-08-31**，统一观察区间为 **2025-08-31 至 2026-08-31**；财务同比允许使用更早的比较基期。2026 年 8 月的[实验下载审计](docs/experiments/2026-08-one-month-data-audit.md)已完成，但实验原始数据尚未发布为完整产品快照。

一年窗口的原始数据已取得：扶摇 19 组、iFinD 128 组及五份官方报告；其中除复权事件组明确返回无匹配记录，历史个股异动原因无法回溯。可用 `py scripts/download_annual_raw.py --source all` 复查并补缺，`--source fuyao`、`ifind`、`official` 可单独运行；已有成功文件不覆盖。原始文件保存在 Git 忽略的 `data/raw/annual-2025-08-31_2026-08-31/`，`py scripts/audit_annual_coverage.py` 只检查 72 条候选项的文件覆盖，`py scripts/check_annual_dates.py` 审计部分日频来源日期。下载及缺口见[一年原始数据审计](docs/experiments/2025-08-to-2026-08-full-download-audit.md)。这些原始文件未经逐字段核准，**不供当前诊断入口读取**；完整固定产品快照仍待制作。

## 本地运行与测试

需要 Python 3.10+。Web 页面依赖见 `requirements.txt`（Flask、Gunicorn）。在仓库根目录执行：

```powershell
py -m pip install -r requirements.txt
py webapp.py   # 打开 http://127.0.0.1:8080
py scripts/download_data.py
py scripts/build_product_snapshot.py   # 一次性：由一年原始文件生成完整产品快照
py scripts/route_question.py "天齐锂业的估值和行业位置如何？"
py scripts/diagnose_question.py "天齐锂业的净利润是正还是负？"
py scripts/diagnose_question.py "天齐锂业的经营活动现金流净额为正吗？"
py scripts/diagnose_question.py "天齐锂业的经营现金流与净利润的比值是多少？"
py scripts/diagnose_question.py "天齐锂业的利润和经营现金流匹配吗？"
py -m unittest discover -s tests -p 'test_*.py' -v
```

Web 页面（`webapp.py`）提供 `GET /healthz`、`GET /api/bootstrap` 和 `POST /api/chat`；状态语义、有限追问规则与 LLM 分工见[决策 0015](docs/decisions/0015-web-chat-and-api.md)。页面显示快照下载时间（北京时间）和快照 ID，每条证据可展开来源、报告期、口径、优先级及计算输入；快照缺失或校验失败时返回不可用状态。容器入口为 `Dockerfile`（Gunicorn），镜像不含 `data/`。

首次准备时执行一次 `py scripts/download_data.py`。它把当前两项标准化年报字段写入被 Git 忽略的 `data/cache/profit_cash_002466.json`；文件一旦存在，脚本不再次下载或覆盖。`route_question.py` 只展示问题对应的维度、候选字段、优先展示字段、来源和待核准状态，不读取金融数据。天齐锂业的默认展示优先关注锂价、分业务量价成本、利润现金、存货及债务风险；研发费用等仅在专门提问或钻取时突出。全部 72 条候选仍可检查。诊断只读固定快照，**不会在用户提问时请求扶摇或 iFinD**。结果包含快照 ID、下载时间、证据和 `cannot_say` 校验状态；页面文案应标注“截至快照时间”，不能称实时或最新。DeepSeek 不可用或文案不通过校验时使用确定性文案。现可执行净利润正负、经营现金流正负、两者比值和方向关系四类问题。同比、指定年份、绝对差额、估值、行业及全面财务问题仍只显示规划路由，不生成诊断；iFinD 产品字段尚待一次性准备。旧命令 `py scripts/diagnose_profit_cash.py` 仍可用。结构与边界见[数据契约](docs/data-contract.md)及[决策 0010](docs/decisions/0010-company-specific-display-priority.md)。

完整产品快照 `data/cache/product_snapshot_002466.json` 由 `py scripts/build_product_snapshot.py` 从 Git 忽略的一年原始文件一次性生成，已存在不覆盖；其路径默认与两字段快照同目录，也可用 `DIAGNOSIS_PRODUCT_SNAPSHOT_PATH` 指定。缺失或校验失败时四维问题返回“不可用”，窄问题不受影响。

部署时拟将已核准发布快照存入 CloudBase 云存储，挂载到云托管实例，再由 `DIAGNOSIS_SNAPSHOT_PATH` 指向容器内的准确文件路径；真实数据不放入公开仓库或构建镜像。该变量留空时读取上述本地路径。完整快照模式、挂载和公开 URL 尚未实现，详见[CloudBase 部署清单](docs/deployment-cloudbase.md)和[决策 0012](docs/decisions/0012-cloudbase-git-and-storage-deployment.md)。

## 本地 LLM 环境变量

项目后续的 LLM 调用使用 `DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL` 和 `DEEPSEEK_MODEL`。非密钥配置示例见 [.env.example](.env.example)，模型选择见 [决策记录](docs/decisions/0002-deepseek-llm.md)。本地 `.env` 与原始 `apikey.md` 均被 Git 忽略；部署时应在平台的环境变量设置中填写密钥，不上传这两个文件。

## 金融数据访问

扶摇使用本地 `.env` 中的 `FUYAO_API_KEY` 和 `FUYAO_BASE_URL`；iFinD 使用 `IFIND_MCP_AUTH_TOKEN` 和 `IFIND_MCP_URL`。访问审计见 [数据权限验证记录](docs/data-access-audit.md)。可分别运行 `py scripts/probe_fuyao.py 002466.SZ` 和 `py scripts/probe_ifind.py` 复查权限；后者可附加 `stock` 等服务名筛选。两个探测脚本只输出状态、数量和字段名，不输出密钥或完整数据。Web 端提问时不调用这两个数据源。

## 工作区导航

- [AGENTS.md](AGENTS.md)：新会话接手顺序、当前决策与实施约定
- [题目原文](docs/03_个股多维诊断与证据验证.md)：线上笔试要求
- [ARCHITECTURE.md](docs/ARCHITECTURE.md)：架构草案与数据流
- [CloudBase 部署清单](docs/deployment-cloudbase.md)：Git 构建、云存储挂载、权限与验收步骤
- [todo/TODO.md](docs/todo/TODO.md)：任务与交付检查表
- [worklog/](docs/worklog/)：按日期记录进度和验证结果
- [decisions/](docs/decisions/)：关键决策及理由
- [2026 年 8 月实验下载审计](docs/experiments/2026-08-one-month-data-audit.md)：月度接口覆盖与待核口径
- [docs/data-contract.md](docs/data-contract.md)：证据与数据字段约定
- [问题类别与证据展开对照表](docs/question-routing-map.md)：每类问题的完整候选、默认优先字段、来源、计算依赖和当前执行状态
- [天齐锂业当前字段候选表](docs/field-candidates-002466-v2.md)：按筛选前范围恢复为 72 条，移除暂不开放外部接入的主力资金能力；[原始表及旧标记](docs/field-candidates-002466.md)仅作历史记录。
- [docs/test-plan.md](docs/test-plan.md)：测试计划与结果
- [docs/ai-use-and-validation.md](docs/ai-use-and-validation.md)：AI 使用及人工验证记录
- `src/`：产品代码；`tests/`：测试；`scripts/`：辅助脚本；`data/fixtures/`：可公开的测试样本

## 交付原则

指标由程序确定性计算，结论能追溯到原始字段或原文；明确区分事实、推断与未知。数据缺失或接口失败时显示相应状态，不生成未经验证的正常结论。产品不提供确定性涨跌预测、收益承诺或直接买卖建议。密钥、隐私信息和受限数据不得提交到公开仓库。

当前四类可执行财务问题的证据和结论均记录天齐锂业公司专属四档优先级及配置版本；计算证据保留输入优先级来源，LLM 受限翻译按优先级安排解读重点。优先级不改变公式或证据有效性。其他维度的计算与 Web 展示仍待实现，详见[决策 0011](docs/decisions/0011-evidence-priority-propagation.md)。
