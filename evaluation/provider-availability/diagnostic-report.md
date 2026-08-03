# 多模态服务可用性诊断

## 当前状态（2026-08-03 M1 复核）

- 服务状态：正式 Schema 单次请求成功，连续 3 次最小冒烟全部成功。
- Calibration 状态：服务可用，但 3 张 Canary 未通过业务质量门禁。
- Holdout：继续封存，未读取 Ground Truth，未执行模型调用。
- 24 张完整 Calibration：因 Canary 质量未达标而禁止运行。

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

### 单张正式 Schema 请求（M1）

- 北京时间窗口：2026-08-03 10:03–10:07。
- 使用 Calibration 图片，并发 1，流式响应，读超时不重试。
- HTTP：200；request_id：`0217857226165725630b2fa661ac131412e72f6bdd3759fbf0e1b`。
- 首个流式事件：3.978 秒；完整响应：222.871 秒。
- Schema 合法，5 个模块，未写入 verified、未覆盖人工结果。
- 业务校验仍报告 `LAYOUT_MODULE_MISSED`。

### 连续 3 次最小冒烟

- 3/3 成功，无 fallback。
- 最小文本总耗时：3.967 秒、2.695 秒、3.417 秒。
- 最小图片总耗时：44.940 秒、25.178 秒、38.260 秒。

### 3 张 Calibration Canary

- task_success_rate：100%；schema_valid_rate：100%；timeout_rate：0%。
- product_detection_rate：100%；module_type_accuracy：100%。
- primary_text_detection_rate：66.67%（门槛 90%）。
- layout_module_recall：0%（门槛 90%）。
- 结论：服务恢复，但业务质量门禁失败，不允许运行 24 张 Calibration。

## 根因结论

此前服务端响应前的 `read_timeout` 已通过流式正式合同恢复。当前阻断已从
“服务不可用”转为可度量的拆解质量不足，主要是主文字漏检和排版容器漏检。

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

仅使用 Calibration 修正 `main_text` 与 `layout_block` 的输出合同或识别策略，重新
运行同一 3 张 Canary。不得读取 Holdout，不得在 Canary 达标前运行 24 张完整集。

## 门禁

- 连续 3 次最小冒烟：通过
- 3 张 Calibration Canary：服务与 Schema 通过，业务质量未通过
- 24 张 Calibration：不允许
- Holdout：继续封存
