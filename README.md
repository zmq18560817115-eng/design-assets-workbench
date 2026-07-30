# 设计灵感资产库

产品定位：**AI业务排版知识库与意向方向生成系统**。

当前唯一正式业务主线：

```text
素材上传 → AI拆解 → LayoutBlueprint → 人工校正与确认
         → LayoutPattern 候选发现 → 设计负责人人工审核模式
```

更完整的阶段约束见 [CURRENT_STAGE.md](CURRENT_STAGE.md)。

## 当前阶段判断

正式完成：

- 素材上传、批量导入与图片拆解。
- LayoutBlueprint 标准结构、人工校正、确认和版本追溯。
- BusinessRequirement 基础数据结构、草稿、编辑和确认。
- 从已确认蓝图人工沉淀排版模式。

本轮建设：

- 从每个案例最新的 verified 蓝图自动发现候选模式。
- 模式结构相似度、平均骨架、稳定 `pattern_code`。
- 模式证据、可信度、人工确认和停用。

实验性保留：

- 场景匹配。
- 三个排版方向。
- 方向反馈。

暂未正式验收：

- 真实场景检索准确率。
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
```

第一条仅预览缺失字段，不修改数据库。应用正常启动时也会安全增量建表、补列。

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
.\.venv\Scripts\python.exe -m py_compile app\main.py app\models.py app\schemas.py app\crud.py app\layout_blueprint.py app\layout_patterns.py
cd ..\frontend
npm.cmd run lint
npm.cmd run build
```

真实 AI 配置使用 `.env` 中的 `VISION_PROVIDER`、`VISION_API_KEY`、
`VISION_BASE_URL` 和 `VISION_MODEL`。凭证不得提交；未配置时使用明确标记的 fallback。
