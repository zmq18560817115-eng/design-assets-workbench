# 真实素材 Calibration 报告

## P3.2-C3 Validator v4（2026-08-03）

### 合同结论

人工绿色 `main_text` 是粗粒度空间标注；系统继续保留细粒度语义类型。Calibration 的主要文字区域检测允许以下类型参与一对一空间匹配：

- `main_title`
- `subtitle`
- `selling_point`
- `body_text`
- `feature_list`

该映射只影响 Calibration 指标，不会把正式 LayoutBlueprint 中的 `feature_list` 改写成 `selling_point`。`logo`、`price`、`cta`、`footnote`、`decoration`、`background`、图片类、`layout_block` 和 `parameter_table` 均不属于该集合。

### v3输出离线复评

- 源报告：`evaluation/provider-availability/calibration-canary-v3-live.json`
- 源 Prompt：`visual-calibration-prompt-v3`
- 源 Validator：`visual-calibration-validator-v3`
- 复评 Validator：`visual-calibration-validator-v4`
- `model_recalled=false`
- `holdout_read=false`，`holdout_executed=false`
- 离线复评全部门禁通过；主文字识别率由66.67%修正为100%。

| 图片 | 人工main_text | 预测主要文字子类型 | 命中 | 匹配证据 |
|---|---:|---|---:|---|
| Group 13.png | 2 | main_title×2, selling_point×1 | 2 | 两个 main_title 均由包含关系一对一命中，包含比例100% |
| Group 16.png | 1 | main_title×1, body_text×1 | 1 | main_title 包含比例95.67% |
| Group 34.png | 3 | main_title×1, subtitle×2, selling_point×2, feature_list×2 | 3 | 标题IoU 0.8429；左右 feature_list IoU 0.9135/0.9040，包含比例0.9165/0.9116 |

Group 34 两个 `feature_list` 分别命中两个底部绿色框，没有单个预测框重复命中多个 Ground Truth，也没有未命中文字框。

### Validator v4真实Canary

使用相同3张 Calibration 原图重新调用模型，Prompt保持v3，Validator使用v4：

| 指标 | 结果 | 门禁 |
|---|---:|---:|
| task_success_rate | 100% | 100% |
| schema_valid_rate | 100% | 100% |
| product_detection_rate | 100% | 100% |
| primary_text_detection_rate | 100% | ≥90% |
| layout_module_recall | 100% | ≥90% |
| module_type_accuracy | 100% | — |
| invalid_overlap_rate | 33.33% | ≤5% |
| timeout_rate | 0% | 0% |
| fallback_count | 0 | 0 |
| output_module_count | 29 | — |
| average_elapsed_ms | 185784 | — |

文字子类型输出分布为：`main_title=2`、`subtitle=2`、`selling_point=6`、`body_text=0`、`feature_list=2`。成功匹配人工 `main_text` 的类型为：`main_title=2`、`subtitle=2`、`feature_list=2`。

### 阻断原因

`Group 16.png` 中模型把 `decoration` 完全放入 `product_image`，二者 IoU 为0.7012。该关系不是允许的 layout/background 父容器包含关系，因此产生1个 `MODULE_OVERLAP_INVALID`。三张中一张失败使非法重叠率为33.33%。这属于模型输出不稳定/无效兄弟重叠，不是文字类型映射缺失，也不得通过放宽重叠规则制造通过。

因此未运行24张完整 Calibration，失败案例仅 `Group 16.png`（1张）；未运行Holdout。最终状态：`calibration_quality_blocked`。

## P3.2-C2 v3 Canary（2026-08-03）

### 结论

- v3 将 `layout_module_recall` 从 0% 修正到 100%，证明“无真实边框也可构成逻辑版块”的合同有效。
- `primary_text_detection_rate` 仍为 66.67%，未达到 90% 门禁。
- 失败集中在 `Group 34.png`：人工将左右下方两个完整文字信息组标为 `main_text`，模型输出为 `feature_list`；按冻结合同，`feature_list` 不能冒充 `main_text`。
- 这属于 Prompt 语义覆盖不足与模型类型选择问题，不是评测器漏算。未降低 IoU 阈值。
- 最终状态：`calibration_quality_blocked`。未运行24张完整 Calibration；Holdout 未读取、未运行。

### v2 / v3 汇总

