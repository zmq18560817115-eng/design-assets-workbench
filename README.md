# 设计灵感资产库

## P3.2-C：前端主线与拆解校准

正式业务主线为：素材上传 → AI 多模态拆解 → `LayoutBlueprint` → 人工校正与确认
→ `LayoutPattern` → `BusinessRequirement` → 案例与模式检索 → 人工反馈。

- 普通设计师使用 `/assets` 统一完成素材库、导入和待审核工作。
- 管理员在 `/admin/analysis-evaluation` 运行图片拆解质量校准。
- `/layout-search/evaluation` 只负责业务需求检索准确率验收，两套验收互不混用。
- Calibration 可查看 Ground Truth 和诊断；Holdout 默认密封，只允许冻结版本运行一次。
- 解封 Holdout 会将数据集标记为 `consumed`，之后不得再次作为盲测集。
- 公司成品和外部参考是不同证据；外部素材不能代表公司业务标准。

这里的“学习”是公司素材 Ground Truth、Prompt/Validator 校准、人工反馈和独立盲测，
不是基础多模态模型微调，也不代表系统已学会未经证据支持的“公司偏好”。

## Task 4.1：冻结式检索验收

Task 4.1B 已提供设计负责人可直接操作的数据集工作台：未冻结标注可新增、编辑和删除，可查看需求业务条件、案例原图与蓝图、模式证据，冻结后全部只读。完整验收包不包含原图或 API 密钥。

当前正式主线：

`素材上传 → AI拆解 → 蓝图人工确认 → 排版模式沉淀 → 真实需求 → 冻结Ground Truth → 校准集调试 → 留出集验收 → 通过后进入多案例排版方向`

Task 4 的验收工具建设已完成：可以创建真实验收数据集、预先标注并冻结 Ground Truth、分别运行 calibration/holdout、查看准备度和三态验收结果，以及事务式导入导出完整验收包。

这不表示真实业务验收已经通过。进入 Task 5 前仍须由设计团队提供至少 50 个带 verified LayoutBlueprint 的公司真实案例、至少 5 个 verified LayoutPattern，以及 10 条 confirmed 真实需求（calibration 至少 7 条、holdout 至少 3 条）。calibration 仅用于规则校准；holdout 不得反复用于调权。

`ENABLE_LAYOUT_DIRECTIONS` 默认为 `false`。旧方向接口为 legacy 兼容能力，只有显式开启才可调用；真实验收通过前不属于正式主线能力。系统当前不训练偏好模型，也不生成最终设计图。

工作台：

- `/layout-search/evaluation`
- `/layout-search/evaluation/datasets`
- `/layout-search/evaluation/datasets/{version}`

产品定位：**AI业务排版知识库与意向方向生成系统**。

当前正式业务主线：

```text
素材上传 → AI拆解 → LayoutBlueprint → 人工校正与确认
         → LayoutPattern 候选发现与审核 → BusinessRequirement
         → 已确认模式/案例检索 → 相关性反馈与 Precision 评估
```

更完整的阶段约束见 [CURRENT_STAGE.md](CURRENT_STAGE.md)。

## 当前阶段判断

正式完成：

- 素材上传、批量导入与图片拆解。
- LayoutBlueprint 标准结构、人工校正、确认和版本追溯。
- BusinessRequirement 基础数据结构、草稿、编辑和确认。
- 从已确认蓝图人工沉淀排版模式。

P3 本轮建设：

- 使用必需/禁止模块、业务字段和画布结构检索已确认模式与案例。
- 参考图片临时蓝图，不创建公共 Case。
- 保存检索快照和人工相关性反馈，统计 Precision@5/10。

实验性保留：

- 场景匹配。
- 三个排版方向。
- 方向反馈。

暂未正式验收：

- 50 张公司真实素材和 10 条真实需求的真实场景准确率。
- 多案例融合方向。
- 业务反馈学习。
- 模型训练。
- 最终设计图生成。

Preference、Training、Company Profile、Service Run、Project Review 是
legacy 兼容能力。旧接口、表和历史数据暂时保留，但不属于当前业务主线。

## LayoutPattern 自动发现

只有满足以下条件的蓝图才参与：

- `review_status == verified`。
- 每个真实案例只取版本号最高的合法 verified 蓝图。
- 坐标、模块数量、画布边界和比例通过 LayoutBlueprint 校验。

相似度权重：

- 模块类型：35%。
- 模块位置和尺寸：35%。
- 栅格、阅读动线和签名：15%。
- 画布与信息密度：15%。

默认阈值为 `0.72`。先按方向、比例和信息密度严格分桶，再进行确定性聚类。
少于 3 个不同案例的组不生成候选。

同类型模块按 `y、x` 排序编号，例如 `selling_point-1`。在 80% 及以上
案例出现的模块为必需模块，30%～79% 为可选模块，低于 30% 不进入标准骨架。
平均坐标会再次通过 LayoutBlueprint 校验。

候选模式由结构特征生成稳定 `pattern_code`。自动结果始终为 `draft`；
`verified`、`disabled` 以及人工创建或修改的模式不会被自动覆盖。

## 模式发现 API

