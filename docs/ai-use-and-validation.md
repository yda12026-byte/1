# AI 使用与验证记录

状态：持续记录；提交前补充具体工具、日期、示例与修正证据。

| 日期 | AI 工具及用途 | AI 产出 | 人工核验与修正 | 证据位置 |
| --- | --- | --- | --- | --- |
| 2026-09-25 | Codex：阅读题目、规划交付和建立项目骨架 | 初始计划与文档骨架 | 核对题目要求和截止时间；数据能力尚未验证 | `docs/worklog/2026-09-25.md` |
| 2026-09-25 | DeepSeek-V4.1-Flash：最小文本调用验证 | API 返回非空文本 | 先核对官方模型名，再确认模型列表和实际调用均成功；未用于生成金融结论 | `docs/decisions/0002-deepseek-llm.md` |
| 2026-09-26 | Codex：记录用户选定标的，调用扶摇和 iFinD 核对数据覆盖与公司资料 | 天齐锂业标的决策与数据审计更新 | 以用户明确指定的 `002466` 为准；核对扶摇各接口状态、iFinD 返回的代码/名称/主营业务/行业，未据此自动生成投资判断 | `docs/decisions/0003-target-stock.md`、`docs/data-access-audit.md` |
| 2026-09-26 | Codex：编写跨会话接手指南 | `AGENTS.md` 的接手顺序与项目边界 | 用户指出初稿缺少各文档的维护方法；补入逐文档用途、更新触发条件和决策替代规则，并检查链接 | `AGENTS.md`、`docs/decisions/README.md` |
| 2026-09-26 | Codex：记录实现语言约束 | Python 优先规则及决策 0004 | 以用户明确补充的偏好为准；核对现有工作树，未覆盖进行中的 `.mjs` 原型，也未把 Web 框架写成已选定 | `AGENTS.md`、`docs/decisions/0004-python-default.md` |
| 2026-09-26 | Codex：按用户要求设计 Python 核心后端并迁移辅助脚本 | 统一证据/结论对象、`cannot_say` 校验、利润与现金流切片、两个 Python 探测脚本 | 发现 Python 默认代理连接失败，改为仅对已核准官方域名直连；发现 UTC 转换把报告期末显示为前一日，改为上海时区并加回归测试。构造测试 8 项通过，真实诊断和 7 类扶摇/10 个 iFinD 服务探测通过；保留 Web 与其余维度为待实现 | `src/diagnosis/`、`tests/test_diagnosis.py`、`docs/test-plan.md` |
| 2026-09-26 | Codex：按用户建议改为预下载数据 | 快照下载/发布/读取、过期处理与版本追溯 | 核对提问脚本不再调用金融数据 API；下载失败保留旧版，过期证据转未知。发现系统临时目录在沙箱内不可写，改用 Git 忽略的工作区缓存目录运行测试；10 项测试和真实下载/诊断通过，未把受限值写入仓库 | `src/diagnosis/snapshot.py`、`scripts/download_data.py`、`tests/test_diagnosis.py`、`docs/decisions/0005-preloaded-data.md` |
| 2026-09-26 | Codex：按用户最终决定收敛为考试固定快照 | 决策 0006、一次性发布与重复下载跳过、`NO_LIVE_DATA` 文案校验、文档口径修订 | 删除旧七天失效逻辑与数据库计划；10 项测试通过。清空金融数据密钥后复核重复下载返回原 ID、诊断只读同一快照且文案校验通过。明确现有快照仅含两项扶摇字段，完整产品数据与 Web 仍待完成 | `docs/decisions/0006-fixed-exam-snapshot.md`、`src/diagnosis/snapshot.py`、`src/diagnosis/validator.py`、`docs/test-plan.md` |
| 2026-09-26 | Codex：根据用户确定的区间做月度数据实验下载 | Python 实验脚本、扶摇/iFinD 月度样本、深交所半年报原文、覆盖审计 | 检查 HTTP/业务状态、记录数、日期与原始字段；识别 iFinD 自然日估值行、事件窗口外日期和公告无原文 URL。原始数据仅保存在 Git 忽略目录，文档不包含数值；仅把核准后的字段留待最终快照 | `scripts/experiment_august_data.py`、`docs/experiments/2026-08-one-month-data-audit.md`、`docs/decisions/0007-observation-window.md` |
| 2026-09-26 | Codex：实现问题路由与候选字段配置 | 72 项机器可读清单、七维/多维问题展开、专项执行边界、配置生成脚本与测试 | 逐行比对候选表的名称、来源、状态和维度；把接口“已取值”与产品“已实现”分开。测试发现行业与估值共 15 项并修正测试预期；未把候选项当成运行时有效证据 | `config/diagnosis_fields.json`、`src/diagnosis/routing.py`、`tests/test_routing.py`、`docs/decisions/0008-question-route-catalog.md` |
| 2026-09-26 | Codex：扩大固定快照可回答的问题 | 三个窄财务意图、各自结论与证据链接、通用命令入口 | 用构造值测试单项独立性、比值零/负分母、缺失和超截止报告期；本地固定快照只核对新问法的意图、结论类型和证据数量，不复制受限数值。拒绝把同比、指定年份和绝对差额问法当作已实现 | `src/diagnosis/profit_cash.py`、`src/diagnosis/routing.py`、`tests/test_diagnosis.py`、`tests/test_routing.py`、`docs/decisions/0009-narrow-financial-questions.md` |
| 2026-09-26 | Codex：将问题与字段配置整理为可读文档 | 按问题类别和七个维度组织的来源、72 字段和计算依赖对照表 | 从机器配置生成后核对七维计数之和为 72、四个可执行字段集合与路由一致；显式区分候选核查状态和产品执行状态，并补明历史分位、同行中位数等尚未核准的派生计算 | `docs/question-routing-map.md`、`scripts/export_question_routing_md.py` |
| 2026-09-26 | Codex：按用户反馈修正字段等量展示 | 天齐锂业公司专属四档优先级、有限首屏和可钻取完整字段；问题对照表增加逐项理由 | 对照公司 2025 年报及 2026 年半年报的业务结构、价格/成本传导描述；保留矿与锂化工双业务画像，避免称纯矿企；研发费用默认弱化但专问时提升。以测试确认 72 项全覆盖、价格与量价成本优先、缺口不被当作有效证据 | `config/priority_profile_002466.json`、`src/diagnosis/priority.py`、`docs/decisions/0010-company-specific-display-priority.md` |
| 2026-09-26 | Codex：编写一年原始数据下载与逐字段覆盖审计 | 可重跑的扶摇/iFinD/官方报告采集脚本及 72 字段文件覆盖检查 | 对照既有月度实验和接口文档；真实响应同时检查 HTTP 与业务码，失败请求留审计重试；识别扶摇除复权事件业务 `3002` 为明确无匹配事件、iFinD 公司资料包含截止日之后的日期。原始响应仅在 Git 忽略目录，不将文件齐备当作字段核准 | `scripts/download_annual_raw.py`、`scripts/audit_annual_coverage.py`、`tests/test_annual_download.py`、`docs/experiments/2025-08-to-2026-08-full-download-audit.md` |
| 2026-09-26 | Codex：按用户要求将四档优先级贯穿证据和解读 | 来源/计算证据与结论的版本化优先级、计算输入优先级来源和受限 LLM 提示 | 用构造值核对字段映射、计算值不变、篡改档位与输入来源被拒；检查传给 LLM 的对象含优先级但不含财务原值。仅验证程序输入和校验逻辑，未声称在线 LLM 输出必然遵守篇幅指令 | `src/diagnosis/models.py`、`src/diagnosis/profit_cash.py`、`src/diagnosis/deepseek.py`、`tests/test_diagnosis.py`、`docs/decisions/0011-evidence-priority-propagation.md` |
| 2026-09-26 | Codex：根据用户指定的 CloudBase 路径整理部署契约 | Git 构建、云存储挂载、私有快照读取与验收清单 | 对照 CloudBase 官方 Git 部署、对象存储挂载和存储安全规则文档；仅确认平台支持该部署方式，未把账号套餐可用性、实际挂载或公开访问写成已通过 | `docs/decisions/0012-cloudbase-git-and-storage-deployment.md`、`docs/deployment-cloudbase.md` |

关键数字和结论必须回到原始字段或原文；后续在此记录发现并纠正的错误或不合理结果。
