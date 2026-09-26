# 架构草案

状态：Python 核心后端四类受限财务问题与 72 字段问题路由已实现；部署路径已确定为 CloudBase Git 构建云托管与云存储快照，云上部署尚未执行；其他维度诊断和 Web 框架待实现。主标的是天齐锂业（002466.SZ）。

## 技术语言约定

HTML 前端可使用必要的 CSS 与浏览器 JavaScript。服务端、数据适配、指标计算、LLM 调用、辅助脚本和测试使用 Python；具体 Web 框架尚未选定。原有 Node.js 探测脚本已迁移并复测。见 [`decisions/0004-python-default.md`](decisions/0004-python-default.md)。

## 用户主链路

一次性准备并核准所需金融数据 → 冻结固定快照 → 用户选择个股与研究问题 → 根据公司类型及问题选择诊断维度 → 读取同一快照并计算指标 → 生成带证据的诊断卡片 → 点击卡片查看财务期次、行情区间、同行对比或待验证问题。

产品数据截止日为 2026-08-31，统一观察区间为 2025-08-31 至 2026-08-31；财务同比所需基期可早于观察区间。2026 年 8 月实验样本的覆盖与限制见[下载审计](experiments/2026-08-one-month-data-audit.md)，尚未进入发布快照。

## 模块边界

1. **一次性数据准备**：独立任务从可用的扶摇/iFinD 能力取得所需字段，核准来源、时点、单位和口径后冻结快照。现有文件不覆盖；缺失和冲突仍显式记录。
   一年原始下载入口为 `scripts/download_annual_raw.py`，将 HTTP/业务响应及官方报告原文存入 Git 忽略的 `data/raw/annual-2025-08-31_2026-08-31/`。`scripts/audit_annual_coverage.py` 按 72 条候选项报告文件覆盖；它只属于准备层，不会改变现有两字段发布快照或提问路径。
2. **问题路由与配置**：`routing.py` 将问题归入固定意图，按 `config/diagnosis_fields.json` 展开七维全部候选，再用 `config/priority_profile_002466.json` 按公司业务画像选有限首屏字段。路由分别返回 `field_ids`（完整钻取范围）和 `display_plan.default_field_ids`（优先展示），标明 `implemented` 或 `planned`；用户点名的字段可提升展示次序。可读对照见[问题路由表](question-routing-map.md)。候选与展示顺序均不代表取数和证据核准。
3. **只读数据层**：仅已实现的诊断请求读取固定快照，记录快照 ID 和下载时间；不在用户提问时调用金融数据接口，也不设置刷新调度。部署时将已核准快照单独放 CloudBase 云存储，并挂载为云托管实例内的私有文件路径，由 `DIAGNOSIS_SNAPSHOT_PATH` 指向它；完整快照模式和云上挂载仍待实现。
4. **确定性计算**：财务趋势、估值、行情等数字由代码计算，记录输入字段与公式；计算证据同时保存输出字段优先级及输入证据的优先级来源，用于后续计算编排和追溯。优先级不进入数值公式；不让 LLM 生成或修改关键数字。
5. **证据组织**：将证据标为正面、负面、矛盾或未知；分别标明客观事实、分析推断及待验证事项。
6. **LLM 解读**：基于已校验的结构化证据解释含义和关系；受限翻译输入包含证据及结论的四档优先级，使有效的核心证据优先获得解读。高优先级缺口仍是未知；输出需要有证据引用，无法支持的说法不展示为事实。
7. **Web 展示与部署**：以问题和天齐锂业的价格/量价成本传导为主线，先展示有限的重要证据，再提供完整钻取、数据缺口与免责声明；重要但未核准的字段显示缺口，不由次要字段替代。Python Web 代码由 CloudBase 云托管从 Git 构建，前端只访问服务端接口，不直连快照对象。详见[决策 0010](decisions/0010-company-specific-display-priority.md)、[0012](decisions/0012-cloudbase-git-and-storage-deployment.md)和[部署清单](deployment-cloudbase.md)。

## 已实现：固定快照的四类财务问题

`src/diagnosis/` 定义 `Evidence`、`Conclusion`、`DiagnosisRun`。`scripts/download_data.py` 一次性获取扶摇同一期年报的两项标准化字段，并发布到 `data/cache/`；已有文件不覆盖。`scripts/diagnose_question.py` 只读固定快照，完成受限意图分类、口径校验、程序计算和 DeepSeek 翻译。可回答净利润正负、经营现金流正负、两者比值和方向关系；每类问题只链接所需来源和计算证据。结论对象的 `cannot_say` 包含“不称实时/最新”的限制；服务端校验文案的证据引用、事实锚点、数字和禁区，失败则回退到确定性文案。财务数据值不发送给 LLM，LLM 只接收符号方向和证据元数据。详见 [决策 0006](decisions/0006-fixed-exam-snapshot.md)与[决策 0009](decisions/0009-narrow-financial-questions.md)。

当前仅能执行四个受限财务意图，来源仍只有两项扶摇年报字段；iFinD 尚未进入固定快照产品链路。路由已覆盖候选表 72 条，可检查未实现维度的字段需求，但其他维度的计算、结论及 Web 钻取尚未实现。`report_date_ms` 暂不当作实际披露日。结构细节见 [数据契约](data-contract.md)与[决策 0008](decisions/0008-question-route-catalog.md)。

## 待确定事项

- 公司业务与行业比较口径、可用数据范围
- 具体数据接口及其授权/调用限制
- Python Web 框架、云托管构建入口、端口及实际挂载路径（部署平台已确定为 CloudBase）
- 同行口径与数据新鲜度阈值

每项确定后在 `decisions/` 记录理由，并同步更新本文件。
