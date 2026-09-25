# 0002｜项目 LLM 配置

- 日期：2026-09-25
- 状态：已确定并完成接入验证

## 选择

按项目要求使用用户提供的 DeepSeek API Key。项目环境变量为 `DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL=https://api.deepseek.com`、`DEEPSEEK_MODEL=deepseek-flash`。DeepSeek 官方文档将 `deepseek-flash` 对应到 DeepSeek-V4.1-Flash。

## 验证

- 使用本地 `.env` 中的密钥访问模型列表：成功，包含 `deepseek-flash`。
- 使用 `deepseek-flash` 发起最小文本补全：成功返回内容，响应报告 49 tokens。
- 未在此记录、模板或仓库中写入密钥值；本地 `.env` 和 `apikey.md` 由 `.gitignore` 排除。

## 来源

- [DeepSeek 官方首次调用说明](https://api-docs.deepseek.com/guides/harness)
- [DeepSeek 官方更新日志](https://api-docs.deepseek.com/updates/)
