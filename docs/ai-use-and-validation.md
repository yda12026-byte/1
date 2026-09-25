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

关键数字和结论必须回到原始字段或原文；后续在此记录发现并纠正的错误或不合理结果。
