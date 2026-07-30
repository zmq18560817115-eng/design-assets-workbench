# 设计灵感资产库 · Phase 1

独立服务公司设计部门的视觉知识资产系统。第一阶段只建设：

```text
素材进入 → AI拆解 → 多模态检索 → 案例选择
```

不包含 AI 组合方向、方案工作台、导出与公司风格训练。

## 已实现

- 单图上传与批量导入
- 三类业务来源：公司已发布作品、外部优秀案例、未采用参考方案
- dHash 近重复素材识别
- Pillow 客观视觉测量 + 可插拔视觉大模型语义拆解
- 版式、信息层级、字体、色彩、构图、光影、材质与设计规则
- AI 未校验 / 已校验 / 公司推荐可信状态的数据基础
- 分析版本快照
- 文本、产品、场景、内容类型、来源与参考图混合搜索
- 搜索相关度和匹配原因
- 案例多选与底部选择托盘
- 首页、素材库、上传、批量导入、搜索与案例详情

## 技术结构

```text
frontend/  Next.js 14 + Tailwind CSS
backend/   FastAPI + SQLAlchemy + Pillow
database   SQLite（本地验证），后续迁移 PostgreSQL
AI         OpenAI 兼容视觉模型接口；未配置时使用启发式拆解
```

本项目借鉴 `linggan-agent` 的上传、拆解、存储与案例详情能力，但使用独立项目命名、
独立数据库和新的第一阶段产品边界。

## 启动后端

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

接口文档：`http://127.0.0.1:8000/docs`

## 启动前端

```bash
cd frontend
npm install
npm run dev
```

前端地址：`http://127.0.0.1:3000`

## 当前阶段：AI业务排版知识库与意向方向生成系统基础层

本轮只建设两个基础模块，不训练偏好、不生成最终设计图：

```text
素材上传 → AI图片拆解 → LayoutBlueprint v2 → 人工校正与确认
         → BusinessRequirement 结构化需求
```

### 新增数据模型

- `layout_blueprints`：案例的一对多版本化排版蓝图；新增
  `margins_json`、`layout_signature`，状态使用 `ai_generated`、
  `corrected`、`verified`。旧状态仍只为历史接口兼容。
- `business_requirements`：补充内容目的、必需/可选/禁止模块、卖点、
  风格关键词、原始需求、参考案例、参考图片和创建人，状态为
  `draft`、`confirmed`、`archived`。
- 原有 `analysis`、`analysis_versions`、案例与图片数据不删除、不覆盖。

### 本阶段 API

| 方法 | 地址 | 说明 |
|---|---|---|
| GET | `/api/cases/{id}/layout-blueprint` | 当前蓝图 |
| PATCH | `/api/cases/{id}/layout-blueprint` | 校正并新增版本 |
| POST | `/api/cases/{id}/layout-blueprint/regenerate` | 按需重新调用拆解 |
| POST | `/api/cases/{id}/layout-blueprint/verify` | 确认当前版本 |
| GET | `/api/cases/{id}/layout-blueprint/versions` | 历史版本 |
| GET/POST | `/api/business-requirements` | 需求列表/创建 |
| GET/PATCH | `/api/business-requirements/{id}` | 需求详情/修改 |
| POST | `/api/business-requirements/{id}/confirm` | 确认需求 |
| POST | `/api/business-requirements/reference-image` | 上传需求参考图 |

旧的复数蓝图 API 继续保留，以免破坏已有前端或外部调用。

### 新增页面

- `/requirements`：业务需求列表。
- `/requirements/new`：创建并保存草稿。
- `/requirements/{id}`：查看、编辑和确认需求。
- `/cases/{id}`：原图与低保真蓝图、模块表单、版本、模型与 Prompt 信息。

### 数据库升级

项目继续使用 SQLite。启动后端时会通过 `create_all + ALTER TABLE` 安全增量建表/建列。
现有数据库升级与签名回填可显式执行：

```powershell
cd backend
.\.venv\Scripts\python.exe .\scripts\upgrade_foundation_v2.py
.\.venv\Scripts\python.exe .\scripts\upgrade_foundation_v2.py --execute
```

