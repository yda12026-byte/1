# 个股多维诊断与证据验证

同花顺线上笔试题目 03 的项目工作区。目标是在 **2026-09-26 23:10（北京时间）** 前交付可访问、可操作的 Web 产品、源代码及验证材料。

## 当前状态

目标个股为**天齐锂业（002466.SZ）**；选择理由见[决策记录](docs/decisions/0003-target-stock.md)。Python 核心后端已完成第一条“利润与经营现金流”诊断切片；可操作 Web 产品与部署地址尚未完成。DeepSeek、扶摇和 iFinD 的本地访问已验证，现有辅助探测脚本也已统一为 Python。

产品数据截止日定为 **2026-08-31**，统一观察区间为 **2025-08-31 至 2026-08-31**；财务同比允许使用更早的比较基期。2026 年 8 月的[实验下载审计](docs/experiments/2026-08-one-month-data-audit.md)已完成，但实验原始数据尚未发布为完整产品快照。

## 本地运行与测试

需要 Python 3.10+，目前不依赖第三方包。在仓库根目录执行：

```powershell
py scripts/download_data.py
py scripts/diagnose_profit_cash.py "天齐锂业的利润和经营现金流匹配吗？"
py -m unittest discover -s tests -p 'test_*.py' -v
```

首次准备时执行一次 `py scripts/download_data.py`。它把当前两项标准化年报字段写入被 Git 忽略的 `data/cache/profit_cash_002466.json`；文件一旦存在，脚本不再次下载或覆盖。诊断只读这份固定快照，**不会在用户提问时请求扶摇或 iFinD**。结果包含快照 ID、下载时间、证据和 `cannot_say` 校验状态；页面文案应标注“截至快照时间”，不能称实时或最新。DeepSeek 不可用或文案不通过校验时使用确定性文案。当前仅支持利润/经营现金流关系这一意图，快照也只含两项扶摇字段；iFinD 产品字段与其他维度尚待一次性准备。结构与边界见[数据契约](docs/data-contract.md)及[固定快照决策](docs/decisions/0006-fixed-exam-snapshot.md)。

部署时可设置 `DIAGNOSIS_SNAPSHOT_PATH` 指向服务器私有快照文件；真实数据不放入公开仓库。该变量留空时读取上述本地路径。

## 本地 LLM 环境变量

项目后续的 LLM 调用使用 `DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL` 和 `DEEPSEEK_MODEL`。非密钥配置示例见 [.env.example](.env.example)，模型选择见 [决策记录](docs/decisions/0002-deepseek-llm.md)。本地 `.env` 与原始 `apikey.md` 均被 Git 忽略；部署时应在平台的环境变量设置中填写密钥，不上传这两个文件。

## 金融数据访问

扶摇使用本地 `.env` 中的 `FUYAO_API_KEY` 和 `FUYAO_BASE_URL`；iFinD 使用 `IFIND_MCP_AUTH_TOKEN` 和 `IFIND_MCP_URL`。访问审计见 [数据权限验证记录](docs/data-access-audit.md)。可分别运行 `py scripts/probe_fuyao.py 002466.SZ` 和 `py scripts/probe_ifind.py` 复查权限；后者可附加 `stock` 等服务名筛选。两个探测脚本只输出状态、数量和字段名，不输出密钥或完整数据。产品 Web 端尚未实现。

## 工作区导航

- [AGENTS.md](AGENTS.md)：新会话接手顺序、当前决策与实施约定
- [题目原文](docs/03_个股多维诊断与证据验证.md)：线上笔试要求
- [ARCHITECTURE.md](docs/ARCHITECTURE.md)：架构草案与数据流
- [todo/TODO.md](docs/todo/TODO.md)：任务与交付检查表
- [worklog/](docs/worklog/)：按日期记录进度和验证结果
- [decisions/](docs/decisions/)：关键决策及理由
- [2026 年 8 月实验下载审计](docs/experiments/2026-08-one-month-data-audit.md)：月度接口覆盖与待核口径
- [docs/data-contract.md](docs/data-contract.md)：证据与数据字段约定
- [天齐锂业当前字段候选表](docs/field-candidates-002466-v2.md)：按筛选前范围恢复为 72 条，移除暂不开放外部接入的主力资金能力；[原始表及旧标记](docs/field-candidates-002466.md)仅作历史记录。
- [docs/test-plan.md](docs/test-plan.md)：测试计划与结果
- [docs/ai-use-and-validation.md](docs/ai-use-and-validation.md)：AI 使用及人工验证记录
- `src/`：产品代码；`tests/`：测试；`scripts/`：辅助脚本；`data/fixtures/`：可公开的测试样本

## 交付原则

指标由程序确定性计算，结论能追溯到原始字段或原文；明确区分事实、推断与未知。数据缺失或接口失败时显示相应状态，不生成未经验证的正常结论。产品不提供确定性涨跌预测、收益承诺或直接买卖建议。密钥、隐私信息和受限数据不得提交到公开仓库。
