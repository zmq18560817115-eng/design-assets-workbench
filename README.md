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

## 业务排版意向系统 V1.0

系统正在保留现有上传、AI 拆解、搜索和案例页面的前提下，增加版本化的标准排版知识层。

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
- 可按需显示模块标签和焦点区；人工校正、确认或重新生成都会保留历史版本。

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

## 当前检索说明

100～500 张首批素材阶段先采用可解释结构化混合排序，将需求文本、业务筛选、标签、
版式、字体、风格和色彩相似度共同计分。`POST /api/search` 的输入输出契约已经固定，
后续接入 pgvector 或独立向量库时，不需要重做前端搜索工作台。

## 下一步但不在本次范围

- 登录与角色权限
- 持久化任务队列
- PostgreSQL + 向量检索
- 已选案例进入灵感板和方案工作台
