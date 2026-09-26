# 0020：快照改为启动时从私有 COS 下载（备用方案）

- 日期：2026-09-26（北京时间）
- 状态：**已启用**（2026-09-26 用户在 011 挂载失败后批准，已合并到 main，待线上验证）；取代决策 0012 的“存储挂载”读取方式，0012 其余部分（Git 构建、私有存储、不入镜像）不变
- 关联：决策 0012（CloudBase 部署）、0017（公开展示）

## 背景

CloudBase 云托管的 COS 挂载多次失败：
- 004、005：平台生成的 Endpoint 缺少协议，cosfs 报 `option url has invalid format`；
- 010：经 API `UpdateCloudRunServer` 改为 `https://` 后，地址格式报错消失，但 cosfs 仍失败，平台日志只有“cosfs 挂载失败”，看不到具体原因。

挂载组件由平台控制，每次试验至少要等 5 分钟，失败时又拿不到原因，截止前继续盲试的风险较高。用户同意先把本方案写好作为备用。

## 选择

- 设置环境变量 `DIAGNOSIS_COS_BUCKET` 时，服务启动后用只读子账号密钥（`DIAGNOSIS_COS_SECRET_ID`、`DIAGNOSIS_COS_SECRET_KEY`）通过官方 SDK `cos-python-sdk-v5` 下载 `snapshots/profit_cash_002466.json` 与 `snapshots/product_snapshot_002466.json`。前缀默认为 `snapshots/`，地域默认为 `ap-shanghai`。文件先写临时文件，再原子替换到 `DIAGNOSIS_SNAPSHOT_DIR`（默认 `/tmp/snapshots`），之后仍由现有读取器校验内容摘要、版本和标的。
- 下载失败时服务照常启动，`/healthz` 如实报 `missing`，`snapshot_source` 只给错误码（例如 `AccessDenied`、`missing_credentials`）。后续请求到来时自动重试，间隔至少 60 秒。任何响应和日志都不含密钥、桶域名或对象地址。
- 不设置 `DIAGNOSIS_COS_BUCKET` 时行为完全不变（文件或挂载模式）。
- 未采用的做法：把快照打进镜像或提交 Git（仓库公开，违反决策 0012）；由浏览器直接读取 COS。

## 验证

- `tests/test_cos_fetch.py`（伪造 COS 客户端，5 项）覆盖以下情况：
  - 下载成功，四维与窄问题都能回答；
  - 缺少凭据、返回 403；
  - 响应中不泄露密钥和桶名；
  - 失败后按间隔节流重试；
  - 下载内容被篡改时，由摘要校验拒绝；
  - 未设置桶时，行为不变。
- 全部 68 项测试通过。
- 用无效密钥请求真实的桶，返回 `InvalidAccessKeyId`：证明网络可达、SDK 可用，并且错误只以错误码形式报告。

## 启用步骤（用户在控制台操作）

1. 在服务环境变量中新增：
   - `DIAGNOSIS_COS_BUCKET=7374-stock-diagnosis-qyw-d7b331670000-1496111595`
   - `DIAGNOSIS_COS_REGION=ap-shanghai`
   - `DIAGNOSIS_COS_SECRET_ID`、`DIAGNOSIS_COS_SECRET_KEY`：填只读子账号的 API 密钥，只在控制台填写
2. 关闭存储挂载：`UpdateCloudRunServer` 的 `VolumesConf` 设为空数组，或在控制台停用挂载。
3. 把 `snapshot-download` 分支合并到 `main` 并推送，自动部署会随之开始。
4. 验证：
   - `/healthz` 中 `snapshot_source.state` 为 `ok`，两份快照都为 `fixed`；
   - 运行 `py scripts/smoke_public.py`。
