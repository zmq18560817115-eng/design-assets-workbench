# 真实素材 Calibration 报告

- 数据集：`untitled1-visual-calibration-v1`
- 范围：仅 Calibration；未读取、未运行 Holdout Ground Truth
- 结论：未通过，不得冻结候选版本或运行 Holdout

## 基线与回归

| 指标 | 基线 | 回归 | 变化 |
|---|---:|---:|---:|
| total | 24 | 24 | 0 |
| task_success_rate | 0.0 | 0.0 | 0.0 |
| schema_valid_rate | 0.0 | 0.0 | 0.0 |
| product_detection_rate | 0.0 | 0.0 | 0.0 |
| product_missed_count | 0 | 0 | 0 |
| primary_text_detection_rate | 0.0 | 0.0 | 0.0 |
| layout_module_recall | 0.0 | 0.0 | 0.0 |
| module_type_accuracy | 0.0 | 0.0 | 0.0 |
| out_of_bounds_count | 0 | 0 | 0 |
| invalid_overlap_count | 0 | 0 | 0 |
| invalid_overlap_rate | 0.0 | 0.0 | 0.0 |
| timeout_rate | 1.0 | 1.0 | 0.0 |
| average_elapsed_ms | 30378 | 15320 | -15058 |
| p95_elapsed_ms | 30536 | 15379 | -15157 |

## 诊断

- 基线 24/24 请求超时，正式复现 `MODEL_TIMEOUT`。
- 候选版已压缩模型图片、收窄输出合同并限制输出长度，但当前生产模型端仍为 24/24 超时。
- 因模型没有返回有效 JSON，本轮无法据实评估 PRODUCT_MISSED、模块边界与异常重叠；不得把 0 次此类错误解释为能力通过。
- 下一步应先恢复或核验火山模型服务与部署点，再用同一 Calibration 数据和冻结前候选版本重新回归。

## 门禁

- 失败 `task_success_rate_min`：0.0（要求 0.95）
- 失败 `schema_valid_rate_min`：0.0（要求 0.98）
- 失败 `product_detection_rate_min`：0.0（要求 0.95）
- 失败 `primary_text_detection_rate_min`：0.0（要求 0.9）
- 失败 `layout_module_recall_min`：0.0（要求 0.9）
- 通过 `invalid_overlap_rate_max`：0.0（要求 0.05）
- 失败 `timeout_rate_max`：1.0（要求 0.05）
- 通过 `severe_regression_count_max`：0（要求 0）

## 版本处置

- Prompt：`visual-calibration-prompt-v2`（候选，未冻结）
- Validator：`visual-calibration-validator-v2`（候选，未冻结）
- Model：`ep-20260727140608-zgwnq`（未通过 Calibration）
- Holdout：禁止执行；本任务未读取答案、未运行盲测。
