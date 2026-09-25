# 个股多维诊断与证据验证

同花顺线上笔试题目 03 的项目工作区。目标是在 **2026-09-26 23:10（北京时间）** 前交付可访问、可操作的 Web 产品、源代码及验证材料。

## 当前状态

项目骨架已建立。目标个股确定为**天齐锂业（002466.SZ）**；选择理由见[决策记录](docs/decisions/0003-target-stock.md)。DeepSeek、扶摇和 iFinD 的本地访问已通过最小调用验证；技术栈和部署地址尚待确定。此 README 会随实现补充启动方式、数据来源、AI 的角色和已知边界。

## 本地 LLM 环境变量

项目后续的 LLM 调用使用 `DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL` 和 `DEEPSEEK_MODEL`。非密钥配置示例见 [.env.example](.env.example)，模型选择见 [决策记录](docs/decisions/0002-deepseek-llm.md)。本地 `.env` 与原始 `apikey.md` 均被 Git 忽略；部署时应在平台的环境变量设置中填写密钥，不上传这两个文件。

## 金融数据访问

扶摇使用本地 `.env` 中的 `FUYAO_API_KEY` 和 `FUYAO_BASE_URL`；iFinD 使用 `IFIND_MCP_AUTH_TOKEN` 和 `IFIND_MCP_URL`。访问审计见 [数据权限验证记录](docs/data-access-audit.md)。可分别运行 `node scripts/probe-fuyao.mjs 002466.SZ` 和 `node scripts/probe-ifind.mjs` 复查权限。两个探测脚本只输出状态、数量和字段名，不输出密钥或完整数据。项目 Web 端的数据适配层尚待实现。

## 工作区导航

- [AGENTS.md](AGENTS.md)：新会话接手顺序、当前决策与实施约定
- [题目原文](docs/03_个股多维诊断与证据验证.md)：线上笔试要求
- [ARCHITECTURE.md](docs/ARCHITECTURE.md)：架构草案与数据流
- [todo/TODO.md](docs/todo/TODO.md)：任务与交付检查表
- [worklog/](docs/worklog/)：按日期记录进度和验证结果
- [decisions/](docs/decisions/)：关键决策及理由
- [docs/data-contract.md](docs/data-contract.md)：证据与数据字段约定
- [天齐锂业当前字段候选表](docs/field-candidates-002466-v2.md)：按筛选前范围恢复为 72 条，移除暂不开放外部接入的主力资金能力；[原始表及旧标记](docs/field-candidates-002466.md)仅作历史记录。
- [docs/test-plan.md](docs/test-plan.md)：测试计划与结果
- [docs/ai-use-and-validation.md](docs/ai-use-and-validation.md)：AI 使用及人工验证记录
- `src/`：产品代码；`tests/`：测试；`scripts/`：辅助脚本；`data/fixtures/`：可公开的测试样本

## 交付原则

指标由程序确定性计算，结论能追溯到原始字段或原文；明确区分事实、推断与未知。数据缺失或接口失败时显示相应状态，不生成未经验证的正常结论。产品不提供确定性涨跌预测、收益承诺或直接买卖建议。密钥、隐私信息和受限数据不得提交到公开仓库。
