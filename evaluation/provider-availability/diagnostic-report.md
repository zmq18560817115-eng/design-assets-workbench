# 多模态服务可用性诊断

## 当前状态

- Calibration 状态：`blocked_by_provider_availability`
- 质量结论：未执行新的质量评估，不能标记为 `failed_quality_evaluation`
- Holdout：继续封存，未读取 Ground Truth，未执行模型调用
- 24 张完整 Calibration：禁止运行

## 已确认配置

- Provider：`volcengine`
- API Base URL：`https://ark.cn-beijing.volces.com/api/v3`
- 区域：`cn-beijing`
- 部署点：`ep-20260727140608-zgwnq`，不是占位值
- API Key：`configured`（报告和日志不保存密钥）
- HTTP 客户端：`httpx 0.28.1`
- 环境代理：未配置，`VISION_TRUST_ENV=false`
- 图片编码：压缩 JPEG 后使用 Base64 data URI
- 默认安全策略：并发 1、connect timeout 10 秒、read timeout 120 秒、最多重试 2 次、连续失败 3 次熔断

## 分层诊断结果

### 网络

- DNS：成功
- TCP/TLS：成功，TLS 1.3
- 域名：`ark.cn-beijing.volces.com`
- 本次网络探测耗时：114–148 ms

### 最小文本请求

- HTTP：200
- 服务商错误码：无
- 两次诊断耗时：约 3.0 秒、4.7 秒
- 已进入服务端：是
- 结论：API 地址、API Key、权限、部署点和基本配额可用

### 单张最小图片请求

- 输入：一张 Calibration 原图的 768px JPEG 副本，原图未修改
- 请求体内图片：54,352 bytes
- HTTP：200
- 服务商错误码：无
- 两次诊断耗时：约 29.6 秒、58.2 秒
- 已进入服务端：是
- 结论：部署点具备视觉输入能力，但图片请求延迟波动明显；此前 30 秒读取阈值会产生确定性或临界超时

### 单张正式 Schema 请求

- 使用同一张 Calibration 图片
- 并发：1
- read timeout：120 秒
- 有限重试：1 次
- 第一次：`read_timeout`，约 120.2 秒
- 第二次：`read_timeout`，约 120.2 秒
- HTTP 状态、服务商错误码、request_id：响应头返回前超时，因此不可得
- 未写入 verified、未覆盖人工结果

## 根因结论

已确认直接故障类型为服务端响应前的 `read_timeout`，不是笼统的模型超时，也不是图片拆解质量失败。

已排除：

- 本地 DNS 故障
- TCP/HTTPS 不可达
- TLS 握手或证书错误
- API Base URL 重复路径
- 系统代理误路由
- API Key 缺失或 401 鉴权失败
- 403 权限失败
- 部署点不存在或 404
- 413 请求体过大（最小图片请求已成功）
- 当前请求上的 429 限流、配额错误和 5xx

尚未排除：

- 当前部署点生成完整结构化输出时的推理吞吐不足或服务端拥塞
- 部署点的输出 token / 视觉推理性能配置不适合当前正式 Schema
- 服务商控制台中未通过 HTTP 响应返回的排队、容量或部署健康问题

## 下一项最小验证动作

由管理员在火山方舟控制台按上述成功请求的 request_id 和正式请求时间窗检查部署点日志、容量、排队和配额。服务端确认健康后，只运行连续 3 次最小预检；全部成功后才运行 3 张 Calibration Canary。Canary 未全部通过前不得运行 24 张 Calibration。

## 门禁

- 连续 3 次最小冒烟：未执行（正式 Schema 仍失败）
- 3 张 Calibration Canary：未执行
- 24 张 Calibration：不允许
- Holdout：继续封存