| 方法 | 地址 | 说明 |
|---|---|---|
| GET | `/api/layout-patterns` | 查询模式，支持状态、方向、比例、密度和可信度筛选 |
| POST | `/api/layout-patterns` | 保留的人工模式创建接口 |
| POST | `/api/layout-patterns/rebuild` | dry-run 预览或安全执行自动发现 |
| GET | `/api/layout-patterns/{id}` | 查看模式 |
| PATCH | `/api/layout-patterns/{id}` | 修改自动候选名称、说明和场景 |
| POST | `/api/layout-patterns/{id}/revise` | 保留的人工修订接口 |
| POST | `/api/layout-patterns/{id}/verify` | 人工确认 |
| POST | `/api/layout-patterns/{id}/disable` | 停用但不删除 |
| GET | `/api/layout-patterns/{id}/evidence` | 查看案例、蓝图、相似度和模块证据 |

## P3 业务场景检索

评分固定为 100 分：业务场景 35、必需模块 25、画布结构 20、信息密度 10、
视觉风格 5、人工验证 5。未填写条件保持中性；禁止模块命中结果进入排除区。
检索不读取 PreferenceEvent 或公司偏好权重。

| 方法 | 地址 | 说明 |
|---|---|---|
| POST | `/api/business-requirements/{id}/layout-search` | 执行并保存一次检索 |
| GET | `/api/business-requirements/{id}/layout-search/latest` | 获取最近运行 |
| POST | `/api/layout-search-runs/{id}/feedback` | 保存相关性反馈 |
| GET | `/api/layout-search/evaluation` | 查看 Precision@5/10 与违规数 |

真实验收流程见 [业务场景检索验收手册](docs/业务场景检索验收手册.md)。

dry-run 示例：

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/layout-patterns/rebuild `
  -ContentType application/json `
  -Body '{"dry_run":true,"similarity_threshold":0.72,"minimum_evidence":3}'
```

## 数据库升级

继续使用 SQLite，不删除或重建数据库：

```powershell
cd backend
.\.venv\Scripts\python.exe .\scripts\upgrade_layout_patterns_v2.py
.\.venv\Scripts\python.exe .\scripts\upgrade_layout_patterns_v2.py --execute
.\.venv\Scripts\python.exe .\scripts\upgrade_layout_search_v1.py
.\.venv\Scripts\python.exe .\scripts\upgrade_layout_search_v1.py --execute
```

不带 `--execute` 的命令仅预览，不修改数据库。应用正常启动时也会安全增量建表。

## 本地启动

后端：

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

前端：

```powershell
cd frontend
npm.cmd ci
npm.cmd run dev
```

访问地址：

- 前端：`http://127.0.0.1:3000`
- 排版模式：`http://127.0.0.1:3000/patterns`
- API 文档：`http://127.0.0.1:8000/docs`

## 验证

```powershell
cd backend
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m py_compile app\main.py app\models.py app\schemas.py app\crud.py app\layout_blueprint.py app\layout_patterns.py app\layout_search.py app\search.py
cd ..\frontend
npm.cmd run lint
npm.cmd run build
```

真实 AI 配置使用 `.env` 中的 `VISION_PROVIDER`、`VISION_API_KEY`、
`VISION_BASE_URL` 和 `VISION_MODEL`。凭证不得提交；未配置时使用明确标记的 fallback。

## P3.2-A 统一业务素材数据合同

- 公司成品使用 `company_published`，代表真实发布证据，但上传或 AI 分析本身不等于公司推荐。
- 外部素材使用 `external_reference`，只能作为参考证据，不能代表公司业务标准，也不会自动创建黄金项目。
- 历史 `company_finished_asset`、`internal_reference` 继续可读；新导入使用规范值。
- Case 业务字段包括 `product_name`、`content_purpose`、`page_role`、`sequence_index`、`brief_ref`。
- CSV/JSON manifest 字段优先于文件夹推断；无 manifest 时标记 `metadata_status=inferred`。
- 当前阶段是大批量拆解、人工审核和知识沉淀，不是模型微调。
- 正式主线仍是 `LayoutBlueprint → LayoutPattern → layout_search`，不读取 PreferenceEvent 作为正式权重。

## 全品类排版拆解学习

- 审核入口：`/annotation-learning`；旧的 `/annotation-learning/disinfection-cabinet` 保持兼容。
- 通用接口：`/api/layout-annotations`、`/api/layout-annotations/few-shots` 和
  `/api/cases/{case_id}/layout-auto-decompose`。
- 模型优先使用“同产品分类 + company_published + 人工 verified + calibration”的证据。
- 同品类不足时，公司其他品类只能作为 `cross_category_structure_reference`；
  外部素材仅在显式 `evidence_mode=imitation` 时作为 `imitation_reference`。
- 单品类至少 3 个 calibration 证据可试运行 few-shot；达到 30 张 verified 且存在
  holdout 后才标记该品类评估就绪。
- 通用彩框标注导入：

```powershell
cd backend
.\.venv\Scripts\python.exe scripts\import_layout_annotations.py `
  --source ..\Untitled1 --product-category 消毒柜
```

默认是 dry-run；人工核对统计后追加 `--execute` 才写入本地库，且所有新记录仍为
`pending_review`，不会自动成为学习证据。

Manifest 模板：`docs/templates/asset-import-manifest.csv`。