第一条仅预览，第二条执行；不会删除数据库，也不会修改旧 Analysis 历史。

### 测试

```powershell
cd backend
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m py_compile app\main.py app\models.py app\schemas.py app\crud.py app\layout_blueprint.py

cd ..\frontend
npm run lint
npm run build
```

仓库已提供 `.eslintrc.json`，`npm run lint` 可无人值守执行；
`npm run build` 会继续执行 TypeScript 与 Next.js 编译检查。

### AI 与 fallback 判断

真实视觉模型使用 `.env` 中的 `VISION_PROVIDER`、`VISION_API_KEY`、
`VISION_BASE_URL`、`VISION_MODEL`。凭证不可提交。新蓝图的 Prompt 版本为
`layout-blueprint-v2`。`model_name` 为配置的模型/接入点时代表真实模型语义参与；
包含 `region-detection-fallback` 或 `template-fallback` 时代表模型不可用、输出非法
或未提供合法模块后使用本地降级骨架。严格调用模式下非法 JSON 会直接报错。

### 能力状态与阶段定位

按产品路线图，当前重点是「阶段二：排版知识沉淀与检索」——验证系统能否根据真实业务需求
找到正确的排版参考。以下能力**已提前实现并可用**，但按路线图仍以「阶段二检索准确率达标」
为正式启用前提，属于早期／实验能力：

- 排版模式沉淀（人工触发确认，非自动归纳）。
- 场景化排版检索：`POST /api/business-requirements/{id}/match` 返回匹配得分、推荐理由、
  可复用模块、适配建议与风险提示。
- 三个排版意向方向（稳健 / 主视觉强化 / 信息分区探索）：`/intentions` 页面可生成。
- 方向反馈记录与回流：选择、淘汰、调整要求、调整后骨架、实际使用模块、落地结果与
  修改原因均结构化留痕；选择／采纳／落地／淘汰信号按来源模式与案例聚合后，
  以**有界、可解释的规则加成**回流影响 `/match` 排序。

**当前明确未实现**（对应路线图阶段四、五）：

- 排版模式的自动归纳沉淀（现为人工触发）。
- 基于机器学习的排序模型（当前回流为规则加成，非训练模型）。
- 场景/模式分类器、图文向量检索。
- 视觉大模型微调。
- 最终设计稿生成。

历史仓库中保留的偏好推荐、公司风格画像、通用业务生成等后端兼容代码不属于当前交付，
详见下方「历史兼容层」。

### 历史兼容层（保留但不属于当前交付）

以下后端能力来自早期实验，前端入口已下线，接口与数据表仍保留以兼容历史数据。它们对应
路线图里明确「当前不做」的偏好推荐、公司风格画像与轻量训练，**不参与素材 → 蓝图 →
模式 → 需求 → 意向的主链路**：

- 偏好信号：`PreferenceEvent` 数据表（无对外前端入口）。
- 推荐运行与训练看板：`ServiceRun`、`POST /api/recommend`、`/api/service-runs*`、
  `/api/training/*`（overview / task-pack / readiness / review-quality /
  category-discovery / category-suggestions / batch-* 等）。
- 项目分组：`/api/projects`。
- 聚合与画像模块：`concept.py`（设计方法论聚合）、`platform.py`（平台画像）、
  `sampling.py`（公司素材采样）。

保留它们是为了不删除历史数据；后续若确定不再需要，可整体下线而不影响主链路。

系统以现有素材数据和上传能力为基础，提供版本化的标准排版知识层。

当前产品界面已按业务目标收敛，只保留：

- 首页业务流程说明。
- 单张上传、批量上传。
- 排版素材库与素材详情。
- 纯框架排版拆解、人工校正和模式沉淀。
- 排版模式库。
- 结构化业务需求与三个排版意向方向。

旧“找灵感、偏好训练、公司画像、通用业务生成”等前端页面已移除。历史数据库、
上传素材和后端兼容数据均未删除。

阶段 A1 已建立 `layout_blueprints`：

