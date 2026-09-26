# 架构草案

状态：Python 核心后端四类受限财务问题与 72 字段问题路由已实现；部署路径已确定为 CloudBase Git 构建云托管与云存储快照，云上部署尚未执行；Flask 对话页面与 JSON 接口已在本地实现并验收（决策 0015）；六个维度已接入完整产品快照（决策 0016、0018），事件仅列待核线索。主标的是天齐锂业（002466.SZ）。

## 技术语言约定

HTML 前端可使用必要的 CSS 与浏览器 JavaScript。服务端、数据适配、指标计算、LLM 调用、辅助脚本和测试使用 Python；Web 框架为 Flask，云托管入口为 Gunicorn（决策 0015）。原有 Node.js 探测脚本已迁移并复测。见 [`decisions/0004-python-default.md`](decisions/0004-python-default.md)。

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

## 已实现：对话页面与接口

`webapp.py` 用 Flask 提供页面（`web/templates`、`web/static`）和接口：`/healthz`、`/api/bootstrap`、`/api/chat`。提问先经服务端有限追问解析（固定短句 + 已校验的上一轮意图，不信任客户端上下文），再走 `route_question`：可执行意图读快照、计算、LLM 受限翻译并返回 `DiagnosisRun`；`planned` 只返回字段缺口；`unsupported` 拒答；快照缺失或校验失败返回 503。规则已判出可执行意图时不调用 LLM 分类。页面用 `textContent` 渲染全部数据，浏览器不接触密钥与快照文件。详见[决策 0015](decisions/0015-web-chat-and-api.md)。

## 已实现：核心四维（决策 0016）

`src/diagnosis/product_snapshot.py` 把一年原始文件标准化为 schema 2 产品快照（报表累计值、扶摇指标、四只股票前复权日线、iFinD 估值截止值与序列、同行估值、申万有色月度窗口、四类锂价、公告/新闻线索），按 242 个交易日过滤并记录原始文件摘要。`src/diagnosis/dimensions.py` 为每个维度生成来源证据、带公式和输入的计算证据及若干结论；`pipeline.diagnose_dimensions` 按路由的 `runnable_dimensions` 运行并各发一次受限 LLM 调用，逐条校验。Web 返回 `runs`（每维一个运行对象）、`gaps`（未接入维度的优先字段）和 `clues`（待核线索）。

经营质量与风险维度在 `src/diagnosis/dimensions_extra.py`，读取产品快照的 `official_h1` 块（官方半年报人工摘录，含页码与 iFinD 交叉核对状态），见决策 0018。

## 已实现：重要事件（决策 0022）

- `scripts/download_cninfo_events.py` → `cninfo_announcements.json` 与 `cninfo_pdf/`；`scripts/extract_cninfo_events.py` → `cninfo_event_extract.json`（追加资本运作类后重新生成，首版保留为 `cninfo_event_extract.v1.json`，原 21 条摘录逐字相同）；`scripts/record_event_spotcheck.py` → `cninfo_event_spotcheck.json`（均在 Git 忽略的一年原始目录）。
- `src/diagnosis/events.py`：标题分类规则与定期报告法定期限；`product_snapshot._events` 生成可选 `events` 块。
- `src/diagnosis/dimension_events.py`：事件维度结论（分类计数、按期披露、业绩预告对照、原文摘录）与 `price_chart`；快照无 `events` 块时 `webapp.py` 把事件退回缺口与新闻线索。
- 前端：摘录以引用块显示并链接 PDF 页码；行情分区（或只问事件时的事件分区）显示 SVG 收盘价折线与事件标记。

## 待确定事项

早期列出的业务与行业比较口径、数据接口与授权、同行口径已分别在决策 0003、0013、0014、0016–0018 确定；数据新鲜度不适用（固定快照，决策 0006）。剩余：

- CloudBase 存储挂载实测（服务已从 Git 构建上线，端口 8080；首次挂载因平台生成的 COS 地址格式报错，正在改用“云开发云存储”选项，见部署清单）
- 锂价经营敏感性（f070）、海外敞口（f071）仍无核准数据；股权质押（f060）、解禁（f061）尚未作为正式证据

每项确定后在 `decisions/` 记录理由，并同步更新本文件。
