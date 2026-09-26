# CloudBase 部署执行清单

状态：服务已从 Git 构建上线，但快照存储挂载两次失败，诊断暂不可用；交接给 Codex 继续处理，见文末“状态与交接”。产品数据截至 2026-08-31，固定快照不自动刷新。

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

## 状态与交接（2026-09-26 13:40 北京时间，Claude Code → Codex）

### 已完成（已核实）

- **云环境**：CloudBase 个人版，环境 ID `stock-diagnosis-qyw-d7b331670000`，地域上海。
- **云托管服务** `lithium-diagnosis`：从 GitHub `yda12026-byte/1` 的 `main` 分支、以根目录 `Dockerfile` 构建，**自动部署已开启**（每次推送都会触发构建），服务端口 8080，公网访问已开启。
- **公网地址**：<https://lithium-diagnosis-319862-8-1496111595.sh.run.tcloudbase.com>。浏览器首次打开会出现 CloudBase 测试域名“风险提醒”页，需点“确定访问”；程序直接调用 API 不受该页拦截（已实测）。
- **当前线上版本**：首个版本 `lithium-diagnosis-001`（无挂载）。`/healthz` 返回 `status: ok`、`llm_configured: true`、`snapshots: {profit_cash: missing, product: missing}`，所以 `/api/bootstrap` 中各维度为 planned，诊断问题返回 503 `snapshot_unavailable`。拒答与缺口类回答正常。
- **环境变量**（用户在控制台填写，未在仓库记录值）：`DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL=https://api.deepseek.com`、`DEEPSEEK_MODEL=deepseek-flash`、`DIAGNOSIS_SNAPSHOT_PATH=/mnt/snapshots/profit_cash_002466.json`、`PORT=8080`。产品快照默认读取同目录下的 `product_snapshot_002466.json`。
- **云存储**：桶 `7374-stock-diagnosis-qyw-d7b331670000-1496111595`（环境自带桶），目录 `snapshots/002466/`，已上传两份快照，并逐个文件设为“私有读写”。
- **挂载用凭据**：已创建 CAM 子用户，编程访问，策略为 `QcloudCOSDataReadOnly`；其 API 密钥已在 CloudBase 的连接密钥里配置。密钥值只在控制台，不在仓库或对话中。
- **数据公开展示许可**：已确认，不设限流（决策 0017）。

### 未完成与已知问题

1. **存储挂载失败**。
   - **第一次**：选“腾讯云对象存储”，桶名手填，对象存储目录 `/snapshots/002466/`，实例目录 `/mnt/snapshots`。版本 `lithium-diagnosis-002` 部署失败，事件日志为：
     `Exec lifecycle hook ([/mount.sh]) for Container "side-dns-cache" ... cosfs 挂载失败`，
     `Warn:option url has invalid format:cos.ap-shanghai.myqcloud.com, correct example:-ourl=http://cos.ap-guangzhou.myqcloud.com`。
     即平台生成的 COS 地址缺少 `http://`，cosfs 拒绝了这个参数。表单中没有可以填写该地址的字段。
   - **第二次**：改选“云开发云存储”后再次失败。**错误日志尚未取得**，接手后先到服务的部署记录 / 版本事件里读取。
2. **产品快照需要重新上传**。本地快照已于 13:08 按决策 0018 重新生成，ID `f15e78c2f368f02b87e7`，含经营质量与风险两维所需的官方摘录。桶里的 `product_snapshot_002466.json` 可能还是旧版 `1e66af5657d890225715`：旧版只能运行四维，经营质量与风险会校验失败或缺数据。两字段快照 `profit_cash_002466.json`（ID `727ddd3473c779dc637c`）没有变化。
3. **公网验收未执行**。挂载一旦生效，运行 `py scripts/smoke_public.py`（验收脚本，本地 21/21 通过）。另需核对：
   - 重启后 `snapshot_id` 不变；
   - 直接访问快照对象被拒绝（在无痕窗口打开对象地址，应返回 AccessDenied）。

### 可选路径（改动部署方案前须经用户批准）

- **A. 继续排查挂载**：
  - 取第二次失败的日志；
  - 尝试把对象存储目录改为无结尾斜杠的 `/snapshots/002466` 或根目录 `/`，并相应把 `DIAGNOSIS_SNAPSHOT_PATH` 改为 `/mnt/snapshots/snapshots/002466/profit_cash_002466.json`；
  - 若 cosfs 仍报地址格式问题，属平台缺陷，可向 CloudBase 提工单。
- **B. 启动时下载（用户此前选择“只排查挂载”，切换前须重新征得同意，并新建决策取代 0012 的挂载部分）**：
  - 服务启动时用只读子账号密钥（新增环境变量，例如 `DIAGNOSIS_COS_SECRET_ID`、`DIAGNOSIS_COS_SECRET_KEY`、`DIAGNOSIS_COS_BUCKET`、`DIAGNOSIS_COS_REGION=ap-shanghai`），从私有桶下载两份快照到容器本地目录（如 `/tmp/snapshots`），再按现有读取器校验摘要。
  - 依赖 `cos-python-sdk-v5`，或用标准库实现 COS 签名。
  - 下载失败时 `/healthz` 如实报 `missing`，不回退到任何样本。
  - 需补测试（模拟下载成功/失败）并更新 `.env.example`、本清单、README、决策记录。
- **不采用**：把快照打进镜像或提交 Git。仓库是公开的，且违反决策 0012。

### 完成后需要同步的文档

- README“在线访问”一节的状态；
- `docs/test-plan.md` 中“公开部署”“CloudBase 快照读取”两行及公网验收结果；
- `docs/todo/TODO.md` 中部署相关三项；
- 当天工作日志与 AI 使用记录；
- 本清单的本节。

### Codex 接手核查（2026-09-26 13:36 北京时间）

- 直接读取部署记录 `005`（第二次选择“云开发云存储”）：Git 检出、Docker 构建及推送成功；实例创建时 `side-dns-cache` 的 `/mount.sh` 报 `Warn:option url has invalid format:cos.ap-shanghai.myqcloud.com`，与第一次相同。错误发生在平台的 cosfs 启动阶段，尚未到应用读取快照或鉴权检查。
- 控制台挂载表单只提供桶、对象目录、实例目录和连接密钥，没有 COS URL/endpoint 的可编辑项。按路径 A 将对象目录改为无结尾斜杠的 `/snapshots/002466`，使用既有只读连接密钥发布试验版本 `008`；其部署事件再次出现完全相同的 URL 格式错误，随后取消该试验版本发布。不能据此认定目录、密钥或代码是报错根因；继续改目录不会修正该 URL 参数。
- 当前线上无挂载版本 `007` 的 `/healthz` 为 200，但 `profit_cash`、`product` 均为 `missing`。尚未运行 21 项公网验收，也未验证重启后的 ID。
- COS 对象详情显示**实际对象地址**为桶内 `snapshots/product_snapshot_002466.json`，同目录另有 `profit_cash_002466.json`；交接原写的 `snapshots/002466/` 与实际地址不一致。产品对象仍为 12:25 上传的旧文件（控制台显示 297.32KB），本地新文件 ID `f15e78c2f368f02b87e7`、大小 322118 字节。匿名 HEAD 请求该旧对象得到 403。重新上传时须核对准确对象名、覆盖后 ID 和私有权限。
- 挂载方案目前被平台 cosfs 参数格式阻塞。路径 B 尚未获用户批准，未实施或配置启动下载；如继续挂载，可携带 `005`、`008` 的错误信息向 CloudBase 提工单。注意本节以上旧交接内容是当时状态，以上实测为当前状态。