- 每个案例可保存多版排版骨架，人工校正时新增版本，不覆盖历史。
- 模块坐标统一使用 0～1 的归一化比例。
- 模块必须完整位于画布内，`x + width` 与 `y + height` 均不得超过 1。
- `module_count` 必须与 `modules_json` 数量一致，模块 ID 在同一骨架内必须唯一。
- AI 结果保存 `model_name` 和 `prompt_version`。
- 审核状态仅允许 `ai_unverified`、`human_edited`、`verified`。
- 新表由 `Base.metadata.create_all()` 创建，旧数据库不需要删除或重新初始化。
- 新上传案例会自动生成首版低保真排版骨架。
- 旧案例可通过幂等回填脚本补齐，已存在骨架的案例不会重复创建。
- 提供骨架读取、重新生成、人工修订与确认 API。
- 案例详情页提供排版骨架校正台：默认以白底、单色描边的“纯框架图”表达模块位置、
  大小和层级，不模拟真实图片与文案内容。
- 首版骨架基于原图内容边界、纵向区段和列组检测生成；检测不足时才回退方向模板，
  并在 Prompt 版本中明确区分。
- 可按需显示模块标签和焦点区；人工校正、确认或重新生成都会保留历史版本。
- 已确认骨架可在案例详情中沉淀为排版模式；`/patterns` 提供模式库框架预览、
  版本状态和来源案例追溯。
- `/intentions` 可保存结构化真实业务需求，并按行业、品类、渠道、场景、目标、
  画布和信息密度匹配人工确认的模式与案例，结果包含分数和可解释原因。
- 每个需求可组合生成稳健、平衡、探索三个排版意向方向；方向包含纯框架预览、
  适用原因、来源模式／案例、模型与 Prompt 版本以及模型失败回退说明。
- 设计师可记录方向选择、淘汰、调整要求，并用简单坐标表单保存调整后的框架快照；
  反馈单独留痕，不进入公司偏好推荐链路。

详细数据契约见 [排版意向系统接口与数据规范](docs/排版意向系统接口与数据规范.md)。

## Docker

```bash
docker compose up -d --build
```

若使用真实视觉模型，在运行前配置：

```bash
export VISION_PROVIDER=volcengine
export VISION_API_KEY=...
export VISION_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
export VISION_MODEL=...
```

凭证不得写入代码或提交到仓库。

## 第一阶段核心 API

| 方法 | 地址 | 说明 |
|---|---|---|
| POST | `/api/analyze` | 上传单图、AI拆解并入库 |
| POST | `/api/analyze/batch` | 批量导入 |
| GET | `/api/analyze/batch/{id}` | 查询导入进度 |
| POST | `/api/search` | 文本、筛选和参考图混合检索 |
| GET | `/api/cases` | 浏览素材库 |
| GET | `/api/cases/{id}` | 案例拆解详情 |
| GET | `/api/cases/{id}/layout-blueprints` | 获取骨架版本 |
| POST | `/api/cases/{id}/layout-blueprints/generate` | 生成下一版骨架 |
| POST | `/api/layout-blueprints/{id}/revise` | 保存人工骨架校正 |
| POST | `/api/layout-blueprints/{id}/verify` | 确认骨架版本 |
| GET/POST | `/api/layout-patterns` | 查询／沉淀排版模式 |
| POST | `/api/layout-patterns/{id}/verify` | 确认模式版本 |
| GET/POST | `/api/business-requirements` | 查询／保存结构化需求 |
| POST | `/api/business-requirements/{id}/match` | 场景化匹配模式与案例 |
| POST | `/api/business-requirements/{id}/directions/generate` | 生成三个排版方向 |
| GET/POST | `/api/layout-directions/{id}/feedback` | 查询／记录选择与调整 |

## 当前检索说明

100～500 张首批素材阶段先采用可解释结构化混合排序，将需求文本、业务筛选、标签、
版式、字体、风格和色彩相似度共同计分。`POST /api/search` 的输入输出契约已经固定，
后续接入 pgvector 或独立向量库时，不需要重做前端搜索工作台。

## 下一步但不在本次范围

- 登录与角色权限
- 持久化任务队列
- PostgreSQL + 向量检索
- 已选案例进入灵感板和方案工作台
