# 金融数据访问验证

验证时间：2026-09-25 23:54 至 2026-09-26 00:13（北京时间）。这里只记录权限、数量和字段结构，不保存原始行情、财务数据或授权值。样本股 `600519.SH` 仅用于验证权限，尚未选定为产品标的。

## 扶摇 REST API

- 本地配置：`.env` 中的 `FUYAO_API_KEY`、`FUYAO_BASE_URL`；请求头为 `X-api-key`。
- 使用样本股的真实调用全部返回 HTTP 200、业务 `code=0`：行情快照 1 条；近 60 天日 K 43 条；利润表、资产负债表、现金流量表各 4 期；`2026-2` 财务指标 24 项；估值快照 1 条。
- 已确认可取得行情 OHLC/成交量/成交额、财报期次及关键科目、估值 PE/PB/PS/PCF。具体数值、单位与统计口径要在确定产品标的后逐字段校验。
- 可用 `node scripts/probe-fuyao.mjs 600519.SH` 复查。探测脚本不输出原始数值。

## iFinD MCP

- 用户提供的授权已写入本地 `.env`；同花顺官方 `ifind-finance-data` Skill 1.4.0 已安装于 Codex 用户 Skill 目录并配置相同授权。本地 Node.js 版本为 24.19.0。
- 安装包来自官方安装指南中的 URL，下载文件 SHA-256 为 `C16074BA363FCE498ADBF2F223BFA3CF5ABA4B56BAEF0E7E2524F6DA61EBD837`；临时下载与解压副本在安装验证后已删除。
- 安装后的 `listTools('stock')` 自检成功（HTTP 200，10 个工具）。`index` 3 个、`edb` 2 个、`news` 3 个、`global_stock` 5 个工具也可列出。
- 实际调用 `get_stock_info` 与 `search_news` 均返回 HTTP 200、非错误且有非空内容。未将返回原文写入仓库。
- 项目 `.env` 提供 `IFIND_MCP_AUTH_TOKEN` 与 `IFIND_MCP_URL`；可用 `node scripts/probe-ifind.mjs` 复查。Web 产品尚未实现 iFinD 数据适配层。
- 另外已将用户提供的 9 个 Streamable HTTP 服务注册到本机 Codex 用户配置 `C:\Users\qyw\.codex\config.toml`，使用各自 URL 和 Authorization 请求头；改动前的配置已在同目录备份。`codex mcp list --json` 能解析并显示 9 个服务均为启用状态。
- 2026-09-26 00:13 对这 9 个服务逐一执行 MCP `initialize` 与 `tools/list`，全部返回 HTTP 200，工具数量依次为：综合 9、企业 2、法律 6、股票 10、基金 8、经济数据 2、资讯 3、债券 5、指数 3。当前已启动的 Codex 任务未动态加载新工具，需要新任务或重启 Codex 后在工具列表中确认。

## 安全与边界

- `.env` 被 Git 忽略；iFinD Skill 的 `mcp_config.json` 位于用户本机的 Codex Skill 目录，不在项目仓库。
- Codex 用户配置含授权请求头，位于仓库之外；不得把它或其备份加入 Git。
- 这次验证证明当前凭据和样本接口可用；不代表所有接口、时点和数据使用场景均已授权。产品调用要逐接口检查业务错误和数据缺失。
- iFinD 授权可能随账户状态变化，部署时需在平台环境变量中配置，不得提交到公开仓库。

## 官方资料

- [扶摇快速开始](https://fuyao.aicubes.cn/docs/quickstart/)
- [扶摇行情接口](https://fuyao.aicubes.cn/docs/api-reference/prices/)
- [扶摇财报接口](https://fuyao.aicubes.cn/docs/api-reference/financials/)
- [扶摇估值接口](https://fuyao.aicubes.cn/docs/api-reference/valuations/)
- [iFinD Skill 安装指南](https://mcp.51ifind.com/gwstatic/static/ds_web/ifind-mcp-web/skills/SKILL_INSTALL_GUIDE.md)
- [Codex 配置参考：MCP 服务与 HTTP 请求头](https://developers.openai.com/codex/config-reference)
