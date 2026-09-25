# 个股多维诊断与证据验证

同花顺线上笔试题目 03 的项目工作区。目标是在 **2026-09-26 23:10（北京时间）** 前交付可访问、可操作的 Web 产品、源代码及验证材料。

## 当前状态

项目骨架已建立；数据接口、个股、技术栈和部署地址尚待验证与确定。此 README 会随实现补充启动方式、环境变量、数据来源、AI 的角色和已知边界。

## 工作区导航

- [ARCHITECTURE.md](ARCHITECTURE.md)：架构草案与数据流
- [todo/TODO.md](todo/TODO.md)：任务与交付检查表
- [worklog/](worklog/)：按日期记录进度和验证结果
- [decisions/](decisions/)：关键决策及理由
- [docs/data-contract.md](docs/data-contract.md)：证据与数据字段约定
- [docs/test-plan.md](docs/test-plan.md)：测试计划与结果
- [docs/ai-use-and-validation.md](docs/ai-use-and-validation.md)：AI 使用及人工验证记录
- `src/`：产品代码；`tests/`：测试；`scripts/`：辅助脚本；`data/fixtures/`：可公开的测试样本

## 交付原则

指标由程序确定性计算，结论能追溯到原始字段或原文；明确区分事实、推断与未知。数据缺失或接口失败时显示相应状态，不生成未经验证的正常结论。产品不提供确定性涨跌预测、收益承诺或直接买卖建议。密钥、隐私信息和受限数据不得提交到公开仓库。