| 指标 | v2 | v3 |
|---|---:|---:|
| task_success_rate | 100% | 100% |
| schema_valid_rate | 100% | 100% |
| product_detection_rate | 100% | 100% |
| primary_text_detection_rate | 66.67% | 66.67% |
| layout_module_recall | 0% | 100% |
| module_type_accuracy | 旧算法误报100% | 88.89% |
| invalid_overlap_rate | 0% | 0% |
| timeout_rate | 0% | 0% |
| 平均耗时 | 221941 ms | 188394 ms |
| 输出模块总数 | 23 | 30 |

### 逐图诊断

| 图片 | 版本 | 产品 GT/预测/最佳IoU | 主文字 GT/预测/逐框最佳IoU | 版块 GT/预测/逐框最佳IoU | 实际输出类型 | 诊断 |
|---|---|---|---|---|---|---|
| Group 13.png | v2 | 2/2/0.8470,0.8428 | 2/3/0.2955,0.2607 | 2/0/0,0 | product_image×2, subtitle×2, selling_point, other×2 | 可见边框规则导致版块全漏；文字框偏小，但位于人工完整文字组内，按包含关系命中。Prompt定义冲突，不是评测器错误。 |
| Group 13.png | v3 | 2/2/0.8734,0.8428 | 2/3/0.2533,0.2235 | 2/2/0.9612,0.9419 | layout_block×2, product_image×2, main_title×2, selling_point, scene_image×2 | 逻辑上下分区准确；文字仍偏小但被人工组包含，合同允许命中。 |
| Group 16.png | v2 | 1/1/0.6586 | 1/2/0.4332 | 2/0/0,0 | main_title, selling_point, product_image, decoration, person_image, footnote | 版块全漏源于Prompt定义冲突；标题组被拆小，包含关系命中。 |
| Group 16.png | v3 | 1/1/0.6750 | 1/2/0.3991 | 2/3/0.8268,0.8032 | layout_block×3, main_title, body_text, product_image, person_image, footnote | 顶部和主体分区命中；额外底部逻辑块不影响一对一召回。文字组边界仍小于人工框。 |
| Group 34.png | v2 | 2/2/0.7647,0.7921 | 3/6/0.4909,0,0 | 3/0/0,0,0 | main_title, subtitle, selling_point×4, product_image×2, feature_list×2 | 版块全漏；左右底部人工文字组被输出成 feature_list，按合同不能匹配 main_text。 |
| Group 34.png | v3 | 2/2/0.8044,0.8014 | 3/5/0.8429,0,0 | 3/3/0.8671,0.8268,0.8268 | layout_block×3, main_title, subtitle×2, selling_point×2, product_image×2, feature_list×2, decoration | 标题与三大逻辑分区准确；两个底部主要文字组仍被分为 feature_list，是Prompt语义覆盖不足/模型类型选择问题。 |

逐图数量均来自相同3张 Calibration 原图。最佳 IoU 是每个人工框与同评测类别预测框的空间 IoU；主文字的正式命中还允许预测文字框被人工完整文字组包含，但仍保持一对一匹配。

### v3 合同

- `layout_block` 是由留白、背景、对齐、堆叠、分栏、内容组合、层级和视觉中心形成的逻辑版块，不要求存在真实边框；优先输出2—5个主要分区，并允许包含产品和文字子模块。
- `main_text` 是视觉完整的主要文字组。模型使用 `main_title`、`subtitle`、`selling_point`、`body_text` 表达，空间上必须与人工文字组匹配；装饰小字、页码和不可读背景字不计入。

### 评测器与门禁修正

- 四种标准文字类型统一映射到人工 `main_text`，仍按空间关系匹配。
- 产品、文字、layout_block 分组一对一匹配，单个预测框不能重复命中多个人工框。
- `module_type_accuracy` 改为匹配类型数/可评估人工模块数；零匹配时为0，不再出现版块召回0但类型准确率100%的误导。
- 父 layout_block 包含子模块继续视为合法重叠；重复同类块仍拒绝。
- 完整 Calibration 必须同时满足 `quality_passed=true`、全部 quality gates、业务指标门槛且无 fallback，否则命令直接返回 `calibration_quality_blocked`。
- v3 使用独立报告与 raw 目录，不覆盖 v2；所有运行均声明 `verified_write_count=0`。

## M1 恢复复核（2026-08-03）

- 正式 Schema 单次请求成功，连续 3 次最小冒烟全部成功。
- 3 张 Canary 服务成功率和 Schema 合法率均为 100%，无超时、无 fallback。
- 主文字识别率为 66.67%，布局模块召回率为 0%，均未达到 90% 门槛。
- 因此未运行新的 24 张完整 Calibration；下方 24/24 timeout 为历史基线，
  不能当作本次恢复后的新结果。
- Holdout 继续封存，未读取答案，未执行模型调用。

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
