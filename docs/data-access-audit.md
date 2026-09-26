# 金融数据访问验证

首轮验证时间：2026-09-25 23:54 至 2026-09-26 00:13（北京时间）。本审计文档只记录权限、数量和字段结构，不包含原始行情、财务数据或授权值。`600519.SH` 是首轮权限验证样本；产品标的随后确定为 `002466.SZ`。后续 2026 年 8 月实验原始响应只保存在 Git 忽略的本地目录。

## 扶摇 REST API

- 本地配置：`.env` 中的 `FUYAO_API_KEY`、`FUYAO_BASE_URL`；请求头为 `X-api-key`。
- 使用样本股的真实调用全部返回 HTTP 200、业务 `code=0`：行情快照 1 条；近 60 天日 K 43 条；利润表、资产负债表、现金流量表各 4 期；`2026-2` 财务指标 24 项；估值快照 1 条。
- 已确认可取得行情 OHLC/成交量/成交额、财报期次及关键科目、估值 PE/PB/PS/PCF。具体数值、单位与统计口径要在确定产品标的后逐字段校验。
- 可用 `node scripts/probe-fuyao.mjs 600519.SH` 复查。探测脚本不输出原始数值。
- 2026-09-26 00:23（北京时间）对天齐锂业 `002466.SZ` 复查：行情快照 1 条、近 60 天日 K 42 条、利润表/资产负债表/现金流量表各 4 期、`2026-2` 财务指标 24 项、估值快照 1 条；七类请求均为 HTTP 200、业务 `code=0`。可用 `node scripts/probe-fuyao.mjs 002466.SZ` 复查。

## iFinD MCP

- 用户提供的授权已写入本地 `.env`；同花顺官方 `ifind-finance-data` Skill 1.4.0 已安装于 Codex 用户 Skill 目录并配置相同授权。本地 Node.js 版本为 24.19.0。
- 安装包来自官方安装指南中的 URL，下载文件 SHA-256 为 `C16074BA363FCE498ADBF2F223BFA3CF5ABA4B56BAEF0E7E2524F6DA61EBD837`；临时下载与解压副本在安装验证后已删除。
- 安装后的 `listTools('stock')` 自检成功（HTTP 200，10 个工具）。`index` 3 个、`edb` 2 个、`news` 3 个、`global_stock` 5 个工具也可列出。
- 实际调用 `get_stock_info` 与 `search_news` 均返回 HTTP 200、非错误且有非空内容。未将返回原文写入仓库。
- iFinD `get_stock_info` 对 `002466.SZ` 返回公司名称“天齐锂业”，主营业务为锂精矿及锂化工产品的生产、加工和销售，所属申万和同花顺一级行业均为“有色金属”。同行比较仍需定义更细的业务可比口径。
- 项目 `.env` 提供 `IFIND_MCP_AUTH_TOKEN` 与 `IFIND_MCP_URL`；可用 `node scripts/probe-ifind.mjs` 复查。Web 产品尚未实现 iFinD 数据适配层。
- 另外已将用户提供的 9 个 Streamable HTTP 服务注册到本机 Codex 用户配置 `C:\Users\qyw\.codex\config.toml`，使用各自 URL 和 Authorization 请求头；改动前的配置已在同目录备份。`codex mcp list --json` 能解析并显示 9 个服务均为启用状态。
- 2026-09-26 00:13 对这 9 个服务逐一执行 MCP `initialize` 与 `tools/list`，全部返回 HTTP 200，工具数量依次为：综合 9、企业 2、法律 6、股票 10、基金 8、经济数据 2、资讯 3、债券 5、指数 3。当前已启动的 Codex 任务未动态加载新工具，需要新任务或重启 Codex 后在工具列表中确认。

## 安全与边界

- 2026-09-26 将原 Node 探测脚本迁移为 `py scripts/probe_fuyao.py 002466.SZ` 与 `py scripts/probe_ifind.py`。迁移后再次实测：扶摇七类请求均为 `ok`，返回条数依次为 1、42、4、4、4、24、1；iFinD 十个服务的工具列表均为 `ok`，数量依次为 9、2、6、10、8、3、2、3、5、5。此前文中的 `node scripts/...` 命令仅记录当时的验证方法，当前请使用 Python 命令。探测仍只输出状态、数量、字段名，不输出密钥或完整数据。
- 2026-09-26 预下载切片对天齐锂业的扶摇年报利润表与现金流量表取数成功，发布 2 项标准化来源字段；产物在 Git 忽略的 `data/cache/`，未保存完整 API 响应。iFinD 仍仅完成权限和字段候选核查，产品预下载尚未接入。
- 2026-09-26 按数据截止日 2026-08-31 完成 8 月实验下载：扶摇 7 组、iFinD 17 组均有成功响应，另下载深交所 2026 年半年报原文。日线、财报、估值、行业、锂价、股东/事件、公告/新闻的数量、日期与口径问题见[实验审计](experiments/2026-08-one-month-data-audit.md)。原始返回只在 Git 忽略的 `data/raw/`，不属于发布快照。

