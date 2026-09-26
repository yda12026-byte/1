# CloudBase 部署执行清单

状态：部署路径已确定，云上操作尚未执行。产品数据截至 2026-08-31，固定快照不自动刷新。

## 代码与快照分离

1. 将经测试的 Python Web 代码提交到 Git 仓库。云托管使用[Git 仓库部署](https://docs.cloudbase.net/run/deploy/deploy/deploying-git)构建镜像；构建上下文不得包含 `.env`、`apikey.md`、`data/raw/` 或产品快照。
2. 只把逐字段核准、许可允许保存的**发布快照**上传到 CloudBase 云存储。使用不可变的版本化对象名，例如 `snapshots/002466/2026-08-31/<snapshot_id>.json`；记录文件摘要、下载时点、报告期、上传对象名和核准清单。原始扶摇/iFinD 批量响应不作为产品快照上传。
3. 在云托管服务的“存储挂载”中选择“云开发对象存储”，将快照目录挂载到容器内的路径，例如 `/mnt/diagnosis-snapshots`。官方[挂载说明](https://docs.cloudbase.net/run/deploy/configuring/storage/cos)给出了控制台步骤；最终路径以实际配置为准。设置服务端环境变量 `DIAGNOSIS_SNAPSHOT_PATH` 为**准确文件路径**，例如 `/mnt/diagnosis-snapshots/002466/2026-08-31/<snapshot_id>.json`。完整产品快照 `product_snapshot_002466.json`（决策 0016）放在同一挂载目录即可被自动读取；若对象名不同，另设 `DIAGNOSIS_PRODUCT_SNAPSHOT_PATH` 为其准确路径。两份文件都由服务端校验摘要。
4. 在云存储权限设置中阻止浏览器直接读取快照。不要将 fileID、下载链接、存储凭据或原始快照作为公开页面配置；前端只请求云托管诊断接口，服务端按数据展示许可返回必要证据。参见[存储安全规则](https://docs.cloudbase.net/storage/security-rules)。

## 云托管配置与验证

- 构建入口为仓库根目录 `Dockerfile`：Gunicorn 运行 `webapp:app`，监听 `PORT`（默认 8080），超时 60 秒；健康检查 `GET /healthz`；诊断接口 `GET /api/bootstrap`、`POST /api/chat`（决策 0015、0016）。服务端环境变量：`DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL`、`DEEPSEEK_MODEL`、`DIAGNOSIS_SNAPSHOT_PATH`，可选 `DIAGNOSIS_PRODUCT_SNAPSHOT_PATH`。
- DeepSeek 密钥只放服务端环境变量；提问路径不需要扶摇/iFinD 凭据。云托管存储挂载所需访问密钥按 CloudBase 控制台流程配置，采用最小访问范围，不写进项目文件。
- 启动时验证挂载文件存在且快照内容摘要、标的、版本和截止日正确。异常时服务报告“快照不可用”；不得把缺失当零，也不得退回构造样本。
- 公开 URL 验收：页面可打开；四类已实现问题可操作；证据可钻取；显示报告期和快照时间；缺失/冲突/不适用状态正确；直接访问云存储快照被拒绝；容器重启后仍读到相同 `snapshot_id`。其他维度在数据和计算未就绪时仍标为待实现。
- 记录真实环境 ID、服务名、部署版本和 URL 时，应写入 README 与测试记录；不要在这些记录中写访问密钥。公开展示许可已由用户确认，且不设接口限流（决策 0017）。

Git 构建只能读取已推送的提交。首次部署前需完成代码、文档、测试和敏感内容审查，再配置云托管仓库绑定与存储挂载。