- `.env` 被 Git 忽略；iFinD Skill 的 `mcp_config.json` 位于用户本机的 Codex Skill 目录，不在项目仓库。
- Codex 用户配置含授权请求头，位于仓库之外；不得把它或其备份加入 Git。
- 这次验证证明当前凭据和样本接口可用；不代表所有接口、时点和数据使用场景均已授权。产品调用要逐接口检查业务错误和数据缺失。
- iFinD 授权可能随账户状态变化，部署时需在平台环境变量中配置，不得提交到公开仓库。

## 一年观察区间原始下载（2026-09-26）

对天齐锂业 `002466.SZ` 与候选同行赣锋锂业 `002460.SZ` 运行 `py scripts/download_annual_raw.py --source fuyao|ifind|official`，目标窗口 2025-08-31 至 2026-08-31。取得扶摇 19 组响应（18 组 HTTP 200、业务 `code=0`；除复权事件一组 HTTP 200、`code=3002` 明确无匹配记录），iFinD 128 组响应（HTTP 200、MCP 工具无错误、内层业务 `code=1` 且有 `data`），另取得 5 份官方定期报告 PDF。两项 iFinD 临时连接错误重试后成功；原始响应、请求参数、下载时间和 SHA-256 仅保存在 Git 忽略目录。扶摇两股前复权日线各 242 条、实际日期 2025-09-01 至 2026-08-31；三张报表每股各 12 期，财务指标按五个报告期查询。详见[一年原始数据审计](experiments/2025-08-to-2026-08-full-download-audit.md)。

这次是原始采集的权限/覆盖验证，不是逐字段核准：iFinD 自然语言返回出现周末行和截止日后的日期；估值与行业返回自然日行，公告检索片段没有证明全年原文齐全。扶摇个股异动原因接口仅支持当日，无法回溯本窗口；该候选项保持历史数据缺口。除复权 `3002` 只说明请求范围内无匹配事件，不可扩展为公司不存在任何分红或送配行为。2026-08-31 截止日后的信息不能进入产品快照。

2026-09-26 按决策 0013 的正式同行组补下载：扶摇新增中矿资源 `002738.SZ`、永兴材料 `002756.SZ`，各取得 242 条前复权日线、12 期三张报表、5 期财务指标（HTTP 200、业务 `code=0`）；iFinD 新增两家 2026-06-30 财务、四只股票 2026-08-31 同日估值（HTTP 200、内层 `code=1`）。赣锋沿用已有文件，未覆盖任何成功文件。同行财务的报告期语义与同日/同区间口径仍待核准。

2026-09-26 核实 iFinD 估值 TTM/MRQ 口径（决策 0014）：`get_stock_performance` 返回的 `indicators_params` 显示 `PE(TTM)` 的 `TTM基准日 = 报表公告日期`、`PB(最新)` 的 `基准日 = 报表截止日期`、交易日为指定日期。用扶摇累计报表反推确认分子为总市值、`PE(TTM)` 分母为归母净利润 TTM、`PE(MRQ)` 半年报年化 ×2、`PB(MRQ)` 分母为归母净资产、`PS/PCF(TTM)` 为收入/经营现金流 TTM；亏损期返回负 PE。另发两条查询：2026-08-31 的总市值/流通市值，及 2024-12-31 的估值指标。分子绝对水平与本地归母 TTM 约差 5%，且候选查询元数据出现“总市值 交易日期 = 最新”，列为未解释项；文档只记录比值与结论，不含受限数值。同日第三轮核实（2 条只读查询，未落盘）：PE/PB 市值 = 总股本 × A 股收盘价（比值 1.0000），“总市值”对 H 股按港股价，差异查明；同行组 PE 显式 20260831 重查与原文件逐一相同，“交易日期: 最新”标签不可靠。

## 官方资料

- [扶摇快速开始](https://fuyao.aicubes.cn/docs/quickstart/)
- [扶摇行情接口](https://fuyao.aicubes.cn/docs/api-reference/prices/)
- [扶摇财报接口](https://fuyao.aicubes.cn/docs/api-reference/financials/)
- [扶摇估值接口](https://fuyao.aicubes.cn/docs/api-reference/valuations/)
- [iFinD Skill 安装指南](https://mcp.51ifind.com/gwstatic/static/ds_web/ifind-mcp-web/skills/SKILL_INSTALL_GUIDE.md)
- [Codex 配置参考：MCP 服务与 HTTP 请求头](https://developers.openai.com/codex/config-reference)

## 2026-09-26 巨潮资讯公告清单与原文（决策 0022）

- 请求：`POST https://www.cninfo.com.cn/new/hisAnnouncement/query`，`stock=002466,<orgId>`（orgId 由 `/new/information/topSearch/query` 按代码唯一匹配），`column=szse`、`tabName=fulltext`、`seDate=2025-08-31~2026-08-31`，每页 30 条翻页。HTTP 200；`totalAnnouncement=207`，取回 207 条，公告编号无重复，全部为 PDF。
- 字段：公告编号、标题、公告时间（毫秒，按北京时间换算为披露日）、附件路径（拼接 `https://static.cninfo.com.cn/`）。
- 原文：按标题规则选出八类重要事项中非定期报告的 21 份，下载 PDF 共约 2.8MB；同日追加“资本运作”类后续下 5 份，共 26 份；定期报告只用清单中的披露时间。
- 限制：公开接口无需密钥，但属网站查询接口，字段含义以返回为准；清单与 PDF 存于 Git 忽略的一年原始目录，不入仓库。
